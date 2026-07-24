# Yggdrasil 前端观测器设计

## 1. 产品定位

前端不是管理后台，也不是知识编辑器，而是一台**认知森林观测器**：

> 让用户看见森林的整体生命状态，再沿着土地、树木、树干、枝叶、果实和年轮，追溯一次认知是如何形成、被使用、被验证和被发布的。

本阶段只读。所有 UI 操作都只能改变观察范围、时间、筛选条件或详情展开状态，不得改变任何树、节点、边、事件、Run、Evaluation 或 Ring。

### 1.1 明确允许的交互

- 平移、缩放、旋转观察视角；
- 点击森林中的树、土地层、树枝、叶片、果实和年轮；
- 搜索并定位认知节点、Run、证据或树；
- 按树、角色、健康度、季节、状态、时间范围筛选；
- 在历史 Ring 之间切换和对比；
- 播放一段 Run 或季节演化时间线；
- 打开只读详情、来源、证据和影响范围。

### 1.2 明确禁止的交互

页面不得出现：新建、编辑、删除、反馈、强化、减弱、Fork、合并、发布、激活、回滚、审批、执行 Skill、上传证据和修改权限入口。

不使用“管理”“配置”“操作”“提交”等按钮文案。只使用“查看”“展开”“定位”“播放”“对比”“返回森林”等观察动作。

## 2. 视觉叙事

### 2.1 从宏观到微观

```text
森林全景
  -> 某棵树的冠层与树干
    -> 某条枝上的 Skill / Knowledge / Memory
      -> 某片叶子的 revision、证据和状态
        -> 土地中的事件、Run 和 Evaluation
          -> 年轮时间线与可复现版本
```

默认首屏必须是森林，而不是表格、卡片网格或空状态。第一眼应看到树群、地表和季节光线；第二眼才能读到数量、健康度和活动状态。

### 2.2 视觉语汇

| 概念 | 视觉表达 | 信息含义 |
|---|---|---|
| Forest | 宽幅森林全景 | 多棵 Tree 的协作和整体健康 |
| Soil | 屏幕底部横向土壤剖面 | SoilEvent、Evidence、身份和时钟 |
| Tree | 有树冠、树干、根系的独立生命体 | bounded context / Tree |
| Trunk | 树干内的纵向光脉或年轮 | Agent Run 决策轨迹和稳定主干 |
| Branch | 从树干分叉的粗细枝条 | Skill、Knowledge、Memory 关系 |
| Leaf | 可发光或轻微摆动的叶片 | active revision；亮度表示可用性 |
| Fruit | 枝端果实 | ActionResult、Evaluation 或可验证产出 |
| Ring | 树干横截面的年轮 | Ring 版本、发布和回滚历史 |
| Firefly / particle | 极少量流动粒子 | Soil event 或跨树引用，不表示装饰噪声 |
| Fog | 低对比、稀疏的雾 | 未确认、低置信或不可见内容；不能遮盖主要信息 |

避免把每个节点画成独立卡片。卡片只用于右侧详情、证据列表和时间线条目；森林和树的主体使用连续空间。

### 2.3 色彩

采用多色但克制的自然色系，避免整页单一绿色或深蓝：

```text
背景夜色      #101820 / #17242b
土壤深层      #2b211d
树干          #5a3f2e
叶片健康      #6fa36b
叶片活跃      #a8cf7a
事实/证据     #d9e4d0
规则/启发     #e8b86a
案例/记忆     #b899d6
Skill         #77b7c9
冲突/污染     #d56b5d
年轮/时间     #d4a35f
文字主色      #edf2e8
文字弱色      #9aa99d
```

健康状态优先使用亮度、呼吸频率和纹理辅助表达，不能只依靠颜色，保证低色觉用户也能辨识。

## 3. 信息架构

前端只保留四个观察层级，不做传统后台侧边栏导航：

```text
/observe                 森林全景
/observe/tree/:treeId    单棵树
/observe/soil            土地与事件流
/observe/run/:runId      单次 Run 复盘
```

右上角提供全局搜索、时间范围、Ring 选择和只读筛选。左上角显示当前面包屑：`森林 / 数据库诊断 / Ring 4 / Run ...`。

## 4. 页面一：森林全景

### 4.1 首屏构图

```text
┌──────────────────────────────────────────────────────────┐
│ YGGDRASIL   森林 / Ring 24    搜索  时间  观测筛选       │
├──────────────────────────────────────────────────────────┤
│                                                          │
│        树冠 A                 树冠 B          远景幼树     │
│      /\  ·  /\             /\  ·  /\                  │
│        \  |  /                 \  |                      │
│          树干                 树干                         │
│──────────────────────地表────────────────────────────────│
│  Soil events  ● ● ●       检索/运行流  ────>              │
├──────────────────────────────────────────────────────────┤
│ 当前森林状态  3 Trees  2 active rings  98.2% 健康  ...   │
└──────────────────────────────────────────────────────────┘
```

顶部只显示身份、当前 Forest Release、全局搜索和筛选。底部状态条显示聚合指标，不抢占森林主体。

### 4.2 树的视觉编码

- 树的高度：Tree 内 active revision 数量的对数映射，避免大树吞没小树；
- 树冠密度：active revision 的数量和角色分布；
- 树冠亮度：tree health；
- 枝条颜色：能力、知识、记忆三类角色；
- 枝条断裂或灰化：deprecated、quarantined 或缺证据内容；
- 根部光点：最近 SoilEvent 数量；
- 树间细线：公开 imports、delegates_to 或共享证据，不画所有内部边。

树不能因为数量变化突然跳动。使用固定布局、稳定 seed 和 300-600ms 的缓动动画。

### 4.3 森林全景详情

点击树后，从右侧滑出只读面板：

```text
DATABASE DIAGNOSTICS
数据库诊断 · owner: platform
当前 Ring       Ring 4 · sealed · healthy
认知规模        128 revisions / 34 skills / 67 facts
最近生长        12 个 Soil events · 3 个 Runs
健康            96.4%   新鲜度 91.2%   风险 0.08

[查看树] [对比上一 Ring]
```

按钮仅用于导航和对比，不产生写操作。

## 5. 页面二：单棵树

### 5.1 画面

进入单棵树后，镜头靠近树冠，地表仍保留 15-20% 高度，用户始终知道这棵树属于哪片森林。

```text
                 树冠 / Knowledge
              · 叶 叶 叶 叶 ·
             /      |       \       Skill 枝
          枝───────树干───────枝
             \    |    /
                根系 / Memory
──────────────────地表──────────────────
     Soil events       Ring timeline       Run traces
```

### 5.2 观察控件

- `角色`：Capacity / Schema / Fact / Heuristic / Case / State；
- `状态`：Active / Candidate / Deprecated / Quarantined；
- `关系`：Enables / Evidences / Supports / Contradicts / Supersedes；
- `季节`：Spring / Summer / Autumn / Winter；
- `版本`：当前 Ring、上一 Ring、任意已封存 Ring。

筛选只改变可见性。筛选器旁显示当前结果数量和“已隐藏内容”数量。

### 5.3 节点详情

点击叶片、枝条或果实后展示：

- 标题、角色、Tree、domain path；
- 当前 revision、Ring、status；
- utility、confidence、freshness、risk；
- valid time 和最后使用时间；
- evidence refs 和来源类型；
- 上游/下游一跳关系；
- 被哪些 Run 引用；
- revision 时间线；
- “在森林中定位”“查看来源”“查看受影响 Run”。

详情必须先显示状态和证据，再显示正文，避免把长文本误认为事实。

## 6. 页面三：土地剖面

### 6.1 目的

土地是共同现实的观察层。它不展示“知识树长了多少”，而展示“哪些事件进入系统、来自哪里、如何被树吸收”。

### 6.2 构图

页面底部或独立视图展示横向土壤剖面：

```text
空气层   用户请求 · Agent Decision · Tool Action
──────────────────────────────────────────────
表土层   Observation  Evidence  Evaluation
══════════════════════════════════════════════
公共层   tenant / identity / shared facts
──────────────────────────────────────────────
基岩层   immutable events · audit · integrity hash
```

事件按照 observed_at 从左到右形成时间流。不同事件类型用形状区分：圆点表示 observation，六边形表示 evidence，菱形表示 decision，果实状节点表示 evaluation。

点击事件显示：`event_id、source、trust_level、observed_at、valid time、integrity hash、correlation/causation、被哪些 Tree 吸收`。

### 6.3 时间播放

提供时间轴滑块和播放按钮，播放时只推进观察窗口，不修改数据。播放速度提供 0.5x、1x、4x；当前时间点的 Soil event、Run 和 Tree 变化同步高亮。

## 7. 页面四：Run 复盘

### 7.1 叙事目标

用户要看到的是“这次回答为什么这样做”，而不是一段无法验证的模型思维文本。

### 7.2 序列图

```text
Intent
  ↓
Forest Router ──> Tree A / Ring 4
  ↓
Retrieved context ──> revisions + evidence
  ↓
Selected Skill
  ↓
ActionResult / Observation
  ↓
Evaluation
```

每个步骤都显示时间、耗时、输入/输出 hash 和关联 revision。敏感 payload 只显示脱敏摘要。

右侧显示本次 Run 在森林中的路径：从哪棵树、哪一条枝、哪几片叶子到哪个果实。被引用的叶片在树视图中同步发光。

## 8. 页面五：年轮与 Ring 对比

### 8.1 年轮视图

点击树干进入横截面视图。每一圈代表一个 sealed Ring，外圈为最新版本，中心为 Ring 0。

- 环宽：该 Ring 的变更规模；
- 环色：质量和健康状态；
- 缺口：被 quarantine 或 superseded 的版本；
- 环上标记：soil checkpoint、发布原因、评价报告；
- 点击两圈进入差异视图。

### 8.2 Ring 对比

对比页分三列：

```text
Ring 3                    变化                    Ring 4
42 active revisions       + 8 / - 2              48 active revisions
confidence 0.82           + 0.04                 confidence 0.86
P95 180 ms                - 12 ms                P95 168 ms
```

变化类型只读标记为 `added / superseded / deprecated / quarantined / unchanged`。不得提供合并或发布按钮。

## 9. 全局搜索与定位

搜索框同时查找：Tree、revision、节点标题、event、evidence、Run 和 Ring。结果按上下文分组，不做单一平面列表：

```text
森林        2 棵树
认知节点    18 个 revision
土地事件    7 条 event
运行轨迹    3 个 Run
年轮        4 个 Ring
```

点击结果后把镜头定位到对应视觉对象，并在详情面板中打开证据。搜索结果必须显示 `status/ring/created_at`，避免把历史版本误认为当前事实。

## 10. 只读数据契约

前端不应拼接旧的硬编码 domain 列表。建议提供以下只读 API：

```text
GET /api/v1/observe/forest?release_id=
GET /api/v1/observe/trees/{tree_id}?ring_id=
GET /api/v1/observe/trees/{tree_id}/graph?ring_id=&role=&status=
GET /api/v1/observe/soil/events?after=&before=&event_type=
GET /api/v1/observe/runs/{run_id}
GET /api/v1/observe/rings/{ring_id}/diff?against=
GET /api/v1/observe/search?q=&scope=
```

所有响应只读，统一返回：

```json
{
  "data": {},
  "as_of": "2026-07-23T12:00:00Z",
  "forest_release_id": "fr-24",
  "source": "active_ring",
  "truncated": false
}
```

当数据不可用时显示“观测延迟”“索引重建中”或“来源不可验证”，不得用模拟数据伪装成真实森林状态。

### 10.1 前端 View Model

后端原始模型与画面模型分离，前端只消费：

```text
ForestScene
  release, as_of, trees[], soil_summary, active_run_count
TreeScene
  tree, canopy, trunk, branches[], leaves[], fruits[], metrics
SoilScene
  layers[], events[], checkpoints[], subscriptions
RunScene
  steps[], references[], path[], evaluation
RingDiff
  base_ring, target_ring, changes[], quality_delta
```

## 11. 技术实现建议

### 11.1 第一版

保留 `frontend/index.html` 的单页部署方式，但将内嵌脚本拆为：

```text
frontend/
  index.html
  styles/observatory.css
  app/main.js
  app/api.js
  app/state.js
  views/forest-scene.js
  views/tree-scene.js
  views/soil-scene.js
  views/run-scene.js
  views/ring-scene.js
```

第一版可用 SVG/Canvas 绘制结构化森林：SVG 适合点击、标签和无障碍；Canvas 适合大量叶片和粒子。建议森林布局用 SVG，微粒和轻微呼吸动画用 Canvas overlay。

不要一开始引入 Three.js 或图数据库。只有当需要真正三维穿行、数据规模超过 SVG 可控范围，并通过截图和像素检查确认交互价值后再引入 Three.js。

### 11.2 视觉资产

森林背景和土壤纹理使用真实或生成的位图资产，作为环境层；树、枝、叶、年轮等数据对象使用可访问的 SVG/Canvas 几何层叠加。背景不能过暗、过度模糊或成为信息主体，用户仍需清楚识别树和事件。

### 11.3 动画规则

- 默认动画只表达状态变化，不做持续炫技；
- 树冠呼吸周期 6-10 秒；
- Soil event 粒子沿路径移动 1.2-2 秒；
- Ring 切换使用镜头推进和 crossfade，时长 400-700ms；
- 支持 `prefers-reduced-motion`，关闭粒子和自动播放；
- 动画不得改变布局尺寸或遮挡详情文字。

## 12. 响应式和可访问性

桌面端优先呈现全景；移动端改为纵向叙事：森林缩略图 -> 树详情 -> 土地时间线 -> Run 步骤。

所有视觉对象必须有键盘可达的替代列表：

- 森林对象列表：Tree 名称、健康度、active Ring；
- 树对象列表：revision 标题、角色、状态、证据数；
- 土地对象列表：event 类型、时间、来源；
- Run 对象列表：步骤、状态、耗时；
- 年轮列表：sequence、状态、质量指标。

颜色之外使用图标、纹理、边框和文字状态。详情面板提供 `Esc` 关闭、焦点陷阱和明确的面包屑。

## 13. 实施里程碑

### F0：观测壳层

- 移除现有“新建节点、领域、沙盒、反馈”入口；
- 建立只读路由、全局状态和 API mock adapter；
- 首屏完成森林背景、树群、地表和状态条；
- 无后端数据时显示明确的观测状态，不创建假节点。

### F1：森林与单树

- 接入 `ForestScene` 和 `TreeScene`；
- 支持树、叶片、枝条点击和详情面板；
- 支持 Ring 选择和角色/状态筛选；
- 完成桌面和移动端布局。

### F2：土地与 Run

- 接入 Soil event 时间流；
- 接入 Run 路径和引用高亮；
- 支持只读时间播放和暂停；
- 脱敏显示输入输出摘要。

### F3：年轮与对比

- 实现树干横截面 Ring 视图；
- 实现 Ring diff；
- 支持定位被 quarantine 的 revision 和受影响 Run；
- 补齐键盘、减少动画和错误状态。

## 14. 验收标准

1. 首屏是森林观测画面，不是 CRUD 面板。
2. 页面不存在任何写操作入口。
3. 用户可以从森林进入 Tree、从 Tree 进入 revision、从 revision 进入 evidence 和 Run。
4. 用户可以在至少两个 Ring 之间切换和比较，且历史版本不会冒充当前版本。
5. Soil event、Run、Evaluation 和 Tree 的时间顺序可视化一致。
6. candidate、quarantined、过期和越权内容不会出现在 active 视图。
7. 数据延迟、索引重建、权限拒绝和空数据都有明确状态。
8. 桌面和移动端没有文字遮挡、布局跳动或不可操作的重叠。
9. `prefers-reduced-motion` 和键盘导航可用。
10. 视觉层有真实/生成的环境位图，数据对象仍清晰可辨。

## 15. 暂不做

暂不实现：前端创建或编辑认知、树之间拖拽嫁接、手动调整强度、审批候选、运行 Skill、发布 Ring、回滚 Ring、实时协作光标、3D 漫游和沉浸式 VR。

这套前端首先要证明的是：用户能否在富有画面感的森林中准确回答“现在有哪些树、这棵树为何健康或衰弱、这条知识来自哪里、某次 Run 使用了什么、Ring 之间发生了什么变化”。
