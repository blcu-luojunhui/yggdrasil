import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

import duckdb

logger = logging.getLogger(__name__)


class DuckDBPool:
    """DuckDB 连接池 - 进程内单连接，线程安全封装"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: Optional[duckdb.DuckDBPyConnection] = None

    async def init_pools(self):
        """初始化 DuckDB 连接"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._conn = duckdb.connect(self.db_path)
        logger.info(f"DuckDB connected: {self.db_path}")

    async def close_pools(self):
        """关闭连接"""
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.info("DuckDB connection closed")

    async def _execute(self, query: str, params=None):
        """执行 SQL，返回 duckdb 结果"""
        if not self._conn:
            await self.init_pools()
        loop = asyncio.get_running_loop()
        if params:
            return await loop.run_in_executor(None, lambda: self._conn.execute(query, params))
        return await loop.run_in_executor(None, lambda: self._conn.execute(query))

    async def async_fetch(self, query: str, params=None) -> list[dict]:
        """执行查询并返回字典列表"""
        result = await self._execute(query, params)
        if result is None:
            return []
        loop = asyncio.get_running_loop()
        rows = await loop.run_in_executor(None, result.fetchall)
        cols = [desc[0] for desc in result.description]
        return [dict(zip(cols, row)) for row in rows]

    async def async_fetch_one(self, query: str, params=None) -> Optional[dict]:
        """执行查询并返回单行字典"""
        rows = await self.async_fetch(query, params)
        return rows[0] if rows else None

    async def async_save(self, query: str, params=None, return_lastrowid: bool = False) -> int:
        """执行写入并返回受影响行数"""
        result = await self._execute(query, params)
        if result is None:
            return 0
        loop = asyncio.get_running_loop()
        count = await loop.run_in_executor(None, result.fetchall)
        if return_lastrowid and count:
            return count[0][0] if count[0] else 0
        return len(count) if count else 0

    async def async_execute(self, query: str, params=None):
        """执行 SQL（DDL 等），不返回结果"""
        await self._execute(query, params)

    @asynccontextmanager
    async def transaction(self):
        """事务上下文管理器"""
        if not self._conn:
            await self.init_pools()
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, lambda: self._conn.execute("BEGIN TRANSACTION"))
            yield self._conn
            await loop.run_in_executor(None, lambda: self._conn.execute("COMMIT"))
        except Exception:
            await loop.run_in_executor(None, lambda: self._conn.execute("ROLLBACK"))
            raise


__all__ = ["DuckDBPool"]