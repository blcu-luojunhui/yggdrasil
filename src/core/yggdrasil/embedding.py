import hashlib
import logging
import os
from typing import List, Optional, Dict

import chromadb
import numpy as np
from chromadb.config import Settings

from src.core.config import YggdrasilConfig
from src.core.yggdrasil.models import CognitiveNode, CognitiveRole, Season

logger = logging.getLogger(__name__)


class EmbeddingService:
    """ChromaDB 向量存储 + 嵌入服务"""

    COLLECTION_NAME = "yggdrasil_nodes"

    def __init__(self, config: YggdrasilConfig):
        self.config = config
        self._client: Optional[chromadb.PersistentClient] = None
        self._collection: Optional[chromadb.Collection] = None
        self._initialized = False

    async def initialize(self):
        os.makedirs(self.config.chroma_path, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=self.config.chroma_path,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            embedding_function=None,  # 不使用 Chroma 内置 embedding，自己调用 API
            metadata={"hnsw:space": "cosine"},
        )
        self._initialized = True
        logger.info(f"ChromaDB initialized: {self.config.chroma_path}")

    @property
    def collection(self) -> chromadb.Collection:
        if not self._collection:
            raise RuntimeError("ChromaDB not initialized, call initialize() first")
        return self._collection

    # ── Embedding ──

    async def embed_text(self, text: str) -> np.ndarray:
        embeddings = await self.embed_texts([text])
        return embeddings[0]

    async def embed_texts(self, texts: List[str]) -> List[np.ndarray]:
        if self.config.llm_api_key:
            try:
                return await self._call_openai_embedding(texts)
            except Exception:
                if not self.config.embedding_deterministic_fallback:
                    raise
                logger.warning(
                    "Remote embedding failed; using deterministic local fallback",
                    exc_info=True,
                )
        return [self._deterministic_embedding(t, self.config.llm_embedding_dim) for t in texts]

    @staticmethod
    def _deterministic_embedding(text: str, dim: int = 1536) -> np.ndarray:
        """无 API Key 时用 SHA-256 派生 seed 的确定性向量，同一输入输出相同并归一化"""
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()
        seed = int(h[:16], 16)
        rng = np.random.default_rng(seed)
        vec = rng.standard_normal(dim).astype(np.float32)
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec

    async def _call_openai_embedding(self, texts: List[str]) -> List[np.ndarray]:
        import aiohttp
        url = f"{self.config.llm_base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.config.llm_api_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": self.config.llm_model, "input": texts}
        timeout = aiohttp.ClientTimeout(total=5.0)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                result = await resp.json()
                if "data" not in result:
                    raise ValueError(f"Invalid response from embedding API: {result}")
                embeddings = []
                for item in sorted(result["data"], key=lambda x: x["index"]):
                    embeddings.append(np.array(item["embedding"], dtype=np.float32))
                return embeddings

    # ── Chroma CRUD ──

    def _node_metadata(self, node: CognitiveNode) -> dict:
        return {
            "node_id": node.id or "",
            "domain_id": str(node.domain_id),
            "domain_path": node.domain_path,
            "role": node.role.value,
            "title": node.title,
            "strength": str(node.strength),
            "health": str(node.health),
            "season": node.season.value,
            "tenant_id": node.tenant_id,
            "embedding_id": node.embedding_id or "",
        }

    def _node_document(self, node: CognitiveNode) -> str:
        return f"{node.title}\n{node.content or ''}"

    async def upsert_node(self, node: CognitiveNode):
        doc = self._node_document(node)
        embedding = await self.embed_text(doc)
        self.collection.upsert(
            ids=[node.id],
            embeddings=[embedding.tolist()],
            documents=[doc],
            metadatas=[self._node_metadata(node)],
        )

    async def delete_node(self, node_id: str):
        self.collection.delete(ids=[node_id])

    async def get_node(self, node_id: str) -> Optional[CognitiveNode]:
        result = self.collection.get(ids=[node_id], include=["metadatas", "documents"])
        if not result["ids"]:
            return None
        return self._result_to_node(result["ids"][0], result["metadatas"][0], result["documents"][0])

    async def search(
        self,
        query_text: str,
        n_results: int = 10,
        where: Optional[Dict] = None,
    ) -> List[tuple[CognitiveNode, float]]:
        if self.collection.count() == 0:
            return []
        # 自己生成嵌入，避免 Chroma 下载 ONNX 模型
        query_embedding = await self.embed_text(query_text)
        result = self.collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=n_results,
            where=where,
            include=["metadatas", "documents", "distances"],
        )
        if not result["ids"] or not result["ids"][0]:
            return []

        nodes: List[tuple[CognitiveNode, float]] = []
        for i, node_id in enumerate(result["ids"][0]):
            metadata = result["metadatas"][0][i]
            document = result["documents"][0][i]
            distance = result["distances"][0][i] if result.get("distances") else 0.0
            nodes.append((self._result_to_node(node_id, metadata, document), distance))
        return nodes

    async def list_nodes(self, domain_id: Optional[int] = None, min_health: float = 0.0) -> List[CognitiveNode]:
        where = {"health": {"$gt": str(min_health)}}
        if domain_id is not None:
            where["domain_id"] = str(domain_id)

        result = self.collection.get(where=where, include=["metadatas", "documents"])
        if not result["ids"]:
            return []
        return [
            self._result_to_node(result["ids"][i], result["metadatas"][i], result["documents"][i])
            for i in range(len(result["ids"]))
        ]

    async def update_metadata(self, node_id: str, metadata: Dict):
        self.collection.update(ids=[node_id], metadatas=[metadata])

    async def count_nodes(self) -> int:
        return self.collection.count()

    async def count_nodes_by_role(self) -> Dict[CognitiveRole, int]:
        result = self.collection.get(include=["metadatas"])
        counts: Dict[str, int] = {}
        for meta in (result["metadatas"] or []):
            role = meta.get("role", "unknown")
            counts[role] = counts.get(role, 0) + 1
        return {CognitiveRole(k): v for k, v in counts.items()}

    @staticmethod
    def _result_to_node(node_id: str, metadata: dict, document: str) -> CognitiveNode:
        return CognitiveNode(
            id=node_id,
            role=CognitiveRole(metadata.get("role", "fact")),
            domain_id=int(metadata.get("domain_id", 0)),
            domain_path=metadata.get("domain_path", ""),
            title=metadata.get("title", ""),
            content=document,
            strength=float(metadata.get("strength", 0.5)),
            health=float(metadata.get("health", 1.0)),
            season=Season(metadata.get("season", "spring")),
            embedding_id=metadata.get("embedding_id") or None,
            tenant_id=metadata.get("tenant_id", "default"),
        )


__all__ = ["EmbeddingService"]
