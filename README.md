# Yggdrasil — 世界树认知引擎

> 一棵活的、会呼吸的认知之树，为 Agent 提供可自我迭代进化的大脑。

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 愿景

Yggdrasil 将 Agent 的技能（Skill）、知识（Knowledge）与记忆（Memory）统一为树上的有机节点——**认知原子**。树随每一次任务执行而生长、强化、修剪乃至涅槃重生，最终成为一个持续进化的数字大脑。

## 核心特性

- **统一认知原子模型**：Skill/Knowledge/Memory 统一存储，通过 role 区分功能
- **有向有权关联网络**：节点之间通过显式边连接，形成可解释的因果/证据网络
- **领域分层骨架**：按需分裂，冷启动清晰，数据驱动扩展
- **子树检索（光合作用）**：只加载相关认知，控制 token 预算
- **沙盒分支**：安全探索，有害变异不影响主干
- **污染隔离与自愈**：健康度机制，错误认知自动隔离回滚
- **认知四季节律**：春生/夏长/秋收/冬藏，完整自进化闭环
- **REST HTTP API**：独立服务，任何 Agent 框架都可接入

## 快速开始

```bash
# 克隆
git clone git@github.com:blcu-luojunhui/yggdrasil.git
cd yggdrasil

# 安装依赖
pip install -r requirements.txt

# 配置环境
cp .env.example .env
# 编辑 .env 配置 LLM API Key（可选，不配置则使用 mock embedding）

# 启动服务（DuckDB + ChromaDB 自动初始化，无需外部数据库）
hypercorn app:app -c config.toml
```

## 技术栈

- **Web 框架**: Quart（async Flask 等价，基于 Hypercorn ASGI）
- **向量存储**: ChromaDB（进程内 ANN 搜索）
- **关系存储**: DuckDB（进程内，零依赖）
- **DI**: dependency-injector
- **配置**: pydantic-settings
- **Python**: >=3.11, asyncio

## 架构分层

```
api (REST HTTP 接口) → core (Yggdrasil 引擎) → infra (DuckDB、ChromaDB、日志)
```

## 演进路线

**Phase 1：种子** — 统一节点模型、领域骨架、基础子树检索
**Phase 2：生长** — 动态强度更新、沙盒分支、经验自动挂载
**Phase 3：免疫与四季** — 污染传播与自愈、巡检服务、四季节律
**Phase 4：生态** — 多 Agent 子树共享与权限隔离

## License

MIT License