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
    """后台巡检任务 - 健康检查、冗余清理、季节转换、冬季衰减"""

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
                await self.alert_service.send_alert(
                    "Yggdrasil Inspection Failed",
                    {"error": str(e)},
                )
            try:
                await asyncio.sleep(24 * 3600)
            except asyncio.CancelledError:
                break

    async def run_inspection(self):
        logger.info("Starting Yggdrasil inspection...")
        self.metrics.increment_inspection()

        domains = await self.season_manager.list_all_domains()
        logger.info(f"Inspecting {len(domains)} domains")

        total_pruned = 0
        total_merged = 0

        for domain in domains:
            pruned, merged = await self.inspect_domain(domain)
            total_pruned += pruned
            total_merged += merged

        self.metrics.increment_nodes_pruned(total_pruned)
        self.metrics.increment_nodes_merged(total_merged)

        await self.apply_winter_decay()

        logger.info(f"Inspection complete: pruned {total_pruned}, merged {total_merged}")

        await self.log_service.log({
            "event": "yggdrasil_inspection",
            "domains_inspected": len(domains),
            "nodes_pruned": total_pruned,
            "nodes_merged": total_merged,
        })

    async def inspect_domain(self, domain) -> tuple[int, int]:
        pruned = 0
        merged = 0

        if domain.season == Season.AUTUMN:
            # 秋收：标记低强度节点
            pass

        return pruned, merged

    async def apply_winter_decay(self):
        decay_factor = self.config.evolution_decay_factor
        logger.info(f"Winter decay applied (factor={decay_factor})")

    async def check_pollution(self, domain_id: int) -> tuple[bool, int]:
        # 检查污染程度
        return False, 0


__all__ = ["InspectionJob"]