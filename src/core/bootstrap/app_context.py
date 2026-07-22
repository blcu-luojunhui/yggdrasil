import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.dependency import ServerContainer

logger = logging.getLogger(__name__)


class AppContext:
    """应用上下文管理器 - 统一管理所有资源的启动和关闭生命周期"""

    def __init__(self, container: "ServerContainer"):
        self.container = container

    async def start_up(self):
        """启动所有资源"""
        logger.info("=== Phase 1: Initializing DuckDB ===")
        pool = self.container.duckdb_pool()
        await pool.init_pools()
        logger.info("DuckDB initialized")

        logger.info("=== Phase 2: Starting log service ===")
        log_service = self.container.log_service()
        await log_service.start()
        logger.info("Log service started")

        logger.info("=== Phase 3: Starting alert service ===")
        alert_service = self.container.alert_service()
        await alert_service.start()
        logger.info("Alert service started")

        logger.info("=== Phase 4: Starting HTTP client ===")
        http_client = self.container.http_client()
        await http_client.start()
        logger.info("HTTP client started")

        logger.info("=== Phase 5: Initializing Yggdrasil world tree ===")
        try:
            yggdrasil_store = self.container.yggdrasil_store()
            await yggdrasil_store.ensure_skeleton()

            embedding_service = self.container.embedding_service()
            await embedding_service.initialize()
            logger.info("Yggdrasil: ChromaDB initialized")
        except Exception:
            logger.warning("Yggdrasil initialization failed", exc_info=True)

        logger.info("=== Phase 6: Starting inspection job ===")
        try:
            inspection_job = self.container.inspection_job()
            await inspection_job.start()
            logger.info("Inspection job started")
        except Exception:
            logger.warning("Inspection job start failed", exc_info=True)

        logger.info("=== Application startup complete ===")

    async def shutdown(self):
        """关闭所有资源（优雅关闭）"""
        logger.info("=== Phase 1: Stopping inspection job ===")
        inspection_job = self.container.inspection_job()
        await inspection_job.stop(timeout=30.0)
        logger.info("Inspection job stopped")

        logger.info("=== Phase 2: Stopping alert service ===")
        alert_service = self.container.alert_service()
        await alert_service.stop(drain_timeout=5.0)
        logger.info("Alert service stopped")

        logger.info("=== Phase 3: Stopping log service ===")
        log_service = self.container.log_service()
        await log_service.stop(drain_timeout=10.0)
        logger.info("Log service stopped")

        logger.info("=== Phase 4: Closing DuckDB ===")
        pool = self.container.duckdb_pool()
        await pool.close_pools()
        logger.info("DuckDB closed")

        logger.info("=== Phase 5: Closing HTTP client ===")
        http_client = self.container.http_client()
        await http_client.close()
        logger.info("HTTP client closed")

        logger.info("=== Application shutdown complete ===")


__all__ = ["AppContext"]