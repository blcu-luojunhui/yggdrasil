from dependency_injector import containers, providers

from src.core.config import YggdrasilConfig
from src.core.yggdrasil import (
    YggdrasilEngine,
    YggdrasilStore,
    EmbeddingService,
    SubtreeRetriever,
)
from src.infra.database.mysql import AsyncMySQLPool
from src.infra.observability import LogService, AlertService, MetricsCollector
from src.infra.shared import HttpClient
from src.jobs import InspectionJob, SeasonManager


class ServerContainer(containers.DeclarativeContainer):
    config = providers.Singleton(YggdrasilConfig)

    log_service = providers.Singleton(LogService, log_config=config.provided.log)

    async_mysql_pool = providers.Singleton(
        AsyncMySQLPool, config=config.provided.db, log_service=log_service
    )

    alert_service = providers.Singleton(
        AlertService,
        alert_backend=None,
        max_queue_size=config.provided.alert.queue_size,
    )

    http_client = providers.Singleton(
        HttpClient,
        timeout=10,
        max_connections=100,
    )

    metrics_collector = providers.Singleton(MetricsCollector)

    # ============ Yggdrasil 核心能力 ============
    yggdrasil_store = providers.Singleton(
        YggdrasilStore,
        db=async_mysql_pool,
        config=config,
    )

    embedding_service = providers.Singleton(
        EmbeddingService,
        config=config,
        http_client=http_client,
    )

    subtree_retriever = providers.Singleton(
        SubtreeRetriever,
        store=yggdrasil_store,
        embedding=embedding_service,
        config=config,
    )

    yggdrasil_engine = providers.Singleton(
        YggdrasilEngine,
        store=yggdrasil_store,
        retriever=subtree_retriever,
        embedding=embedding_service,
        metrics=metrics_collector,
    )

    # ============ 后台任务 ============
    season_manager = providers.Singleton(
        SeasonManager,
        store=yggdrasil_store,
        config=config,
    )

    inspection_job = providers.Singleton(
        InspectionJob,
        store=yggdrasil_store,
        retriever=subtree_retriever,
        season_manager=season_manager,
        metrics=metrics_collector,
        config=config,
        log_service=log_service,
        alert_service=alert_service,
    )


__all__ = ["ServerContainer"]
