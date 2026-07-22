from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class CognitiveRole(str, Enum):
    """认知节点角色"""
    CAPACITY = "capacity"  # Skill - 可执行能力
    SCHEMA = "schema"      # Knowledge - 概念框架、数据模型
    HEURISTIC = "heuristic"  # Knowledge - 启发式规则、经验法则
    CASE = "case"          # Memory - 具体案例或历史情景
    FACT = "fact"          # Knowledge - 可验证的客观陈述
    STATE = "state"        # Knowledge - 当前世界状态快照


class RelationType(str, Enum):
    """边关系类型"""
    ENABLES = "enables"        # 知识使能技能: schema → capacity
    TRIGGERS = "triggers"      # 状态/案例触发技能执行: state/case → capacity
    EVIDENCES = "evidences"    # 案例为事实/规则提供证据: case → fact/heuristic
    CONTRADICTS = "contradicts"  # 矛盾关系
    STRENGTHENS = "strengthens"  # 成功执行强化关联
    WEAKENS = "weakens"        # 失败执行削弱关联


class Season(str, Enum):
    """认知四季"""
    SPRING = "spring"    # 春 · 生 - 探索与播种
    SUMMER = "summer"    # 夏 · 长 - 强化与茂盛
    AUTUMN = "autumn"    # 秋 · 收 - 反思与修剪
    WINTER = "winter"    # 冬 · 藏 - 休眠与重组


class Domain(BaseModel):
    """领域，分层骨架"""
    id: Optional[int] = None
    parent_id: Optional[int] = None
    domain_name: str
    full_path: str
    depth: int = 1
    season: Season = Season.SPRING
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CognitiveNode(BaseModel):
    """认知原子节点"""
    id: Optional[int] = None
    domain_id: int
    role: CognitiveRole
    node_name: str
    description: Optional[str] = None
    content: Optional[str] = None
    embedding: Optional[bytes] = None
    strength: float = Field(default=0.5, ge=0.0, le=1.0, description="强度 [0,1]")
    health: float = Field(default=1.0, ge=0.0, le=1.0, description="健康度 [0,1]")
    is_isolated: bool = False
    last_used_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CognitiveEdge(BaseModel):
    """认知有向边"""
    id: Optional[int] = None
    from_node_id: str
    to_node_id: str
    relation_type: RelationType
    strength: float = Field(default=0.5, ge=0.0, le=1.0, description="边强度 [0,1]")
    source: Optional[str] = None  # 强度来源: execution/reflection/inspection
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SubtreeContext(BaseModel):
    """检索结果：认知子树"""
    domain: Domain
    nodes: List[CognitiveNode]
    edges: List[CognitiveEdge]
    total_tokens: int
    message: str = ""

    def to_markdown(self) -> str:
        """转换为 Markdown 格式供 LLM 使用"""
        lines = [f"# 认知上下文: {self.domain.full_path}\n"]

        if not self.nodes:
            lines.append("*无相关认知节点*\n")
            return "\n".join(lines)

        # 按角色分组
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
                    header = f"- **{node.node_name}** (强度={node.strength:.2f})"
                    if node.description:
                        header += f": {node.description}"
                    lines.append(header)
                    if node.content and node.content.strip():
                        lines.append(f"  \n  {node.content.strip()}\n  ")

        # 关系提示
        if self.edges:
            lines.append("\n## 关联关系\n")
            relation_summary: dict[str, int] = {}
            for edge in self.edges:
                relation_summary[edge.relation_type.value] = relation_summary.get(edge.relation_type.value, 0) + 1
            for rel, count in relation_summary.items():
                lines.append(f"- {rel}: {count} 条")

        return "\n".join(lines)


class StrengthUpdate(BaseModel):
    """强度更新请求"""
    node_id: Optional[int] = None
    edge_id: Optional[int] = None
    delta: float  # 正为 strengthen，负为 weaken


class ChangeLogEntry(BaseModel):
    """变更日志"""
    id: Optional[int] = None
    node_id: Optional[int] = None
    edge_id: Optional[int] = None
    operation: str
    old_values: Optional[dict] = None
    new_values: Optional[dict] = None
    reason: Optional[str] = None
    trace_id: Optional[str] = None
    created_at: Optional[datetime] = None


__all__ = [
    "CognitiveRole",
    "RelationType",
    "Season",
    "Domain",
    "CognitiveNode",
    "CognitiveEdge",
    "SubtreeContext",
    "StrengthUpdate",
    "ChangeLogEntry",
]
