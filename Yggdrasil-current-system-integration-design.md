# Yggdrasil 现有系统集成设计

## 1. 目标与结论

本文回答《Yggdrasil Agent 认知森林落地方案》如何应用到当前仓库，而不是重新设计一套平行系统。

推荐路线是：**保留 Quart 模块化单体和 core/api/jobs/infra 分层，以现有单树原型为兼容入口，在 core 内逐步引入 Soil、Tree、Revision、Ring、Run 和 Evaluation 六个稳定边界。** 第一阶段继续使用 DuckDB + ChromaDB 完成单实例试点；当需要多实例、并发审批和生产级事务时，再把仓储实现切换到 PostgreSQL + pgvector。

目标形态不是让现有 `CognitiveNode` 继续增加字段，而是形成三条彼此隔离的状态链：

```text
事实链：Environment -> SoilEvent / Evidence（追加写）
认知链：Candidate -> Revision -> Ring（版本化发布）
运行链：Run -> RetrievalReference -> ActionResult -> Evaluation（可复现、可归因）
```

在线检索只读取 active ring；Agent 运行结果只写 Soil 和 Run；Evaluation 与季节作业只能生成候选修订；Ring Manager 是候选内容进入生产检索视图的唯一入口。

## 2. 当前系统基线

### 2.1 可以保留的部分

| 现有能力 | 当前实现 | 在目标系统中的位置 | 处理方式 |
|---|---|---|---|
| HTTP 服务 | Quart / Hypercorn | API 层 | 保留 |
| 依赖注入与生命周期 | `ServerContainer` / `AppContext` | Bootstrap | 保留并扩展 |
| 关系存储 | DuckDB | MVP 仓储适配器 | 保留到单实例试点结束 |
| 向量存储 | ChromaDB | MVP 向量索引适配器 | 保留，但索引键改为 revision ID |
| 节点与边 | `CognitiveNode` / `CognitiveEdge` | 认知模型雏形 | 拆成稳定身份和不可变修订 |
| 图扩展 | `SubtreeRetriever` + BFS | Tree 内检索 | 改为 ring 内、关系白名单的一跳扩展 |
| 沙盒 | `SandboxManager` | Candidate workspace | 替换占位隔离语义 |
| 季节调度 | `SeasonManager` / `InspectionJob` | Evolution jobs | 从日历轮换改为有输入输出的作业 |
| 指标、日志、Trace | `infra/observability` | 可观测基础 | 保留并补 Run/Ring 维度 |
| Web 页面 | `frontend/index.html` | 管理控制台原型 | 后续改为 Tree/Ring/Candidate 管理视图 |

### 2.2 当前模型与目标模型的关键差距

| 当前行为 | 风险 | 目标行为 |
|---|---|---|
| `strength` 同时代表可信度、效用和排序权重 | 技术成功会被误当成知识正确 | 分离 `utility`、`confidence`、`freshness`、`risk` |
| 节点内容原地可变 | 无法复现历史上下文 | `CognitiveNode` 保存身份，`NodeRevision` 保存不可变内容 |
| `feedback()` 直接修改节点和边强度 | 形成自我强化闭环 | 写 `Evaluation`，异步计算候选质量 |
| 检索没有 ring、状态、有效期和权限过滤 | candidate、过期或越权内容可能进入上下文 | 从 active ring 的授权 revision 集合检索 |
| Chroma 以 node ID 建索引 | 修订后历史向量不可复现 | 以 revision ID 建索引，metadata 带 tree/ring/tenant/status |
| `Branch` 只有状态，没有 overlay 归属 | 沙盒节点实际写入主节点表，无法隔离或回滚 | workspace 只保存相对基线 ring 的 revision overlay |
| 季节只是枚举和衰减定时器 | 没有进入条件、产物、门禁 | 每季是可重试、可审计的 `EvolutionJob` |
| `tree_log` 是可选操作日志 | 不能回答一次 Run 使用了什么 | 建立 Run、引用、事件和发布审计模型 |
| domain path 同时承担树和目录 | 无法表达独立 owner、权限和发布 | `Tree` 是限界上下文，`domain_path` 只做树内命名空间 |

### 2.3 Phase 0 必须先修正的基线问题

这些问题会使检索评估和迁移结果失真，应先于新架构开发处理：

1. `AppContext` 当前调用 `store.ensure_skeleton()`，没有调用 `engine.ensure_skeleton()`，因此默认领域和 main 分支并未由启动流程可靠创建。
2. 未配置 API Key 时 embedding 每次生成随机向量，同一文本写入和查询不稳定，不能作为检索基线。测试环境应改为确定性 embedding，生产试点必须配置真实模型。
3. DuckDB 与 Chroma 是双写但无 outbox/补偿；节点写入成功、向量写入失败时会永久不一致。需要索引任务表和可重建机制。
4. `feedback()` 直接改变在线排序，违反“评价异步、候选发布”的核心边界。兼容 API 可以保留，但只能写 evaluation 事件。
5. 沙盒没有 revision/branch 关联，所谓 discard 不会撤销已创建节点。引入 revision 前不得把沙盒称为隔离环境。
6. 检索逐节点查询和逐节点 touch，存在明显 N+1 写放大；检索路径不应同步更新认知内容，可异步记录 usage event。
7. 当前没有自动化测试和可复现任务集，无法证明新检索优于普通 RAG。

## 3. 架构决策

### 3.1 演进方式

有两种可行方案：

| 方案 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| 原地扩充 `YggdrasilEngine` 和现有表 | 初期代码少、API 改动小 | 继续混合运行、治理和存储职责；迁移到 revision/ring 时风险集中 | 不推荐 |
| 模块化单体内建立新边界，旧 Engine 做 facade | 能渐进迁移；每个边界可独立测试和替换仓储；旧 API 可兼容 | 初期会多一层应用服务和映射代码 | 推荐 |

推荐的调用方向：

```text
api -> application -> domain ports <- infra adapters
                 |
                 +-> jobs (只触发 application use case)
```

现有 `src/core/yggdrasil` 不需要一次性删除。先将 `YggdrasilEngine` 收敛为兼容 facade，内部委托给新的 application services；兼容期结束后再按领域模块移除旧入口。

### 3.2 数据库路线

| 路线 | 适用阶段 | 约束 |
|---|---|---|
| DuckDB + ChromaDB | 本地开发、单进程 Phase 0/1 试点 | 单写者；后台作业不可多实例；发布操作需进程内互斥 |
| PostgreSQL + pgvector | 多实例、生产审批、并发 Run、可靠 outbox | 需要数据库迁移、连接池和部署依赖 |

当前不要同时维护 DuckDB 和 PostgreSQL 两套业务 SQL。先定义 Repository Protocol 和契约测试，再更换 adapter。切换条件建议设为任一项满足：需要两个以上服务实例、稳定写入超过 20 QPS、出现并发发布/审批需求、DuckDB 写锁影响在线检索。

### 3.3 图检索路线

MVP 不引入图数据库。树内检索采用结构化过滤 + 向量/关键词召回 + 一跳批量扩展。只有在真实数据证明两跳以上扩展是主要质量来源，且 PostgreSQL 查询达到延迟瓶颈后，才评估专用图数据库。

## 4. 目标模块映射

建议将新能力放入以下结构：

```text
src/
  api/v1/endpoints/
    soil.py
    trees.py
    runs.py
    rings.py
    evolution.py
    forest.py
  application/
    soil_service.py
    tree_service.py
    retrieval_service.py
    run_service.py
    evaluation_service.py
    evolution_service.py
    ring_service.py
    forest_service.py
  core/yggdrasil/
    soil/models.py
    forest/models.py
    cognitive/models.py
    runtime/models.py
    evaluation/models.py
    evolution/models.py
    ports/repositories.py
    policies/retrieval.py
    policies/release_gate.py
    policies/propagation.py
  infra/
    database/duckdb/repositories/
    vector/chroma_index.py
    execution/skill_registry.py
  jobs/
    outbox_job.py
    evaluation_job.py
    evolution_job.py
    inspection_job.py
```

边界职责如下：

| 模块 | 唯一写入职责 | 不允许做的事 |
|---|---|---|
| Soil Service | 追加 Event/Evidence，分配 checkpoint | 直接创建 active knowledge |
| Tree Service | Tree Manifest、节点身份、候选修订 | 激活未发布修订 |
| Retrieval Service | 固定 release/ring 下检索和上下文组装 | 修改节点分数 |
| Run Service | 固化版本、执行 Skill、记录引用和结果 | 根据一次成功直接强化 |
| Evaluation Service | 生成多维评价和归因 | 直接发布知识 |
| Evolution Service | 消费事件、生成候选、回放和归纳 | 切换 active ring |
| Ring Service | 构建 manifest、门禁、seal/activate/rollback | 修改 sealed ring |
| Forest Service | 路由、组合各树 ring、发布 Forest Release | 穿透树的私有节点 |

## 5. 数据模型如何落到现有表

### 5.1 树与命名空间

新增 `tree` 表；保留 `domains`，但将其语义缩小为树内目录。

```text
tree
  id, tenant_id, name, bounded_context, owner
  ontology_version, active_ring_id
  access_policy, retrieval_policy, evaluation_policy, season_policy
  status, created_at, updated_at

domains
  + tree_id
  UNIQUE(tree_id, full_path)
```

现有 `database/http/auth/task/utils` 顶级路径不要直接各自变成树。首个试点建议只创建：

- `database-diagnostics`：数据库诊断的 Domain Tree；
- `shared-foundation`：通用安全策略和输出规范；
- `agent-memory` 延后到 Phase 2。

原有路径按内容迁移到这两棵树的树内 namespace，无法确定所有者或评价方法的内容先放 candidate，不进入 Ring 1。

### 5.2 认知身份与修订

将现有 `cog_node` 拆为稳定身份和不可变修订：

```text
cognitive_node
  node_id, tree_id, domain_id, role, created_by, created_at

node_revision
  revision_id, node_id, parent_revision_id
  title, summary, payload_json, content_hash
  status, utility, confidence, freshness, risk
  valid_from, valid_until
  change_reason, evidence_refs, author_type, author_id, created_at
```

`payload_json` 按 role 由 Pydantic discriminated union 校验：`SkillSpec`、`KnowledgeClaim`、`MemoryEpisode`。这比给表不断增加可空列更适合当前 DuckDB MVP，也保留了后续拆列和索引的空间。

边采用同样结构：

```text
cognitive_edge
  edge_id, tree_id, source_node_id, target_node_id, relation

edge_revision
  revision_id, edge_id, parent_revision_id
  weight, confidence, applicability, propagation_policy
  evidence_refs, valid_from, valid_until, status, created_at
```

### 5.3 年轮与发布视图

```text
ring
  ring_id, tree_id, sequence, lifecycle_status, health_status
  parent_ring_ids, soil_checkpoint, ontology_version, policy_version
  evaluation_report_ref, quality_metrics, content_hash
  started_at, sealed_at

ring_node_revision(ring_id, node_id, revision_id)
ring_edge_revision(ring_id, edge_id, revision_id)

forest_release
  release_id, sequence, status, content_hash, created_at, activated_at

forest_release_ring(release_id, tree_id, ring_id)
```

`active_ring_id` 是控制面的快速指针，真正可复现状态来自 manifest 关联表。激活操作必须在一个事务内校验 `sealed + healthy`、更新 active 指针并写审计事件；rollback 本质上是把指针切回已封存 ring，不修改任何历史内容。

### 5.4 Soil、Run 与 Evaluation

```text
soil_event
  event_id, event_type, tenant_id, subject_id
  source_type, source_ref, payload_json
  observed_at, ingested_at, valid_from, valid_until
  trust_level, integrity_hash, access_scope, contamination_status
  correlation_id, causation_id, idempotency_key, checkpoint

evidence
  evidence_id, event_id, media_type, object_ref, content_hash
  classification, access_scope, created_at

agent_run
  run_id, tenant_id, intent, forest_release_id, soil_checkpoint
  prompt_context_hash, selected_skill_revision_id
  decision_trace_ref, result_ref, status, started_at, completed_at

run_tree_ring(run_id, tree_id, ring_id)
run_node_reference(run_id, revision_id, rank, score, usage_type)
run_edge_reference(run_id, revision_id)
action_result(run_id, skill_revision_id, input_hash, output_ref, status)

evaluation
  evaluation_id, run_id, evaluator_type
  technical_success, task_success, result_quality, safety, user_feedback
  delayed_outcome, attribution_json, created_at
```

证据大对象只在数据库保存元数据和 hash；MVP 可用本地受控目录实现 ObjectStore adapter，生产再切对象存储。

### 5.5 索引一致性

Chroma 不再作为事实源。新增 `index_outbox`：

```text
index_outbox
  id, aggregate_type, aggregate_id, operation
  payload_hash, status, attempts, available_at, processed_at, last_error
```

候选或 ring 发布事务只写 DuckDB 和 outbox。后台 job 幂等更新 Chroma。检索发现索引条目不在目标 ring manifest 时必须丢弃；索引可以从 revision 表全量重建。

## 6. 关键运行流程

### 6.1 在线 Agent Run

```text
1. Run Service 创建 run，解析当前 active Forest Release
2. Forest Service 根据 intent、权限和 capability 路由 1-3 棵树
3. Retrieval Service 对每棵树固定 ring_id 检索
4. 先按 tenant/status/valid_time/ring manifest 过滤，再混合召回
5. 按关系白名单做一跳扩展，批量取节点和边
6. 按角色配额和 token budget 组装 VersionedContext
7. Run Service 固化 revision 引用和 context hash
8. Skill Registry 根据 executor_ref 执行能力
9. ActionResult、Observation 和 Decision 追加到 Soil
10. Evaluation job 异步评价；在线响应不等待知识演化
```

`VersionedContext` 必须返回结构化数据和 Markdown 两种表示，至少包含 `tree_id/ring_id/revision_id/source/evidence/applicability/confidence`。Markdown 只是 Agent 输入格式，不是审计事实源。

### 6.2 候选知识晋升

```text
Soil event
  -> Spring job 创建 candidate case/state
  -> Summer job 回放并聚合 evaluation
  -> Autumn job 去重、冲突处理、产生候选 heuristic/fact
  -> 人工审批高风险修订
  -> Winter job 构建 candidate ring 并执行门禁
  -> Ring Service seal
  -> activate（或纳入新的 Forest Release）
```

每步写 `evolution_job` 和 `evolution_artifact`，使用 `(tree_id, job_type, input_checkpoint, policy_version)` 作为幂等边界。失败可从最后成功阶段重试，不依赖一个常驻协程记忆状态。

### 6.3 回滚与污染处置

```text
检测污染来源
  -> 标记 event/evidence/revision contamination_status
  -> 按 propagation_policy 计算影响集合
  -> 高风险 skill 先暂停
  -> active ring 标记 degraded/quarantined
  -> 指针回退到上一 healthy sealed ring
  -> 生成修复 candidate，而不是修改污染 ring
  -> 查询 run references 得到受影响 Run
```

`contradicts` 只进入冲突队列；`derived_from` 要求下游重新验证；`used_by` 只标记历史影响，不能传播“有害”判断。

## 7. 检索改造

### 7.1 两级路由

Phase 1 只有两棵树时，Forest Router 先用可解释规则实现：capability 标签匹配、tree access、tree health 和固定优先级。Phase 2 数据足够后再加入向量路由或学习排序，必须保留路由原因。

### 7.2 树内召回

现有纯向量锚点 + BFS 改为：

```text
candidate = keyword_top_k UNION vector_top_k UNION exact_capability_match
filtered  = candidate INTERSECT ring_manifest AND access AND validity AND active_status
expanded  = one_hop(candidate, allowed_relations, per_relation_budget)
ranked    = score(filtered + expanded) - redundancy - risk
context   = allocate_by_role(ranked, token_budget)
```

初始允许图扩展的关系建议为 `enables/evidences/supports/specializes`；`contradicts` 单独保留风险槽位；`strengthens/weakens/used_by` 不用于真值传播。

复杂度目标：召回集合大小记为 `K`，一跳平均出度为 `d`，扩展应控制在 `O(K*d)`，通过每种关系预算将结果上限固定。禁止恢复当前逐节点 SQL 查询，仓储必须提供批量 `get_revisions(ids)` 和 `get_edges_from(ids, relations)`。

### 7.3 排序与预算

不要直接把所有维度相乘，因为任一低值会把候选归零且难以解释。MVP 建议先使用可校准的加权和，再应用硬门禁：

```text
base = 0.40 * relevance
     + 0.20 * confidence
     + 0.15 * freshness
     + 0.15 * task_utility
     + 0.10 * relation_relevance

score = base - risk_penalty - redundancy_penalty
```

权限、ring membership、生命周期和有效时间是过滤条件，不是软分数。权重通过离线任务集调整，不由线上单次反馈直接改变。

## 8. API 迁移策略

新增文档方案中的资源化 API，路径使用 `/api/v1/soil`、`/api/v1/trees`、`/api/v1/runs`、`/api/v1/rings`、`/api/v1/forest`。

现有 `/api/v1/yggdrasil/*` 保留一个发布周期：

| 旧 API | 兼容行为 |
|---|---|
| `POST /node` | 创建 candidate node + first revision，不直接进入 active ring |
| `POST /edge` | 创建 candidate edge revision |
| `POST /retrieve` | 未传 release 时解析 active release，并返回新增版本字段 |
| `POST /feedback` | 写 evaluation，不再同步修改 strength |
| sandbox API | 映射为 workspace overlay，旧占位 branch 数据只读 |

所有写请求新增 `Idempotency-Key`、actor 和 reason。API 层只做校验和错误映射，不能直接访问 repository。当前 blueprint 模块级 `_engine` 注入应迁移为 app context/provider 获取，避免测试隔离和多 app 实例互相污染。

## 9. 四季与后台任务改造

当前 `InspectionJob` 同时巡检、衰减和季节行为，应拆为：

| Job | 触发方式 | 输入 | 输出 |
|---|---|---|---|
| OutboxJob | 高频轮询 | pending outbox | 向量索引状态 |
| EvaluationJob | Run 完成/反馈事件 | run + references | evaluation |
| SpringIngestionJob | checkpoint/批次阈值 | Soil events | candidate revisions |
| SummerReplayJob | 样本阈值/人工触发 | candidates + task set | evaluation report |
| AutumnConsolidationJob | 候选稳定/人工触发 | candidates + evaluations | promotion set/conflicts |
| WinterReleaseJob | promotion set ready | revisions + baseline ring | candidate ring/gate report |
| InspectorJob | 定时 | 全局元数据 | 悬空边、过期状态、索引漂移报告 |

`SeasonManager.next_season()` 不应自动推动生产状态。季节状态来自作业状态机；每棵树可独立执行，失败后停在当前阶段并暴露原因。

DuckDB 阶段只运行单个 job worker，并使用数据库 lease 防止同一任务重复执行。迁移 PostgreSQL 后可使用 `FOR UPDATE SKIP LOCKED` 或工作流引擎。

## 10. 分阶段实施

### Phase 0：建立可信基线（1-2 周）

交付物：

- 修复启动骨架、确定性 embedding、双写漂移和沙盒命名问题；
- 建立 100-300 条数据库诊断任务集与普通 RAG 对照；
- 定义 `database-diagnostics` 和 `shared-foundation` manifest；
- 为现有 Engine/Store/Retriever 增加契约和回归测试；
- 记录检索准确率、任务成功率、延迟、token 和错误引用率。

退出标准：同一数据和配置可重复得到稳定基线，失败能够定位到检索、推理或 Skill 执行阶段。

### Phase 1A：版本化读模型（2 周）

交付物：Tree、NodeRevision、EdgeRevision、Ring 表和 repository ports；迁移现有节点为 first revision；生成 Ring 0；Chroma 改用 revision ID；检索固定 Ring 0。

退出标准：旧 API 仍可查询，任一次检索能返回 ring/revision，Ring 0 可重建且 hash 稳定。

### Phase 1B：Soil 与 Run 闭环（2 周）

交付物：Soil 追加事件、Evidence、AgentRun、引用表、Skill Registry、ActionResult、索引 outbox；接入 3-5 个只读数据库诊断 Skill。

退出标准：一次任务从检索到执行、结果和评价全链可追踪；重放时能解析同一 ring 和 revision 集合。

### Phase 1C：候选发布与回滚（2 周）

交付物：candidate 生命周期、人工审批、candidate ring、发布门禁、seal/activate/quarantine/rollback；旧 feedback API 改为 evaluation 写入。

退出标准：candidate 不进入在线检索；Ring 1 可发布；污染演练可回退到 Ring 0。

### Phase 2：评价与春夏演化（4-6 周）

交付物：多维 Evaluation、case 自动挂载、回放框架、utility/confidence/freshness、Agent Memory Tree、Forest Release、规则版两级路由。

退出标准：Ring 2 相对 Ring 1 在预设任务集上达到门禁增益，且每项增益有引用归因。

### Phase 3：秋冬治理与生产化（6-10 周）

交付物：聚类去重、冲突队列、传播策略、发布审批、受影响 Run 查询、PostgreSQL/pgvector adapter、多 worker 调度。

退出标准：多实例下发布原子性、权限隔离、索引恢复和局部/整轮回滚通过演练。

## 11. 首批代码改造顺序

1. 增加 repository protocols 和 DuckDB contract tests，先把业务层从具体 SQL 中解耦。
2. 引入 Tree/Revision/Ring 模型和 migration，迁移旧节点得到 Ring 0。
3. 将 `SubtreeRetriever` 改为接收显式 `RetrievalScope(tree_ids, ring_ids, tenant, valid_at)`。
4. 增加 revision 索引 outbox，并提供 Chroma 全量重建命令。
5. 增加 Soil 和 Run，先记录调用链，不急于自动学习。
6. 将 `feedback()` 降级为 evaluation adapter，停止在线直接改权重。
7. 实现 candidate ring 和人工 seal/activate/rollback。
8. 最后拆分季节作业；没有 Run 和 Ring 数据前，自动四季没有可靠输入。

这个顺序的关键在于先建立“可复现读取”，再开放“可演化写入”。如果新演化逻辑效果不佳，可以关闭 Evolution jobs，系统仍能作为固定 Ring 的版本化 RAG/Skill Runtime 运行。

## 12. 测试与验收矩阵

| 层级 | 必测内容 |
|---|---|
| 模型 | role payload 校验、状态迁移、内容 hash、有效期 |
| Repository 契约 | 追加写、幂等键、revision 不可变、ring manifest 一致性 |
| 检索 | ring/tenant/status/time 过滤、关系预算、角色配额、确定性排序 |
| Run | 固定 release、引用完整、Skill 超时/取消、结果落 Soil |
| 发布 | 门禁失败不激活、seal 后不可写、原子切换、回滚 |
| 污染 | 关系差异化传播、隔离后不可检索、受影响 Run 可查询 |
| 恢复 | Chroma 丢失后重建、outbox 重试、进程重启后 job 续跑 |
| 对照评估 | 无认知、普通 RAG、Yggdrasil 三组任务质量与成本 |

首期验收不以节点数量为目标。最小业务指标建议提前固定：数据库诊断任务成功率提升、错误知识引用率不增加、P95 检索延迟和上下文 token 成本在预算内、所有回答具备 revision/evidence 引用、一次污染回滚演练成功。

## 13. 暂不实施的能力

以下能力保留接口但不进入首期：独立图数据库、自动本体演化、LLM 自动批准知识、多模型投票、跨区域多活、复杂实时事件总线、完全自治的跨树委托。

首期最重要的不是让树自动长得更快，而是证明四个工程事实：同一 Ring 能复现；候选不会污染线上；知识能追溯到证据；失败后能可靠回滚。
