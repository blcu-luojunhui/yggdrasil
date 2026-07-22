from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class CognitiveRole(str, Enum):
    """认知节点角色"""
    CAPACITY = "capacity"      # Skill - 可执行能力
    SCHEMA = "schema"          # Knowledge - 概念框架、数据模型
    HEURISTIC = "heuristic"    # Knowledge - 启发式规则、经验法则
    CASE = "case"              # Memory - 具体案例或历史情景
    FACT = "fact"              # Knowledge - 可验证的客观陈述
    STATE = "state"            # Knowledge - 当前世界状态快照


class RelationType(str, Enum):
    """边关系类型（8 种）"""
    ENABLES = "enables"            # 知识使能技能: schema → capacity
    TRIGGERS = "triggers"          # 状态/案例触发技能执行: state/case → capacity
    EVIDENCES = "evidences"        # 案例为事实/规则提供证据: case → fact/heuristic
    SPECIALIZES = "specializes"    # 特化/细化: 通用知识 → 具体应用
    CONTRADICTS = "contradicts"    # 矛盾关系: 新证据与旧知识冲突
    CAUSES = "causes"              # 因果关系: 事件 A → 事件 B
    STRENGTHENS = "strengthens"    # 成功执行强化关联: execution → any
    WEAKENS = "weakens"            # 失败执行削弱关联: execution → any


class Season(str, Enum):
    """认知四季"""
    SPRING = "spring"    # 春 · 生 - 探索与播种，精力最充沛
    SUMMER = "summer"    # 夏 · 长 - 强化与茂盛，成长加速
    AUTUMN = "autumn"    # 秋 · 收 - 反思与修剪，归纳提炼
    WINTER = "winter"    # 冬 · 藏 - 休眠与重组，衰减保护


class Domain(BaseModel):
    """领域，分层骨架"""
    id: Optional[int] = None
    parent_id: Optional[int] = None
    domain_name: str
    full_path: str
    depth: int = 1
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CognitiveNode(BaseModel):
    """认知原子节点"""
    id: Optional[str] = None                            # CHAR(36) UUID v7
    role: CognitiveRole
    domain_id: int
    domain_path: str = ""                               # 物化路径，如 /database/skills/
    title: str = ""
    content: Optional[str] = None                       # 结构化 Markdown
    strength: float = Field(default=0.5, ge=0.0, le=1.0)
    health: float = Field(default=1.0, ge=0.0, le=1.0)
    season: Season = Season.SPRING                      # 节点级四季
    embedding_id: Optional[str] = None                  # 外部向量库 ID
    tenant_id: str = "default"                          # 租户/视野隔离
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_accessed_at: Optional[datetime] = None

    @property
    def is_isolated(self) -> bool:
        """health <= 0 视为隔离"""
        return self.health <= 0.0


class CognitiveEdge(BaseModel):
    """认知有向边"""
    id: Optional[str] = None                            # CHAR(36) UUID v7
    source_id: str                                      # → cog_node.id
    target_id: str                                      # → cog_node.id
    relation: RelationType
    strength: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_count: int = 1                             # 支撑经验次数
    last_activated: Optional[datetime] = None
    source_origin: Optional[str] = None                 # 来源：run_id / manual
    created_at: Optional[datetime] = None


class SubtreeContext(BaseModel):
    """检索结果：认知子树"""
    domain: Optional[Domain] = None
    nodes: List[CognitiveNode] = []
    edges: List[CognitiveEdge] = []
    total_tokens: int = 0
    message: str = ""

    def to_markdown(self) -> str:
        """转换为 Markdown 格式供 LLM 使用"""
        lines = ["# 认知上下文\n"]

        if not self.nodes:
            lines.append("*无相关认知节点*\n")
            return "\n".join(lines)

        by_role: dict[CognitiveRole, List[CognitiveNode]] = {}
        for node in self.nodes:
            by_role.setdefault(node.role, []).append(node)

        role_names = {
            CognitiveRole.CAPACITY: "## 可用技能 (Capacity)",
            CognitiveRole.SCHEMA: "## 概念框架 (Schema)",
            CognitiveRole.HEURISTIC: "## 经验法则 (Heuristic)",
            CognitiveRole.CASE: "## 历史案例 (Case)",
            CognitiveRole.FACT: "## 客观事实 (Fact)",
            CognitiveRole.STATE: "## 当前状态 (State)",
        }

        for role, name in role_names.items():
            if role in by_role:
                lines.append(f"\n{name}\n")
                for node in sorted(by_role[role], key=lambda n: n.strength, reverse=True):
                    header = f"- **{node.title}** (强度={node.strength:.2f}, 季节={node.season.value})"
                    if node.content:
                        header += f"\n  {node.content.strip()}"
                    lines.append(header)

        if self.edges:
            lines.append("\n## 关联关系\n")
            relation_summary: dict[str, int] = {}
            for edge in self.edges:
                relation_summary[edge.relation.value] = relation_summary.get(edge.relation.value, 0) + 1
            for rel, count in relation_summary.items():
                lines.append(f"- {rel}: {count} 条")

        return "\n".join(lines)


class StrengthUpdate(BaseModel):
    """强度更新请求"""
    node_id: Optional[str] = None
    edge_id: Optional[str] = None
    delta: float


class TreeLogEntry(BaseModel):
    """变更日志条目"""
    id: Optional[int] = None
    operation: str                                      # create_node / update_node / delete_node / ...
    entity_type: str                                    # 'node' / 'edge'
    entity_id: str
    changes: Optional[dict] = None
    operator: Optional[str] = None
    created_at: Optional[datetime] = None


# ── Phase 3-4 扩展模型 ──

class Branch(BaseModel):
    """分支表"""
    id: Optional[str] = None
    name: str
    parent_branch_id: Optional[str] = None
    status: str = "active"                              # active / archived / isolated
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None


class CogNodeVersion(BaseModel):
    """节点版本表"""
    id: Optional[str] = None
    node_id: str
    branch_id: str
    role: CognitiveRole
    content: Optional[str] = None
    strength: float = 0.5
    health: float = 1.0
    season: Season = Season.SPRING
    previous_version_id: Optional[str] = None
    created_at: Optional[datetime] = None


class CogEdgeVersion(BaseModel):
    """边版本表"""
    id: Optional[str] = None
    edge_id: str
    branch_id: str
    source_id: str
    target_id: str
    relation: RelationType
    strength: float = 0.5
    previous_version_id: Optional[str] = None
    created_at: Optional[datetime] = None


class SeasonCycle(BaseModel):
    """季节周期配置"""
    id: Optional[int] = None
    domain_path: str = "/"                              # 适用的子树根路径
    current_season: Season = Season.SPRING
    cycle_anchor: Optional[datetime] = None             # 周期起点
    cycle_duration_hours: int = 168                     # 完整四季周期长度（默认1周）
    updated_at: Optional[datetime] = None


class Cooccurrence(BaseModel):
    """共现统计"""
    node_a_id: str
    node_b_id: str
    count: int = 0
    last_cooccur: Optional[datetime] = None


__all__ = [
    "CognitiveRole",
    "RelationType",
    "Season",
    "Domain",
    "CognitiveNode",
    "CognitiveEdge",
    "SubtreeContext",
    "StrengthUpdate",
    "TreeLogEntry",
    "Branch",
    "CogNodeVersion",
    "CogEdgeVersion",
    "SeasonCycle",
    "Cooccurrence",
]