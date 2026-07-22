import asyncio
import logging
from datetime import datetime, timedelta

from src.core.config import YggdrasilConfig
from src.core.yggdrasil.models import (
    Domain,
    CognitiveNode,
    CognitiveRole,
    Season,
)
from src.core.yggdrasil.store import YggdrasilStore
from src.core.yggdrasil.retriever import SubtreeRetriever
from src.jobs import SeasonManager
from src.infra.observability import LogService, AlertService, MetricsCollector

logger = logging.getLogger(__name__)


class InspectionJob:
    """后台巡检任务 - 执行健康检查、冗余清理、季节转换"""

    def __init__(
        self,
        store: YggdrasilStore,
        retriever: SubtreeRetriever,
        season_manager: SeasonManager,
        metrics: MetricsCollector,
        config: YggdrasilConfig,
        log_service: LogService,
        alert_service: AlertService,
    ):
        self.store = store
        self.retriever = retriever
        self.season_manager = season_manager
        self.metrics = metrics
        self.config = config
        self.log_service = log_service
        self.alert_service = alert_service
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self):
        """启动周期性巡检"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Inspection job started")

    async def stop(self, timeout: float = 30.0):
        """停止巡检"""
        if not self._running or self._task is None:
            return
        self._running = False
        self._task.cancel()
        try:
            await asyncio.wait_for(self._task, timeout=timeout)
        except asyncio.CancelledError:
            logger.info("Inspection job cancelled")
        except Exception:
            logger.exception("Error stopping inspection job")
        self._task = None

    async def _run_loop(self):
        """巡检循环"""
        while self._running:
            try:
                await self.run_inspection()
                self.metrics.increment_inspection()
            except Exception as e:
                logger.error(f"Inspection run failed: {e}", exc_info=True)
                await self.alert_service.send_alert(
                    "Yggdrasil Inspection Failed",
                    {"error": str(e)},
                )

            # 等待下一次，这里简化为每 24 小时运行一次
            # 生产环境应该用 cron 调度
            try:
                await asyncio.sleep(24 * 3600)
            except asyncio.CancelledError:
                break

    async def run_inspection(self):
        """执行一次完整巡检"""
        logger.info("Starting Yggdrasil inspection...")
        self.metrics.increment_inspection()

        total_nodes_pruned = 0
        total_nodes_merged = 0

        # 遍历所有领域
        domains = await self.season_manager.list_all_domains()
        logger.info(f"Inspecting {len(domains)} domains")

        for domain in domains:
            pruned, merged = await self.inspect_domain(domain)
            total_nodes_pruned += pruned
            total_nodes_merged += merged

        # 更新指标
        self.metrics.increment_nodes_pruned(total_nodes_pruned)
        self.metrics.increment_nodes_merged(total_nodes_merged)

        # 执行冬季衰减
        await self.apply_winter_decay()

        logger.info(
            f"Inspection complete: pruned {total_nodes_pruned} nodes, merged {total_nodes_merged} nodes"
        )

        await self.log_service.log({
            "event": "yggdrasil_inspection",
            "domains_inspected": len(domains),
            "nodes_pruned": total_nodes_pruned,
            "nodes_merged": total_nodes_merged,
        })

        return {
            "domains_inspected": len(domains),
            "nodes_pruned": total_nodes_pruned,
            "nodes_merged": total_nodes_merged,
        }

    async def inspect_domain(self, domain: Domain) -> tuple[int, int]:
        """巡检单个领域"""
        pruned = 0
        merged = 0

        # 获取所有节点
        nodes = await self.store.list_nodes_by_domain(domain.id, include_isolated=True)

        # 1. 检查健康度，隔离健康度过低的节点
        for node in nodes:
            if node.health <= 0:
                if not node.is_isolated:
                    await self.store.isolate_node(node.id, True)
                    pruned += 1
                    logger.debug(f"Isolated node {node.id} ({node.node_name}) health={node.health:.2f}")

        # 2. 识别相似度非常高的节点，建议合并
        # Phase 1: 标记，不自动合并，留给人工确认
        # 后续版本可以自动合并相似度 > 0.95 的节点

        # 3. 根据季节执行策略
        season = domain.season
        if season == Season.AUTUMN:
            # 秋收：检查低强度节点，建议修剪
            for node in nodes:
                if node.strength < self.config.retrieval_strength_threshold and not node.is_isolated:
                    # 不立即删除，只降低强度，冬季再处理
                    new_strength = node.strength * 0.9
                    await self.store.update_node_strength(node.id, new_strength)

        return pruned, merged

    async def apply_winter_decay(self):
        """冬季衰减：长时间未使用的节点强度衰减"""
        decay_factor = self.config.evolution_decay_factor
        cutoff_days = 90  # 90 天未使用触发衰减

        # 找出超过 cutoff 未使用的节点
        cutoff_date = datetime.now() - timedelta(days=cutoff_days)
        rows = await self.store.db.async_fetch(
            """
            SELECT id, strength FROM cog_nodes
            WHERE last_used_at < %s AND strength > 0 AND is_isolated = FALSE
            """,
            (cutoff_date,),
        )

        decayed = 0
        for row in rows:
            new_strength = row["strength"] * decay_factor
            if new_strength < self.config.retrieval_strength_threshold:
                # 低于阈值，隔离
                await self.store.isolate_node(row["id"], True)
            else:
                await self.store.update_node_strength(row["id"], new_strength)
            decayed += 1

        logger.info(f"Winter decay applied to {decayed} nodes")

    async def check_pollution(self, domain_id: int) -> tuple[bool, int]:
        """检查领域污染程度，判断是否需要回滚"""
        nodes = await self.store.list_nodes_by_domain(domain_id, include_isolated=False)
        if not nodes:
            return False, 0

        unhealthy = sum(1 for node in nodes if node.health < 0.5)
        ratio = unhealthy / len(nodes)

        if ratio > self.config.evolution_pollution_threshold:
            self.metrics.increment_pollution_detected()
            logger.warning(
                f"Pollution detected in domain {domain_id}: "
                f"{unhealthy}/{len(nodes)} nodes unhealthy ({ratio:.1%})"
            )
            await self.alert_service.send_alert(
                "Yggdrasil Pollution Detected",
                {
                    "domain_id": domain_id,
                    "unhealthy_nodes": unhealthy,
                    "total_nodes": len(nodes),
                    "ratio": ratio,
                },
            )
            return True, unhealthy

        return False, unhealthy


__all__ = ["InspectionJob"]
