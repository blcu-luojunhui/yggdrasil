# Yggdrasil 返工计划

## 1. 文档目的

本文根据以下两份规格和当前代码状态编写：

- `Yggdrasil-development-spec.md`
- `Yggdrasil-frontend-observation-design.md`

返工目标不是继续堆叠模块，而是把当前“后端骨架 + 前端 F0/F1 原型”收敛为一个可以启动、调用、验证和回滚的版本化认知运行时 MVP。

本轮完成的判断依据是行为验收，不是文件是否存在。每个阶段都必须同时具备：实现、测试、路由或生命周期接通、失败路径和文档记录。

## 2. 当前基线

### 2.1 已具备

- 新领域模型、Repository Protocol 和 DuckDB repository 的初始实现。
- Ring、revision、SoilEvent、AgentRun、Evaluation 的基础数据结构。
- SHA-256 派生的确定性 embedding fallback。
- 旧 Yggdrasil API 和 Engine facade 基本保留。
- 前端森林全景和单棵树的 SVG 原型。
- `python -m pytest -q` 当前有 30 个基础测试通过。

### 2.2 当前阻断项

1. 新 schema 没有接入启动流程。
2. 新 API blueprint 没有注册，版本化 API 对外不可用。
3. observe API 完全缺失，前端只能降级到旧 API。
4. Ring activate/rollback 不是同一事务，状态语义不正确。
5. DuckDB transaction 暴露裸 connection，不符合端口边界。
6. Retrieval tenant 过滤存在无条件放行，存在数据隔离风险。
7. OutboxJob 和 EvaluationJob 没有随应用启动。
8. Soil、Run、Evaluation、Retrieval、Job、API 测试严重不足。
9. 前端 Soil、Run、Ring 三个观察场景尚未实现。
10. `ruff check .` 当前存在 48 个错误。

## 3. 返工原则

1. **先恢复可运行性，再优化视觉**：没有 schema、路由和生命周期接通，前端视觉不作为完成依据。
2. **关系表是事实源**：Chroma 只能由 outbox 或重建任务生成，不能成为在线事实来源。
3. **发布状态不可含糊**：`growing -> evaluating -> sealed -> active/archived`，Ring 的状态和 Tree active pointer 必须有明确事务语义。
4. **只读观察必须真实**：数据不可用时显示观测延迟或来源不可验证，不把旧数据或随机数据伪装成当前森林。
5. **所有安全过滤前置**：tenant、access policy、status、valid time 必须在数据库查询或明确的 service 边界中完成。
6. **每阶段必须可验收**：阶段结束条件包含命令、接口和故障场景，不以“代码已提交”作为退出条件。
7. **兼容优先但不复制旧缺陷**：旧 API 继续保留，旧写入转换为 candidate/evaluation 语义；新代码不得继续调用旧的权重更新路径。

## 4. 目标架构

```text
启动层
  -> schema migration / skeleton / jobs lifecycle

API 层
  -> versioned write API
  -> observe read-only API
  -> legacy compatibility facade

Application 层
  -> Tree / Revision / Ring / Soil / Run / Evaluation / Retrieval

Core 端口
  -> Repository Protocol
  -> ReleaseGate / RetrievalPolicy / SkillExecutor

Infra 层
  -> DuckDB transaction proxy
  -> relation repositories
  -> Chroma index adapter
  -> Outbox worker
```

在线读取路径必须固定为：

```text
请求
  -> tenant/access policy
  -> forest release / tree active ring
  -> ring mapping
  -> active revision + valid time
  -> retrieval / observation view model
```

## 5. 分阶段返工

## R0：恢复基线和启动可运行性

### 目标

让新数据层能够在空数据库中初始化，并让测试和应用启动使用同一套入口。

### 工作项

- 在 `DuckDBPool` 增加：
  - `execute_script(statements)`
  - `healthcheck()`
  - 事务代理对象 `Transaction`，禁止暴露裸 connection
  - `execute/fetch_one/fetch_all/commit/rollback` 异步方法
- 所有 DuckDB 阻塞调用继续放入 executor。
- 事务代理持有 pool lock，异常自动 rollback，commit 失败向上抛出。
- 在 `YggdrasilStore.ensure_skeleton()` 或独立 migration service 中执行 `schema.py` 的新 DDL。
- 保持旧表初始化逻辑，并增加新表初始化顺序和幂等校验。
- 启动时执行 Ring 0 migration，重复启动不得重复生成 revision。
- 统一测试命令为 `python -m pytest -q`，修正项目配置使 `pytest -q` 也可执行。
- 清理 `ruff` 违规项，先达到零 lint error。

### 退出条件

- 新建临时 DuckDB 后，启动可以创建全部新表和旧表。
- 第二次启动不产生重复 tree、ring、revision。
- transaction 的 commit、rollback、异常和并发测试通过。
- `pytest -q` 和 `python -m pytest -q` 均通过。
- `ruff check .` 无错误。

## R1：接通依赖注入、API 和后台生命周期

### 目标

让已经存在的 service、repository、job 真正进入应用运行路径。

### 工作项

- 在 `src/api/v1/routes/routes.py` 注册：
  - trees
  - rings
  - soil
  - runs
  - observe
- 移除新增 endpoint 对模块级全局 engine 的依赖，统一从 `ServerContainer` 注入。
- 为新增写 API 统一实现：
  - `Idempotency-Key` 校验
  - `X-Actor-Id` 读取
  - actor/reason 入 service
  - 统一错误码和响应结构
- 在 `AppContext.start_up()` 启动：
  - `OutboxJob`
  - `EvaluationJob`
  - `InspectionJob`
- 在 `shutdown()` 按相反顺序停止所有 job，并等待取消完成。
- 增加配置开关：
  - `versioned_read_enabled`
  - `soil_write_enabled`
  - `run_trace_enabled`
  - `candidate_publish_enabled`
  - `outbox_worker_enabled`

### 退出条件

- 应用 url map 包含所有规定的 versioned API。
- 关闭 `versioned_read_enabled` 后旧 facade 仍可读取 Ring 0。
- 启动日志明确记录每个 job 的启动结果。
- 关闭应用不会遗留后台 task。

## R2：修复 Ring、Revision 和发布一致性

### 目标

实现不可变 revision、正确 Ring 状态机和原子 activate/rollback。

### 工作项

- Revision 创建后禁止 update 原地修改；变更必须生成新 revision。
- 对 sealed Ring 的：
  - node revision mapping
  - edge revision mapping
  - manifest
  - content hash
  全部拒绝修改。
- 明确 Ring 状态机：

```text
growing -> evaluating -> sealed -> active
sealed/active -> archived
任意 sealed/active -> quarantined（仅通过隔离流程）
```

- `ReleaseGate` 必须默认开启证据检查。
- 增加门禁检查：
  - manifest 存在
  - 无 candidate/quarantined/过期 revision
  - fact 有 evidence 和 verification
  - heuristic 有 case 或 evidence
  - 无悬空边
  - content hash 可重算
  - baseline 指标满足要求
  - token/P95 预算满足要求
- 将 `activate()` 和 `tree.active_ring_id` 更新放入同一个数据库事务。
- activate 前在事务内重新校验 `sealed + healthy`，防止 TOCTOU。
- rollback 只切换 active pointer，不把目标历史 Ring 标成 archived。
- 使用 tree 粒度锁保护进程内并发，并用数据库条件更新做最终一致性保护。
- 写入 ring activation、rollback、gate failure 审计事件和指标。

### 退出条件

- 门禁失败不会修改 Ring 状态或 Tree active pointer。
- activate 任一写入失败时，Ring 和 Tree pointer 都保持原状。
- rollback 后历史 Ring 内容不变，仅 active pointer 改变。
- sealed Ring 任何 mapping/hash 修改都会返回明确错误码。

## R3：修复检索、Soil、Run 和 Outbox

### 目标

让在线读取只看到授权的 active revision，并形成可复现 Run trace。

### 工作项

- Retrieval 查询层直接过滤：
  - tenant
  - access scope
  - Ring/tree manifest
  - `status = active`
  - valid time
- 删除无条件放行逻辑，非 default tenant 必须走真实隔离。
- 检索上下文必须返回：
  - nodes
  - edges
  - references
  - total_tokens
  - markdown
  - ring_ids
  - forest_release_id
  - as_of
- 一跳扩展不能重新拉取整批节点；增加按 node ids 批量查询。
- 评分固定实现 relevance、confidence、freshness、utility、relation relevance、risk 和 redundancy。
- Soil event 使用 canonical JSON + SHA-256；同 tenant/idempotency key 重复请求返回同一事件。
- 同一幂等键但 payload 不同返回 `IDEMPOTENCY_CONFLICT`。
- Run 创建时固定 forest release 和 ring context；输入只保存 hash，不保存凭证明文。
- `record_context()` 完整保存 revision/reference；`finish_run()` 只能从 running 进入终态。
- Outbox payload hash 改为 SHA-256，增加重试上限、lease、dead-letter 和可恢复状态。
- `rebuild_chroma_index(tree_id=None, ring_id=None)` 只从关系表读取。
- Chroma ID 使用 `revision_id`，metadata 补齐 tree/ring/tenant/status/content_hash。

### 退出条件

- candidate、quarantined、过期、越权 revision 在检索中均不可见。
- 同一输入在同一 release 下可以复现相同 context hash。
- Chroma 删除后可从关系表重建，重建结果与 active ring 一致。
- Soil 幂等、Run 引用完整、Outbox 重试和 dead-letter 测试通过。

## R4：实现只读 Observation API

### 目标

给前端提供稳定的只读数据契约，不再从旧 API 或硬编码 domain 拼装森林。

### API

```text
GET /api/v1/observe/forest?release_id=
GET /api/v1/observe/trees/{tree_id}?ring_id=
GET /api/v1/observe/trees/{tree_id}/graph?ring_id=&role=&status=
GET /api/v1/observe/soil/events?after=&before=&event_type=
GET /api/v1/observe/runs/{run_id}
GET /api/v1/observe/rings/{ring_id}/diff?against=
GET /api/v1/observe/search?q=&scope=
```

所有响应统一为：

```json
{
  "data": {},
  "as_of": "2026-07-23T12:00:00Z",
  "forest_release_id": "fr-24",
  "source": "active_ring",
  "truncated": false
}
```

### 工作项

- 在 application 层建立 ForestScene、TreeScene、SoilScene、RunScene、RingDiff view model。
- API 层只负责参数校验、权限上下文、调用 service 和响应转换。
- 空数据、索引重建、权限拒绝、数据延迟分别使用明确状态，不返回模拟节点。
- search 结果按 Forest、Cognitive、Soil、Run、Ring 分组，并返回 status/ring/created_at。
- 统一分页、时间范围、最大节点数和 truncation 语义。

### 退出条件

- 所有 observe API 可以用临时数据库端到端调用。
- 响应不包含 candidate/quarantined/越权内容。
- 旧 API 不被 observe API 依赖。
- 任何数据不可用场景都有明确 source/status。

## R5：补齐前端观测器 F0-F3

### 目标

完成设计文档定义的四个观察层级，保持纯只读。

### F0：观测壳层

- 保留森林首屏，不出现 CRUD、反馈、强化、发布、回滚等写操作入口。
- 接入真实 observe API 和统一 response envelope。
- 删除硬编码 fallback domain。
- API 不可用时显示“观测延迟”“来源不可验证”“索引重建中”。

### F1：森林与单树

- 森林全景稳定布局，使用固定 seed，树数量变化不导致跳动。
- 单树显示 trunk、branch、leaf、fruit、soil 入口。
- Ring 选择、角色、状态、季节筛选实际改变可见性。
- 详情面板显示 revision、evidence、source、impact Run 和时间线。

### F2：土地与 Run

- 新增 `soil-scene.js`、`run-scene.js`。
- 土壤事件按 observed_at 展示，支持 0.5x/1x/4x 播放和暂停。
- Run 展示 Intent、Router、Context、Skill、ActionResult、Evaluation。
- 输入输出只展示脱敏摘要和 hash。

### F3：Ring 与对比

- 新增 `ring-scene.js`。
- 年轮横截面显示 Ring 0 到最新 sealed Ring。
- 支持两个 Ring 的 diff：added、superseded、deprecated、quarantined、unchanged。
- 可以定位受影响 revision 和 Run，但不提供任何发布或回滚按钮。

### 前端质量要求

- 使用真实或生成的位图环境资产，数据对象仍使用可访问 SVG/Canvas。
- 支持 `prefers-reduced-motion`。
- 所有视觉对象有键盘可达的替代列表。
- 详情面板支持 Escape 关闭、焦点管理和明确面包屑。
- 修复叶片动画累加位移问题，动画只基于固定初始坐标计算。
- 移动端采用森林缩略图 -> 树详情 -> 土地时间线 -> Run 步骤的纵向叙事。

### 退出条件

- `/observe`、`/observe/tree/:id`、`/observe/soil`、`/observe/run/:id`、`/observe/ring/:id` 均可导航。
- 桌面和移动端没有文字遮挡、布局跳动和无法操作的重叠。
- 浏览器自动化检查覆盖首屏、筛选、详情、时间播放、Ring 对比和错误状态。

## R6：测试、可观测性和发布验收

### 必须补齐的测试

```text
tests/infra/test_duckdb_pool.py
tests/infra/duckdb/test_revision_repository.py
tests/infra/duckdb/test_ring_repository.py
tests/application/test_soil_service.py
tests/application/test_run_trace.py
tests/application/test_evaluation.py
tests/application/test_retrieval_service.py
tests/api/test_versioned_endpoints.py
tests/api/test_observe_endpoints.py
tests/jobs/test_outbox_job.py
tests/jobs/test_evaluation_job.py
```

### 必须覆盖的行为

- 确定性 embedding
- DuckDB 并发、rollback、commit failure
- schema 初始化幂等
- Ring 0 migration 幂等
- revision 不可变
- candidate/expired/quarantined/tenant/access 过滤
- 稳定排序和 token budget
- Soil 幂等和 integrity hash
- Run context/reference 完整性
- feedback 不修改权重
- release gate 失败不激活
- activate/rollback 原子性
- Chroma rebuild
- outbox retry、lease、dead-letter
- job 优雅关闭
- observe API 统一 envelope

### 指标

至少实现并验证：

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

## 6. 交付顺序和建议提交边界

建议每个阶段单独提交，避免一次性混合后端、前端和数据迁移：

```text
R0  pool/schema/test baseline
R1  route/DI/job lifecycle
R2  ring/revision/release consistency
R3  retrieval/soil/run/outbox
R4  observe API/view models
R5  frontend F0-F3
R6  full verification/documentation
```

每次提交必须包含：

- 变更说明
- 新增或修改测试
- 运行命令和结果
- 数据迁移影响
- 回滚方式
- 未完成项和已知风险

## 7. 最终 Definition of Done

只有同时满足以下条件，才能标记“返工完成”：

1. 新数据库可从空目录启动，schema 和 Ring 0 migration 幂等。
2. 新 API 已注册，旧 API 仍可用且写入不直接修改 active 权重。
3. sealed Ring 和 revision 不可修改。
4. activate/rollback 是原子操作，失败无半状态。
5. 在线检索只读取 active、有效且授权的 revision。
6. 每个 Run 固定 release、tree/ring、revision 和 context hash。
7. Chroma 丢失后可以从关系表重建。
8. Outbox、Evaluation、Inspection job 有启动、停止、重试和日志。
9. Observe API 覆盖森林、树、土壤、Run、Ring diff 和搜索。
10. 前端四个观察层级可用，并且没有写操作入口。
11. candidate、quarantined、过期和越权内容不会出现在 active 观察视图。
12. 测试、lint、浏览器验收全部通过。
13. 文档记录完成项、未完成项、风险、迁移和回滚方式。

## 8. 暂不返工范围

本轮继续明确不做：

- 自动本体演化
- 跨树自治委托
- PostgreSQL/pgvector 适配器
- 多 worker 分布式调度
- 前端创建、编辑、审批、发布、回滚
- 3D 漫游和 VR
- LLM 自动审批

这些能力必须等 R0-R6 通过后，基于稳定的 revision、Ring、release 和 observe 契约另行设计。

## 9. 推荐验收命令

```bash
ruff check .
python -m pytest -q
pytest -q
python -c "import app; print(sorted(str(r) for r in app.app.url_map.iter_rules()))"
```

前端验收还需要通过浏览器自动化检查：

- 桌面端森林首屏
- 移动端纵向布局
- Tree 详情和筛选
- Soil 时间播放
- Run 复盘
- Ring diff
- 空数据、权限拒绝、索引重建和 reduced-motion 状态
