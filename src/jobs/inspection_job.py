import asyncio
import logging
from datetime import datetime, timedelta

from src.core.config import YggdrasilConfig
from src.core.yggdrasil.models import Season
from src.core.yggdrasil.store import YggdrasilStore
from src.jobs import SeasonManager
from src.infra.observability import LogService, AlertService, MetricsCollector

logger = logging.getLogger(__name__)


class InspectionJob:
    """后台巡检任务 - 健康检查、季节轮转、冬季衰减、秋季归纳"""

    def __init__(
        self,
        store: YggdrasilStore,
        season_manager: SeasonManager,
        metrics: MetricsCollector,
        config: YggdrasilConfig,
        log_service: LogService,
        alert_service: AlertService,
    ):
        self.store = store
        self.season_manager = season_manager
        self.metrics = metrics
        self.config = config
        self.log_service = log_service
        self.alert_service = alert_service
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Inspection job started")

    async def stop(self, timeout: float = 30.0):
        if not self._running or self._task is None:
            return
        self._running = False
        self._task.cancel()
        try:
            await asyncio.wait_for(self._task, timeout=timeout)
        except asyncio.CancelledError:
            logger.info("Inspection job cancelled")
        self._task = None

    async def _run_loop(self):
        while self._running:
            try:
                await self.run_inspection()
                self.metrics.increment_inspection()
            except Exception as e:
                logger.error(f"Inspection failed: {e}", exc_info=True)
            try:
                await asyncio.sleep(24 * 3600)
            except asyncio.CancelledError:
                break

    async def run_inspection(self):
        logger.info("Starting Yggdrasil inspection...")
        self.metrics.increment_inspection()

        total_pruned = 0
        domains = await self.season_manager.list_all_domains()
        logger.info(f"Inspecting {len(domains)} domains")

        for domain in domains:
            pruned = await self._inspect_domain(domain)
            total_pruned += pruned

        await self._apply_winter_decay()
        self.metrics.increment_nodes_pruned(total_pruned)

        logger.info(f"Inspection complete: pruned {total_pruned} nodes")

        await self.log_service.log({
            "event": "yggdrasil_inspection",
            "domains_inspected": len(domains),
            "nodes_pruned": total_pruned,
        })

    async def _inspect_domain(self, domain) -> int:
        pruned = 0
        season = await self.season_manager.get_season(domain.full_path)

        if season == Season.AUTUMN:
            # 秋收：标记低强度节点
            nodes = await self.store.list_nodes(domain_id=domain.id, min_health=0.0)
            for node in nodes:
                if node.strength < self.config.retrieval_strength_threshold:
                    await self.store.update_node_strength(node.id, node.strength * 0.9)
                    pruned += 1

        return pruned

    async def _apply_winter_decay(self):
        """冬季衰减：长时间未使用的节点降低强度"""
        decay_factor = self.config.evolution_decay_factor
        cutoff = datetime.now() - timedelta(days=30)

        rows = await self.store.db.async_fetch(
            """SELECT id, strength FROM cog_node
               WHERE strength > 0.1 AND health > 0
               AND (last_accessed_at IS NULL OR last_accessed_at < ?)""",
            (cutoff,),
        )
        decayed = 0
        for row in rows:
            new_strength = max(0.1, row["strength"] * decay_factor)
            await self.store.update_node_strength(row["id"], new_strength)
            decayed += 1

        logger.info(f"Winter decay applied to {decayed} nodes")

    async def check_pollution(self, domain_id: int) -> tuple[bool, int]:
        """检查污染程度"""
        nodes = await self.store.list_nodes(domain_id=domain_id, min_health=0.0)
        if not nodes:
            return False, 0

        unhealthy = sum(1 for n in nodes if n.health < 0.5)
        ratio = unhealthy / len(nodes)

        if ratio > self.config.evolution_pollution_threshold:
            self.metrics.increment_pollution_detected()
            logger.warning(f"Pollution detected in domain {domain_id}: {unhealthy}/{len(nodes)} ({ratio:.1%})")
            return True, unhealthy

        return False, unhealthy


__all__ = ["InspectionJob"]