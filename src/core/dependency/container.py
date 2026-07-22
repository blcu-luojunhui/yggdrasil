from dependency_injector import containers, providers

from src.core.config import YggdrasilConfig
from src.core.yggdrasil import (
    YggdrasilEngine,
    YggdrasilStore,
    EmbeddingService,
    SubtreeRetriever,
    SandboxManager,
)
from src.infra.database.duckdb import DuckDBPool
from src.infra.observability import LogService, AlertService, MetricsCollector
from src.infra.shared import HttpClient
from src.jobs.inspection_job import InspectionJob
from src.jobs.season_manager import SeasonManager


class ServerContainer(containers.DeclarativeContainer):
    config = providers.Singleton(YggdrasilConfig)

    log_service = providers.Singleton(LogService, log_config=config.provided.log)

    duckdb_pool = providers.Singleton(DuckDBPool, db_path=config.provided.duckdb_path)

    alert_service = providers.Singleton(
        AlertService, alert_backend=None, max_queue_size=config.provided.alert.queue_size,
    )

    http_client = providers.Singleton(HttpClient, timeout=10, max_connections=100)
    metrics_collector = providers.Singleton(MetricsCollector)

    # ── Yggdrasil 核心 ──
    yggdrasil_store = providers.Singleton(YggdrasilStore, db=duckdb_pool, config=config)

    embedding_service = providers.Singleton(EmbeddingService, config=config)

    subtree_retriever = providers.Singleton(
        SubtreeRetriever, store=yggdrasil_store, embedding=embedding_service, config=config,
    )

    sandbox_manager = providers.Singleton(
        SandboxManager, store=yggdrasil_store, embedding=embedding_service,
    )

    yggdrasil_engine = providers.Singleton(
        YggdrasilEngine,
        store=yggdrasil_store,
        retriever=subtree_retriever,
        embedding=embedding_service,
        sandbox=sandbox_manager,
        metrics=metrics_collector,
    )

    # ── 后台任务 ──
    season_manager = providers.Singleton(SeasonManager, store=yggdrasil_store, config=config)

    inspection_job = providers.Singleton(
        InspectionJob,
        store=yggdrasil_store,
        season_manager=season_manager,
        metrics=metrics_collector,
        config=config,
        log_service=log_service,
        alert_service=alert_service,
    )


__all__ = ["ServerContainer"]