from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry
import logging

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Prometheus 指标收集器"""

    def __init__(self, registry: CollectorRegistry = None):
        self.registry = registry or CollectorRegistry()

        # 请求指标
        self.request_count = Counter(
            "yggdrasil_requests_total", "Total number of requests", ["endpoint", "method"],
            registry=self.registry
        )
        self.request_latency = Histogram(
            "yggdrasil_request_duration_seconds", "Request latency", ["endpoint"],
            registry=self.registry
        )

        # 认知操作指标
        self.node_created_total = Counter(
            "yggdrasil_node_created_total", "Total number of nodes created", ["role"],
            registry=self.registry
        )
        self.node_updated_total = Counter(
            "yggdrasil_node_updated_total", "Total number of nodes updated", ["role"],
            registry=self.registry
        )
        self.edge_updated_total = Counter(
            "yggdrasil_edge_updated_total", "Total number of edges updated", ["relation_type"],
            registry=self.registry
        )

        # 检索指标
        self.retrieval_total = Counter(
            "yggdrasil_retrieval_total", "Total number of retrieval requests",
            registry=self.registry
        )
        self.retrieval_nodes_returned = Histogram(
            "yggdrasil_retrieval_nodes_returned_count", "Number of nodes returned per retrieval",
            registry=self.registry
        )

        # 巡检指标
        self.inspection_total = Counter(
            "yggdrasil_inspection_total", "Total number of inspection runs",
            registry=self.registry
        )
        self.inspection_nodes_merged = Counter(
            "yggdrasil_inspection_nodes_merged_total", "Total number of nodes merged during inspection",
            registry=self.registry
        )
        self.inspection_nodes_pruned = Counter(
            "yggdrasil_inspection_nodes_pruned_total", "Total number of nodes pruned during inspection",
            registry=self.registry
        )

        # 污染处理指标
        self.pollution_detected_total = Counter(
            "yggdrasil_pollution_detected_total", "Total number of pollution events detected",
            registry=self.registry
        )
        self.rollback_total = Counter(
            "yggdrasil_rollback_total", "Total number of rollback operations",
            registry=self.registry
        )

        # 系统状态
        self.node_total = Gauge(
            "yggdrasil_node_count", "Total number of nodes in the tree", ["role"],
            registry=self.registry
        )
        self.edge_total = Gauge(
            "yggdrasil_edge_count", "Total number of edges in the tree", ["relation_type"],
            registry=self.registry
        )

    def increment_request(self, endpoint: str, method: str):
        self.request_count.labels(endpoint=endpoint, method=method).inc()

    def observe_request_latency(self, endpoint: str, latency: float):
        self.request_latency.labels(endpoint=endpoint).observe(latency)

    def increment_node_created(self, role: str):
        self.node_created_total.labels(role=role).inc()

    def increment_node_updated(self, role: str):
        self.node_updated_total.labels(role=role).inc()

    def increment_edge_updated(self, relation_type: str):
        self.edge_updated_total.labels(relation_type=relation_type).inc()

    def increment_retrieval(self):
        self.retrieval_total.inc()

    def observe_retrieval_nodes(self, count: int):
        self.retrieval_nodes_returned.observe(count)

    def increment_inspection(self):
        self.inspection_total.inc()

    def increment_nodes_merged(self, count: int):
        self.inspection_nodes_merged.inc(count)

    def increment_nodes_pruned(self, count: int):
        self.inspection_nodes_pruned.inc(count)

    def increment_pollution_detected(self):
        self.pollution_detected_total.inc()

    def increment_rollback(self):
        self.rollback_total.inc()

    def set_node_count(self, role: str, count: int):
        self.node_total.labels(role=role).set(count)

    def set_edge_count(self, relation_type: str, count: int):
        self.edge_total.labels(relation_type=relation_type).set(count)


__all__ = ["MetricsCollector"]
