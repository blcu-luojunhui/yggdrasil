import logging
import struct
import numpy as np
from typing import List, Optional

from src.core.config import YggdrasilConfig
from src.infra.shared import HttpClient

logger = logging.getLogger(__name__)


class EmbeddingService:
    """嵌入服务 - 调用 LLM API 生成文本嵌入"""

    def __init__(self, config: YggdrasilConfig, http_client: HttpClient):
        self.config = config
        self.http_client = http_client
        self.initialized = False

    async def initialize(self):
        """初始化"""
        self.initialized = True
        logger.info("Embedding service initialized")

    async def embed_text(self, text: str) -> np.ndarray:
        """生成单个文本嵌入"""
        return await self._call_openai_embedding([text])

    async def embed_texts(self, texts: List[str]) -> List[np.ndarray]:
        """批量生成文本嵌入"""
        return await self._call_openai_embedding(texts)

    def serialize(self, embedding: np.ndarray) -> bytes:
        """序列化 numpy 数组为二进制存储"""
        return embedding.tobytes()

    def deserialize(self, data: bytes) -> np.ndarray:
        """从二进制反序列化为 numpy 数组"""
        return np.frombuffer(data, dtype=np.float32)

    def cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """计算余弦相似度"""
        dot = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(dot / (norm_a * norm_b))

    async def _call_openai_embedding(self, texts: List[str]) -> List[np.ndarray]:
        """调用 OpenAI 兼容接口生成嵌入"""
        api_key = self.config.llm_api_key
        if not api_key:
            # 返回随机嵌入用于测试
            logger.warning("No API key configured for embedding, returning random embeddings")
            return [np.random.randn(self.config.llm_embedding_dim).astype(np.float32) for _ in texts]

        url = f"{self.config.llm_base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.config.llm_model,
            "input": texts,
        }

        try:
            result = await self.http_client.post(url, json=payload, headers=headers)
            if isinstance(result, dict) and "data" in result:
                embeddings = []
                for item in sorted(result["data"], key=lambda x: x["index"]):
                    embedding = np.array(item["embedding"], dtype=np.float32)
                    if embedding.shape[0] != self.config.llm_embedding_dim:
                        logger.warning(
                            f"Embedding dimension mismatch: expected {self.config.llm_embedding_dim}, got {embedding.shape[0]}"
                        )
                    embeddings.append(embedding)
                return embeddings
            else:
                logger.error(f"Unexpected response from embedding API: {result}")
                raise ValueError(f"Invalid response: {result}")
        except Exception as e:
            logger.error(f"Embedding API call failed: {e}")
            raise

    def similarity_search(
        self,
        query_embedding: np.ndarray,
        candidates: List[tuple[int, bytes]],  # (node_id, embedding_bytes)
        top_k: int = 10,
    ) -> List[tuple[int, float]]:
        """相似度搜索，返回 (node_id, similarity) 按相似度降序"""
        results: List[tuple[int, float]] = []
        for node_id, embedding_bytes in candidates:
            embedding = self.deserialize(embedding_bytes)
            similarity = self.cosine_similarity(query_embedding, embedding)
            results.append((node_id, similarity))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]


__all__ = ["EmbeddingService"]
