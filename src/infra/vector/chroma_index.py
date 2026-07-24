"""Chroma 向量索引 - revision 级别的索引管理"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import chromadb
from chromadb.config import Settings

from src.core.yggdrasil.cognitive.models import NodeRevision
from src.core.yggdrasil.embedding import EmbeddingService
from src.core.yggdrasil.ports.repositories import RevisionRepository

logger = logging.getLogger(__name__)


class ChromaIndexService:
    """Chroma 索引服务 - revision 维度索引管理

    Chroma 不是事实源。索引丢失后可通过 rebuild 从关系表恢复。
    """

    COLLECTION_NAME = "yggdrasil_revisions"

    def __init__(
        self,
        chroma_path: str,
        embedding: EmbeddingService,
        revision_repo: RevisionRepository,
    ):
        self.chroma_path = chroma_path
        self.embedding = embedding
        self.revision_repo = revision_repo
        self._client: Optional[chromadb.PersistentClient] = None
        self._collection: Optional[chromadb.Collection] = None

    async def initialize(self):
        import os
        os.makedirs(self.chroma_path, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=self.chroma_path,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            embedding_function=None,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"Chroma index initialized: {self.chroma_path}")

    @property
    def collection(self) -> chromadb.Collection:
        if not self._collection:
            raise RuntimeError("Chroma not initialized")
        return self._collection

    async def upsert_revision(self, rev: NodeRevision):
        """索引单个 revision"""
        doc = f"{rev.title}\n{rev.summary}"
        if rev.payload:
            import json
            doc += f"\n{json.dumps(rev.payload, ensure_ascii=False)}"

        embedding = await self.embedding.embed_text(doc)
        metadata = {
            "revision_id": rev.revision_id,
            "node_id": rev.node_id,
            "tree_id": rev.tree_id,
            "role": rev.role,
            "status": rev.status.value,
            "utility": str(rev.utility),
            "confidence": str(rev.confidence),
            "risk": str(rev.risk),
            "content_hash": rev.content_hash,
        }
        self.collection.upsert(
            ids=[rev.revision_id],
            embeddings=[embedding.tolist()],
            documents=[doc],
            metadatas=[metadata],
        )

    async def delete_revision(self, revision_id: str):
        """删除 revision 索引"""
        self.collection.delete(ids=[revision_id])

    async def rebuild(
        self,
        tree_id: Optional[str] = None,
        ring_id: Optional[str] = None,
        batch_size: int = 100,
    ):
        """从关系表重建索引

        Args:
            tree_id: 可选，只重建某棵树
            ring_id: 可选，只重建某个 ring（暂未实现 ring 级过滤）
            batch_size: 批量处理大小
        """
        logger.info(f"Rebuilding chroma index (tree={tree_id}, ring={ring_id})")
        # 删除现有集合重建
        try:
            self._client.delete_collection(self.COLLECTION_NAME)
        except ValueError:
            pass

        self._collection = self._client.create_collection(
            name=self.COLLECTION_NAME,
            embedding_function=None,
            metadata={"hnsw:space": "cosine"},
        )

        # 从 revision 表分批获取所有 active revision
        offset = 0
        total = 0
        while True:
            revisions = await self.revision_repo.list_all_active(
                tree_id=tree_id, limit=batch_size, offset=offset
            )
            if not revisions:
                break
            for rev in revisions:
                await self.upsert_revision(rev)
            total += len(revisions)
            offset += batch_size
            logger.info(f"  Indexed {total} revisions...")

        logger.info(f"Chroma index rebuild complete: {total} revisions indexed")

    async def search(
        self,
        query_text: str,
        n_results: int = 10,
        where: Optional[Dict] = None,
    ) -> List[str]:
        """搜索相似 revision

        Returns:
            匹配的 revision_id 列表
        """
        query_embedding = await self.embedding.embed_text(query_text)
        result = self.collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=n_results,
            where=where,
            include=["metadatas", "distances"],
        )
        if not result["ids"] or not result["ids"][0]:
            return []
        return result["ids"][0]
