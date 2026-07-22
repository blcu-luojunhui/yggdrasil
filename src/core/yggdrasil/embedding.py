import logging
import os
from typing import List, Optional, Dict

import chromadb
import numpy as np
from chromadb.config import Settings

from src.core.config import YggdrasilConfig
from src.core.yggdrasil.models import CognitiveNode, CognitiveRole

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
        """初始化 ChromaDB 客户端和集合"""
        os.makedirs(self.config.chroma_path, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=self.config.chroma_path,
            settings=Settings(anonymized_telemetry=False),
        )

        # 获取或创建集合
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

        self._initialized = True
        logger.info(f"ChromaDB initialized: {self.config.chroma_path}")

    @property
    def collection(self) -> chromadb.Collection:
        if not self._collection:
            raise RuntimeError("ChromaDB not initialized, call initialize() first")
        return self._collection

    async def embed_text(self, text: str) -> np.ndarray:
        """生成单个文本嵌入"""
        embeddings = await self.embed_texts([text])
        return embeddings[0]

    async def embed_texts(self, texts: List[str]) -> List[np.ndarray]:
        """批量生成文本嵌入"""
        if self.config.llm_api_key:
            return await self._call_openai_embedding(texts)
        # 没有 API key 时，用 Chroma 内置 embedding function
        return [np.random.randn(self.config.llm_embedding_dim).astype(np.float32) for _ in texts]

    async def _call_openai_embedding(self, texts: List[str]) -> List[np.ndarray]:
        """调用 OpenAI 兼容接口生成嵌入"""
        import aiohttp

        url = f"{self.config.llm_base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.config.llm_api_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": self.config.llm_model, "input": texts}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                result = await resp.json()
                if "data" not in result:
                    raise ValueError(f"Invalid response from embedding API: {result}")
                embeddings = []
                for item in sorted(result["data"], key=lambda x: x["index"]):
                    embeddings.append(np.array(item["embedding"], dtype=np.float32))
                return embeddings

    # ── ChromaDB CRUD ──

    async def upsert_node(self, node: CognitiveNode):
        """插入或更新节点到 ChromaDB"""
        text = f"{node.node_name}\n{node.description or ''}\n{node.content or ''}"
        metadata = {
            "node_id": str(node.id),
            "domain_id": str(node.domain_id),
            "role": node.role.value,
            "node_name": node.node_name,
            "description": node.description or "",
            "strength": str(node.strength),
            "health": str(node.health),
            "is_isolated": str(node.is_isolated),
            "last_used_at": node.last_used_at.isoformat() if node.last_used_at else "",
        }

        self.collection.upsert(
            ids=[str(node.id)],
            documents=[text],
            metadatas=[metadata],
        )

    async def delete_node(self, node_id: str):
        """从 ChromaDB 删除节点"""
        self.collection.delete(ids=[node_id])

    async def get_node(self, node_id: str) -> Optional[CognitiveNode]:
        """从 ChromaDB 获取节点"""
        result = self.collection.get(ids=[node_id], include=["metadatas", "documents"])
        if not result["ids"]:
            return None
        return self._result_to_node(
            result["ids"][0],
            result["metadatas"][0],
            result["documents"][0],
        )

    async def search(
        self,
        query_text: str,
        n_results: int = 10,
        where: Optional[Dict] = None,
    ) -> List[tuple[CognitiveNode, float]]:
        """
        用文本查询搜索最相似的节点
        返回 [(node, distance), ...]
        """
        result = self.collection.query(
            query_texts=[query_text],
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
            node = self._result_to_node(node_id, metadata, document)
            nodes.append((node, distance))

        return nodes

    async def list_nodes(
        self, domain_id: Optional[int] = None, include_isolated: bool = False
    ) -> List[CognitiveNode]:
        """列出节点，可按领域过滤"""
        where = {}
        if domain_id is not None:
            where["domain_id"] = str(domain_id)
        if not include_isolated:
            where["is_isolated"] = "False"

        result = self.collection.get(
            where=where if where else None,
            include=["metadatas", "documents"],
        )

        if not result["ids"]:
            return []

        return [
            self._result_to_node(result["ids"][i], result["metadatas"][i], result["documents"][i])
            for i in range(len(result["ids"]))
        ]

    async def update_metadata(self, node_id: str, metadata: Dict):
        """更新节点元数据"""
        self.collection.update(ids=[node_id], metadatas=[metadata])

    async def count_nodes(self) -> int:
        return self.collection.count()

    async def count_nodes_by_role(self) -> Dict[CognitiveRole, int]:
        """按 role 统计节点数"""
        result = self.collection.get(include=["metadatas"])
        counts: Dict[str, int] = {}
        for meta in (result["metadatas"] or []):
            role = meta.get("role", "unknown")
            counts[role] = counts.get(role, 0) + 1
        return {CognitiveRole(k): v for k, v in counts.items()}

    @staticmethod
    def _result_to_node(node_id: str, metadata: dict, document: str) -> CognitiveNode:
        return CognitiveNode(
            id=int(node_id) if node_id.isdigit() else hash(node_id),
            domain_id=int(metadata.get("domain_id", 0)),
            role=CognitiveRole(metadata.get("role", "fact")),
            node_name=metadata.get("node_name", ""),
            description=metadata.get("description") or None,
            content=document,
            strength=float(metadata.get("strength", 0.5)),
            health=float(metadata.get("health", 1.0)),
            is_isolated=metadata.get("is_isolated", "False") == "True",
            last_used_at=metadata.get("last_used_at") or None,
        )


__all__ = ["EmbeddingService"]