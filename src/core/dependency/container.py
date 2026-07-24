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
from src.infra.execution.skill_registry import SkillRegistry
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

    # ── D1+ Repository ──
    from src.infra.database.duckdb.repositories import (
        DuckDBTreeRepository,
        DuckDBRevisionRepository,
        DuckDBRingRepository,
        DuckDBSoilRepository,
        DuckDBRunRepository,
        DuckDBEvaluationRepository,
        DuckDBOutboxRepository,
    )
    tree_repo = providers.Singleton(DuckDBTreeRepository, pool=duckdb_pool)
    revision_repo = providers.Singleton(DuckDBRevisionRepository, pool=duckdb_pool)
    ring_repo = providers.Singleton(DuckDBRingRepository, pool=duckdb_pool)
    soil_repo = providers.Singleton(DuckDBSoilRepository, pool=duckdb_pool)
    run_repo = providers.Singleton(DuckDBRunRepository, pool=duckdb_pool)
    eval_repo = providers.Singleton(DuckDBEvaluationRepository, pool=duckdb_pool)
    outbox_repo = providers.Singleton(DuckDBOutboxRepository, pool=duckdb_pool)

    # ── D3+ Application Services ──
    skill_registry = providers.Singleton(SkillRegistry)

    from src.application.retrieval_service import RetrievalService
    retrieval_service = providers.Singleton(
        RetrievalService,
        tree_repo=tree_repo,
        revision_repo=revision_repo,
        ring_repo=ring_repo,
        metrics=metrics_collector,
    )

    from src.application.soil_service import SoilService
    soil_service = providers.Singleton(SoilService, soil_repo=soil_repo, metrics=metrics_collector)

    from src.application.run_service import RunService
    run_service = providers.Singleton(
        RunService,
        run_repo=run_repo,
        tree_repo=tree_repo,
        skill_registry=skill_registry,
        metrics=metrics_collector,
    )

    from src.application.evaluation_service import EvaluationService
    evaluation_service = providers.Singleton(EvaluationService, eval_repo=eval_repo)

    from src.application.tree_service import TreeService
    tree_service = providers.Singleton(
        TreeService,
        tree_repo=tree_repo,
        revision_repo=revision_repo,
        ring_repo=ring_repo,
        metrics=metrics_collector,
    )

    from src.application.ring_service import RingService
    ring_service = providers.Singleton(
        RingService,
        tree_repo=tree_repo,
        ring_repo=ring_repo,
        revision_repo=revision_repo,
        pool=duckdb_pool,
        metrics=metrics_collector,
    )

    from src.application.observe_service import ObserveService
    observe_service = providers.Singleton(
        ObserveService,
        tree_repo=tree_repo,
        revision_repo=revision_repo,
        ring_repo=ring_repo,
        soil_repo=soil_repo,
        run_repo=run_repo,
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

    from src.infra.vector.chroma_index import ChromaIndexService
    chroma_index_service = providers.Singleton(
        ChromaIndexService,
        chroma_path=config.provided.chroma_path,
        embedding=embedding_service,
        revision_repo=revision_repo,
    )

    from src.jobs.outbox_job import OutboxJob
    outbox_job = providers.Singleton(
        OutboxJob,
        outbox_repo=outbox_repo,
        config=config,
        log_service=log_service,
        chroma_index=chroma_index_service,
        revision_repo=revision_repo,
    )

    from src.jobs.evaluation_job import EvaluationJob
    evaluation_job = providers.Singleton(
        EvaluationJob,
        run_repo=run_repo,
        eval_repo=eval_repo,
        config=config,
        log_service=log_service,
    )


__all__ = ["ServerContainer"]