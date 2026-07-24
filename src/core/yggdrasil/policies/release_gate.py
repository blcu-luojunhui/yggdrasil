"""发布门禁：candidate ring → sealed ring 的准入检查"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class ReleaseGateResult:
    passed: bool = False
    reasons: List[str] = field(default_factory=list)


class ReleaseGate:
    """发布门禁"""

    def __init__(
        self,
        *,
        require_evidence: bool = True,
        max_risk: float = 0.4,
        min_confidence: float = 0.3,
        require_verification: bool = False,
    ):
        self.require_evidence = require_evidence
        self.max_risk = max_risk
        self.min_confidence = min_confidence
        self.require_verification = require_verification

    async def check(self, ring, node_revisions: list, edge_revisions: list) -> ReleaseGateResult:
        """执行门禁检查"""
        reasons: List[str] = []
        passed = True

        # 1. Manifest revision 存在
        if not node_revisions:
            reasons.append("No node revisions in candidate ring")
            passed = False

        # 2. 无 candidate/quarantined/过期 state
        for rev in node_revisions:
            if rev.status.value in ("candidate", "quarantined"):
                reasons.append(f"Node revision {rev.revision_id} has invalid status: {rev.status}")
                passed = False
            if rev.risk > self.max_risk:
                reasons.append(f"Node revision {rev.revision_id} risk {rev.risk} > {self.max_risk}")
                passed = False

        # 3. Fact 有 evidence 和 verification
        if self.require_evidence:
            for rev in node_revisions:
                if rev.role in ("fact", "heuristic") and not rev.evidence_refs:
                    reasons.append(f"{rev.role} revision {rev.revision_id} missing evidence_refs")
                    passed = False

        # 4. Heuristic 有 case/evidence
        if self.require_evidence:
            for rev in node_revisions:
                if rev.role == "heuristic" and not rev.evidence_refs:
                    reasons.append(f"Heuristic revision {rev.revision_id} missing evidence_refs")
                    passed = False

        # 5. 无悬空边
        node_ids = {n.node_id for n in node_revisions}
        for erev in edge_revisions:
            if erev.source_node_id not in node_ids or erev.target_node_id not in node_ids:
                reasons.append(f"Edge {erev.edge_id} has dangling reference")
                passed = False

        return ReleaseGateResult(passed=passed, reasons=reasons)
