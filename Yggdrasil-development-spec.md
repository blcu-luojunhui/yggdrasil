# Yggdrasil 开发规格

本文供编码 Agent 直接执行，依据 `Yggdrasil-implementation-plan.md` 与 `Yggdrasil-current-system-integration-design.md`。目标是把当前可变单树原型升级为可复现的版本化认知运行时 MVP。

## 1. 本轮范围

必须完成：

```text
Tree + NodeRevision/EdgeRevision
  -> Ring 0 / active ring
  -> ring-scoped retrieval
  -> SoilEvent + AgentRun + reference
  -> Evaluation（只记录，不直接强化）
  -> candidate revision / candidate ring
  -> seal / activate / rollback
```

本轮不实现自动本体演化、跨树自治委托、独立图数据库、LLM 自动审批、PostgreSQL 适配器和多 worker 分布式调度。

完成后的硬性保证：

1. sealed ring 的 revision 和 manifest 不可修改。
2. 在线检索只能读取 active ring 的 active revision；candidate、quarantined、过期或越权内容不能命中。
3. 旧 `/api/v1/yggdrasil/*` API 继续可用，但写操作生成 candidate，不直接改变在线权重。
4. 每次 Run 保存 forest release、tree/ring、node/edge revision 和 context hash。
5. Ring activate/rollback 为原子事务。
6. Chroma 不是事实源，索引丢失后可从关系表重建。
7. 无 API Key 时 embedding 必须确定性，禁止随机向量。

## 2. 执行规则

按阶段顺序开发，每阶段单独提交并运行测试：

```text
D0 基线与 DuckDB 并发
D1 领域模型与 Repository Protocol
D2 Tree / Revision / Ring 数据层
D3 版本化检索与 Chroma outbox
D4 Soil / Run / Reference / Evaluation
D5 兼容 API 与新资源 API
D6 Candidate Ring、发布门禁、回滚
D7 后台任务、启动、指标和文档
```

依赖方向保持：`api -> application -> core ports <- infra adapters`，`jobs -> application`。

- API endpoint 不得写 SQL。
- core 不得 import Quart、DuckDB 或 Chroma。
- application 不得依赖具体数据库实现。
- 检索不得修改 strength、utility 或 confidence。
- Evaluation 不得直接 activate ring。
- 新写 API 必须接受 actor、reason、`Idempotency-Key`。
- 不得删除旧表、旧 API 或旧 Engine facade。

## 3. D0：基线与数据库并发

修改：`src/infra/database/duckdb/pool.py`、`src/core/bootstrap/app_context.py`、`src/core/yggdrasil/embedding.py`、`src/core/config/yggdrasil_config.py`。

### 3.1 DuckDBPool

当前单连接被多个 executor 协程共享，增加一把进程内 `asyncio.Lock`，所有执行、查询、保存和事务必须串行化。

提供并保留兼容接口：

```python
async def execute_script(statements): ...
async def transaction(self): ...  # async context manager
async def healthcheck(self) -> bool: ...
```

事务内不得暴露裸 connection：

```python
async with pool.transaction() as tx:
    await tx.execute(sql, params)
    await tx.fetch_one(sql, params)
```

异常必须 rollback，commit 失败必须向上抛出，阻塞 DuckDB 调用必须在 executor 中执行。

### 3.2 启动和 embedding

`AppContext.start_up()` 必须调用 `yggdrasil_engine.ensure_skeleton()`，确保默认 domain、main branch、Tree 和 Ring 0 初始化。

无 API Key 时使用 SHA-256 派生 seed 的本地确定性 embedding，同一输入和维度输出必须相同并归一化。禁止使用 Python 内置 `hash()`。增加配置 `embedding_deterministic_fallback: bool = true`。

## 4. D1：模型和端口

新增：

```text
src/core/yggdrasil/cognitive/models.py
src/core/yggdrasil/soil/models.py
src/core/yggdrasil/runtime/models.py
src/core/yggdrasil/forest/models.py
src/core/yggdrasil/evaluation/models.py
src/core/yggdrasil/ports/repositories.py
src/core/yggdrasil/policies/retrieval.py
src/core/yggdrasil/policies/release_gate.py
tests/core/test_models.py
```

旧 `models.py` 保留并 re-export 兼容类型。

### 4.1 状态枚举

```text
NodeStatus: candidate | active | deprecated | archived | quarantined
RingLifecycle: growing | evaluating | sealed | archived
RingHealth: healthy | degraded | quarantined | superseded
EventType: observation | claim | evidence | decision | action_result | evaluation
RunStatus: running | succeeded | failed | cancelled
```

保留现有 `CognitiveRole`，扩展关系 `supports`、`derived_from`、`supersedes`、`used_by`、`imports`、`delegates_to`。

### 4.2 必须实现的模型

`TreeManifest`：`tree_id, tenant_id, name, bounded_context, owner, ontology_version, active_ring_id, capabilities, access_policy, retrieval_policy, status`。

`NodeRevision`：`revision_id, node_id, tree_id, parent_revision_id, role, title, summary, payload, status, utility, confidence, freshness, risk, valid_from, valid_until, evidence_refs, change_reason, author_type, author_id, content_hash, created_at`。

`EdgeRevision`：`revision_id, edge_id, tree_id, parent_revision_id, source_node_id, target_node_id, relation, weight, confidence, applicability, propagation_policy, evidence_refs, valid_from, valid_until, status, created_at`。

`RetrievalScope`：`tree_ids, ring_ids: dict[str,str], tenant_id, valid_at, max_nodes, max_depth`。

`Evaluation`：`evaluation_id, run_id, evaluator_type, technical_success, task_success, result_quality, safety, user_feedback, delayed_outcome, attribution`。

payload 按 role 校验：capacity 至少含 `executor_ref/input_schema/output_schema/permissions`；fact 至少含 `claim/source_authority/verification_method`；heuristic 至少含 `claim/applicability/exceptions`；case 至少含 `run_id/situation/action/outcome`。

### 4.3 Repository Protocol

Protocol 至少提供：

```text
TreeRepository: create/get/list/update_active_ring
RevisionRepository: create_node/create_edge/get/list_by_ids/list_active_for_ring
RingRepository: create/get/add_mapping/seal/activate/rollback
SoilRepository: append_event/get_event/list_after_checkpoint
RunRepository: create/get/add_reference/finish
EvaluationRepository: create/list_by_run
OutboxRepository: enqueue/claim/mark_done/mark_failed
```

Protocol 不得暴露 SQL、DuckDB connection 或 Chroma 类型。

## 5. D2：数据层和迁移

新增：

```text
src/infra/database/duckdb/schema.py
src/infra/database/duckdb/repositories/trees.py
src/infra/database/duckdb/repositories/revisions.py
src/infra/database/duckdb/repositories/rings.py
src/infra/database/duckdb/repositories/soil.py
src/infra/database/duckdb/repositories/runs.py
src/infra/database/duckdb/repositories/outbox.py
tests/infra/duckdb/test_revision_repository.py
tests/infra/duckdb/test_ring_repository.py
```

新增表：`tree`、`cognitive_node`、`node_revision`、`cognitive_edge`、`edge_revision`、`ring`、`ring_node_revision`、`ring_edge_revision`、`soil_event`、`agent_run`、`run_reference`、`evaluation`、`index_outbox`。

表结构必须按集成设计文档的字段落地。JSON 字段使用 DuckDB `JSON`，ID 使用 UUID 字符串；所有表带 `created_at`。必须有：

```text
tree UNIQUE(tenant_id, name)
ring UNIQUE(tree_id, sequence)
ring_node_revision PRIMARY KEY(ring_id, node_id)
ring_edge_revision PRIMARY KEY(ring_id, edge_id)
soil_event UNIQUE(tenant_id, idempotency_key)
```

### 5.1 Ring 0 迁移

实现幂等 `migrate_legacy_nodes_to_ring0()`：

1. 创建 `database-diagnostics` 和 `shared-foundation` Tree。
2. 旧 `cog_node` 每行迁移成 identity + one NodeRevision。
3. 旧 `cog_edge` 每行迁移成 identity + one EdgeRevision。
4. 迁移 revision 初始 `active`；`confidence=old health`、`utility=old strength`、`risk=0`。
5. 创建 Ring 0 manifest 和 content hash。
6. 数量校验通过后才设置 `tree.active_ring_id`。
7. 重复启动不得创建重复 revision。

## 6. D3：版本化检索和索引

新增 `src/application/retrieval_service.py`，入口：

```python
async def retrieve(query: str, scope: RetrievalScope) -> VersionedContext
```

过滤顺序固定：tree/ring manifest -> tenant/access -> active status -> valid time -> vector/keyword candidate -> 一跳关系扩展 -> 排序/去重/预算。

禁止在检索中 `touch_node` 或更新权重。批量仓储接口必须避免逐节点 N+1 查询。

初始排序：

```text
0.40 relevance + 0.20 confidence + 0.15 freshness
+ 0.15 utility + 0.10 relation_relevance
- risk_penalty - redundancy_penalty
```

默认角色预算：capacity 3、schema/fact 8、heuristic 5、case 3、风险/冲突 2。上下文必须返回 nodes、edges、references、total_tokens、markdown、ring_ids；Markdown 不是事实源。

Chroma ID 改为 `revision_id`，metadata 至少包含 `revision_id/node_id/tree_id/ring_id/tenant_id/role/status/content_hash`。revision 创建和 ring 激活只写 outbox；OutboxJob 幂等 upsert/delete。实现 `rebuild_chroma_index(tree_id=None, ring_id=None)`，数据源只能是关系表。

## 7. D4：Soil、Run 和 Evaluation

新增：

```text
src/application/soil_service.py
src/application/run_service.py
src/application/evaluation_service.py
src/infra/execution/skill_registry.py
tests/application/test_soil_service.py
tests/application/test_run_trace.py
tests/application/test_evaluation.py
```

### 7.1 Soil

`append_event(event_type, payload, tenant_id, source_type, source_ref, actor_id, idempotency_key, valid_from)` 必须幂等。原始 payload 不覆盖；更正通过 `corrects/invalidates` 新事件追加。`integrity_hash` 对 canonical JSON 计算 SHA-256。

### 7.2 Run

提供：

```text
start_run(intent, tenant_id, forest_release_id=None)
record_context(run_id, VersionedContext)
record_action_result(run_id, skill_revision_id, input_payload, output_ref, status)
finish_run(run_id, status, result_ref=None)
```

Run 创建时固定 Forest Release；没有真正的多树 release 时创建包含两棵 Tree Ring 0 的默认 release。输入只保存 hash，凭证不得写入 Run、node 或 Soil 明文。

### 7.3 Skill Registry

先实现预注册内存 registry，不实现动态 Python import：

```python
class SkillExecutor(Protocol):
    async def execute(self, payload: dict, timeout: float) -> SkillResult: ...
```

未知 `executor_ref` 必须拒绝执行。

### 7.4 Feedback

旧 `feedback()` 只创建 Evaluation 或 Evaluation event。禁止调用 `update_node_strength`、`update_edge_strength`。

## 8. D5：API

新增：

```text
POST /api/v1/soil/events
GET  /api/v1/soil/events/{event_id}
POST /api/v1/trees
GET  /api/v1/trees/{tree_id}
POST /api/v1/trees/{tree_id}/nodes
POST /api/v1/trees/{tree_id}/nodes/{node_id}/revisions
POST /api/v1/trees/{tree_id}/retrieve
POST /api/v1/runs
POST /api/v1/runs/{run_id}/references
POST /api/v1/runs/{run_id}/finish
POST /api/v1/rings/{ring_id}/seal
POST /api/v1/rings/{ring_id}/activate
POST /api/v1/trees/{tree_id}/rollback
```

写请求缺少 `Idempotency-Key` 返回 400；MVP actor 从 `X-Actor-Id` 读取。新增错误码：`CONFLICT`、`IDEMPOTENCY_CONFLICT`、`RING_NOT_ACTIVE`、`REVISION_IMMUTABLE`、`POLICY_DENIED`、`RELEASE_GATE_FAILED`。

旧 API 兼容规则：`POST /node` 和 `POST /edge` 创建 candidate；`POST /retrieve` 默认解析 active ring 并增加 tree/ring/revision 字段；`POST /feedback` 仅写 evaluation；旧 sandbox 只读映射，不得继续把节点写入主表伪装隔离。

不要新增模块级全局 `_engine`；新 services 由 `ServerContainer` 注入。旧 endpoint 可以继续使用 facade。

## 9. D6：Candidate Ring 和发布

状态机：`growing -> evaluating -> sealed -> archived`，任意 sealed ring 可标记 `quarantined`。

实现 `ReleaseGate`，至少检查：manifest revision 存在；无 candidate/quarantined/过期 state；fact 有 evidence 和 verification；heuristic 有 case/evidence；无悬空边；hash 可重算；回归指标不低于 baseline；token 和 P95 延迟不超预算。

`activate()` 在单 transaction 内校验 `sealed + healthy`、更新 `tree.active_ring_id`、写审计、提交。DuckDB 阶段使用按 tree_id 的 `asyncio.Lock`。失败不能留下半激活状态。rollback 只切 active pointer，不修改历史 ring。

## 10. D7：后台任务、启动和指标

新增/修改：`src/jobs/outbox_job.py`、`src/jobs/evaluation_job.py`、`src/jobs/inspection_job.py`、`src/jobs/season_manager.py`、`src/core/dependency/container.py`、`src/core/bootstrap/app_context.py`。

本轮自动启动只包含 OutboxJob、EvaluationJob、InspectorJob；四季候选生成先保留 service 接口，不自动运行。

每个 job 必须有 `start/stop(timeout)`、取消响应、lease/锁、重试上限、单条失败隔离和运行日志。新增指标：

```text
ygg_soil_events_total{event_type,status}
ygg_retrieval_total{tree_id,ring_id,status}
ygg_retrieval_latency_seconds
ygg_run_total{status}
ygg_outbox_pending
ygg_ring_activation_total{result}
ygg_ring_rollback_total
ygg_release_gate_failed_total{reason}
```

## 11. 测试和完成标准

必须新增至少：

```text
tests/core/test_models.py
tests/infra/test_duckdb_pool.py
tests/infra/duckdb/test_revision_repository.py
tests/infra/duckdb/test_ring_repository.py
tests/application/test_soil_service.py
tests/application/test_run_trace.py
tests/application/test_evaluation.py
tests/application/test_retrieval_service.py
tests/api/test_versioned_endpoints.py
tests/jobs/test_outbox_job.py
```

必须覆盖：确定性 embedding；DuckDB 并发和 rollback；事件幂等；revision 不可变；candidate/过期/quarantined/越权过滤；稳定排序；Chroma 重建；feedback 不改权重；门禁失败不激活；activate/rollback 原子性；Run 引用完整；outbox 重试和 dead-letter；优雅关闭。

每阶段运行：

```bash
ruff check .
pytest -q
```

测试必须使用 `tmp_path` 临时 DuckDB/Chroma，不依赖网络、真实 LLM Key 或共享数据库。

Definition of Done：无 placeholder 或“以后再隔离”的假实现；异常有明确错误码；schema 初始化幂等；日志有 trace/run/job/ring 标识；旧 API 和现有数据读取不破坏；文档记录完成项、未完成项、测试和风险。

## 12. 回退与后续 Backlog

保留配置开关：`versioned_read_enabled`、`soil_write_enabled`、`run_trace_enabled`、`candidate_publish_enabled`、`outbox_worker_enabled`。关闭新功能后旧 facade 仍可读取 Ring 0。

D0-D7 和 Ring 0/Ring 1 回归通过后，才开发 Spring ingestion、Summer replay、Autumn consolidation、Winter release、Agent Memory Tree、PostgreSQL/pgvector、RBAC/ABAC 和多 worker。编码 Agent 不得提前引入分布式组件或自动学习逻辑。
