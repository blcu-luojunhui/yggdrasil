# Yggdrasil — Agent 认知森林引擎

> 不是单棵无限增长的知识树，而是一套认知森林运行协议：土壤保存共同现实，领域树形成认知，森林组织多树协作，四季驱动知识演化，年轮固化稳定版本。

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 是什么

Yggdrasil 是一套面向长期运行 Agent 的**认知管理系统**。它将可执行能力（Skill）、领域知识（Knowledge）和经验记忆（Memory）统一为有机的认知原子网络，围绕**可检索、可演化、可验证、可回滚**四个目标构建。

与普通 RAG 的关键区别：Yggdrasil 不只是"检索相关文档塞进 prompt"，而是维护一个**版本化的认知图谱**——每条知识有来源，每次决策有上下文，每轮成长可比较，每次错误可隔离，每个版本可回滚。

## 隐喻与工程对象

| 隐喻 | 工程对象 | 职责 |
|---|---|---|
| 土壤 Soil | 事件、证据、身份、权限、时钟 | 保存可追溯的共同现实 |
| 森林 Forest | 树目录、路由、组合版本、跨树协议 | 发现、隔离、协作和统一治理 |
| 树 Tree | 一个限界上下文 | 独立组织某领域的技能、知识和记忆 |
| 枝 Branch | Skill / Capacity | 对外部环境执行动作 |
| 叶 Leaf | Schema、Fact、State、Heuristic | 为技能和推理提供上下文 |
| 果 Fruit | 执行结果 | 作为事件重新进入土壤 |
| 四季 Season | 四类演化作业 | 摄入、验证、归纳、冻结 |
| 年轮 Ring | 不可变认知版本 | 发布、复现、比较、审计和回滚 |

## 核心设计原则

1. **事实与解释分离**：土壤记录发生了什么，树记录某领域如何理解它
2. **统一外壳、类型化载荷**：共享身份、版本和治理协议，但 Skill / Knowledge / Memory 使用不同载荷和约束
3. **反思只生成候选**：LLM 不得凭反思直接发布事实或核心规则，必须经证据验证和审批
4. **版本不可变**：已封存年轮不原地修改；错误通过隔离、回滚和新年轮修复
5. **评价驱动强化**：执行成功 ≠ 认知正确，权重变化必须基于可归因评价
6. **先可控再自治**：MVP 先实现结构化检索、证据和版本，再逐步开放自动演化

## 架构总览

```
控制面：Forest Registry / Tree Manifest / Ring Manager / Season Orchestrator / Approval
数据面：Soil Events → Retrieval Engine → Agent Runtime → Evaluation → Evolution
```

```
环境产生观察
  → 事件与证据进入土壤
  → 森林路由到有权吸收的树
  → 树在春季形成候选认知
  → 夏季通过任务和沙盒验证
  → 秋季归纳、冲突处理和修剪
  → 冬季回归、冻结并发布年轮
  → Agent 检索版本化认知子图并执行 Skill
  → 结果、轨迹与评价作为果实重新落入土壤
```

### 模块边界

| 模块 | 职责 |
|---|---|
| Soil Service | 接收事件、观察、证据和评价，维护不可变追加日志 |
| Tree Registry | 管理树、领域、本体、公开接口、所有者和权限 |
| Cognitive Store | 管理节点、边、修订及年轮视图 |
| Retrieval Engine | 两级路由、混合召回、图扩展、重排和上下文预算 |
| Agent Runtime | 执行 Run、调用 Skill、记录引用和结果 |
| Evaluation Service | 技术成功、任务成功、质量、风险和归因评估 |
| Evolution Engine | 执行四季作业和候选知识晋升 |
| Ring Manager | 冻结、验证、发布、组合、隔离和回滚年轮 |

## 快速开始

```bash
git clone git@github.com:blcu-luojunhui/yggdrasil.git
cd yggdrasil

pip install -r requirements.txt

cp .env.example .env
# 编辑 .env 配置 LLM API Key

hypercorn app:app -c config.toml
```

## 技术栈

| 层 | 组件 | 说明 |
|---|---|---|
| Web 框架 | Quart + Hypercorn | Async ASGI |
| 关系存储 | PostgreSQL（MVP）/ DuckDB（开发） | 节点、边、修订、年轮、权限 |
| 向量检索 | pgvector（MVP）/ ChromaDB（开发） | ANN 搜索，与关系存储同库 |
| 全文检索 | PostgreSQL FTS | 关键词与过滤 |
| 对象存储 | MinIO / S3 | 大体积证据和执行产物 |
| 消息队列 | PostgreSQL Outbox → 消息队列 | 土壤事件流和异步评价 |
| DI | dependency-injector | JSR-330 风格 |
| 配置 | pydantic-settings | 环境变量前缀 `YGGDRASIL_` |
| 可观测 | OpenTelemetry + prometheus-client | 全链路追踪与指标 |
| Python | >= 3.11, asyncio | — |

## API 速览

```text
# 土壤
POST   /v1/soil/events              # 写入事件
GET    /v1/soil/streams/{stream}     # 读取事件流

# 树与认知原子
POST   /v1/trees                    # 注册领域树
POST   /v1/trees/{id}/nodes         # 创建认知节点
POST   /v1/trees/{id}/retrieve      # 混合检索

# 四季与年轮
POST   /v1/trees/{id}/seasons/spring/start
POST   /v1/rings/{id}/seal          # 封存年轮
POST   /v1/rings/{id}/activate      # 激活年轮
POST   /v1/trees/{id}/rollback      # 回滚

# 森林
POST   /v1/forest/route             # 路由到候选树
POST   /v1/forest/releases          # 创建组合版本
```

## 演进路线

### Phase 0：基线与领域选择（2 周）
选择首个真实领域，建立任务集和普通 RAG 基线，明确限界上下文和评估指标。

### Phase 1：种子系统（4–6 周）
结构化版本化认知上下文运行。Soil 事件、CognitiveNode/Edge/Revision、一棵领域树、混合检索、Run 引用记录、人工审批知识晋升、Ring 1 的冻结发布和回滚。

### Phase 2：生长系统（6–8 周）
从 Run 中稳定积累候选经验。Evaluation Service、case 自动挂载、春夏作业、沙盒 overlay、两级森林路由、Forest Release。

### Phase 3：治理与免疫（8–12 周）
规模化维护和污染控制。秋冬作业、去重聚类、类型化污染传播、年轮发布门禁、自动隔离和局部回滚、完整审计。

### Phase 4：森林生态（持续）
多 Agent、多团队、多租户的认知资产协作。树接口市场、跨租户隔离、多 Agent 写入仲裁、认知资产版本分发。

## 架构分层

```
api (REST HTTP 接口，轻薄层)
  → jobs (后台任务：巡检、四季轮转)
    → core (核心能力：节点/边/检索/进化)
      → infra (基础设施：数据库、向量存储、日志)
```

跨层调用单向（api → jobs → core → infra），反向依赖视为设计缺陷。

## 相关文档

- [Agent 接入指南](docs/agent-integration-guide.md) — 如何让 Agent 把 Yggdrasil 当作认知大脑，含完整 Python 示例
- [实施方案](Yggdrasil-implementation-plan.md) — 完整架构设计、数据模型、API 草案、风险应对
- [开发规范](Yggdrasil-development-spec.md) — 编码规范和开发约定
- [前端观测器设计](Yggdrasil-frontend-observation-design.md) — 认知森林可视化

## License

MIT License