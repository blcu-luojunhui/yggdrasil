import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import List, Optional

import duckdb

logger = logging.getLogger(__name__)


class Transaction:
    """事务代理 — 禁止暴露裸 DuckDB connection。

    通过 DuckDBPool.transaction() 获取，提供 execute/fetch_one/fetch_all。
    事务内持有 pool lock，异常自动 rollback，commit 失败向上抛出。
    """

    def __init__(self, pool: "DuckDBPool", conn: duckdb.DuckDBPyConnection, lock: asyncio.Lock):
        self._pool = pool
        self._conn = conn
        self._lock = lock
        self._committed = False

    async def execute(self, sql: str, params=None):
        """执行 SQL（写入/DDL），不返回结果。"""
        loop = asyncio.get_running_loop()
        if params is not None:
            await loop.run_in_executor(None, lambda: self._conn.execute(sql, params))
        else:
            await loop.run_in_executor(None, lambda: self._conn.execute(sql))

    async def fetch_one(self, sql: str, params=None) -> Optional[dict]:
        """执行查询并返回单行字典。"""
        loop = asyncio.get_running_loop()
        if params is not None:
            result = await loop.run_in_executor(None, lambda: self._conn.execute(sql, params))
        else:
            result = await loop.run_in_executor(None, lambda: self._conn.execute(sql))
        if result is None:
            return None
        rows = await loop.run_in_executor(None, result.fetchall)
        if not rows:
            return None
        cols = [desc[0] for desc in result.description]
        return dict(zip(cols, rows[0]))

    async def fetch_all(self, sql: str, params=None) -> List[dict]:
        """执行查询并返回字典列表。"""
        loop = asyncio.get_running_loop()
        if params is not None:
            result = await loop.run_in_executor(None, lambda: self._conn.execute(sql, params))
        else:
            result = await loop.run_in_executor(None, lambda: self._conn.execute(sql))
        if result is None:
            return []
        rows = await loop.run_in_executor(None, result.fetchall)
        cols = [desc[0] for desc in result.description]
        return [dict(zip(cols, row)) for row in rows]

    async def commit(self):
        """提交事务。"""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: self._conn.execute("COMMIT"))
        self._committed = True

    async def rollback(self):
        """回滚事务。"""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: self._conn.execute("ROLLBACK"))


class DuckDBPool:
    """DuckDB 连接池 - 进程内单连接，asyncio.Lock 串行化"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: Optional[duckdb.DuckDBPyConnection] = None
        self._lock = asyncio.Lock()

    async def init_pools(self):
        """初始化 DuckDB 连接"""
        async with self._lock:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            self._conn = duckdb.connect(self.db_path)
            logger.info(f"DuckDB connected: {self.db_path}")

    async def close_pools(self):
        """关闭连接"""
        async with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None
                logger.info("DuckDB connection closed")

    async def healthcheck(self) -> bool:
        """检查数据库连接健康状态"""
        try:
            async with self._lock:
                if not self._conn:
                    return False
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(
                    None, lambda: self._conn.execute("SELECT 1").fetchall()
                )
                return result is not None
        except Exception:
            return False

    async def execute_script(self, statements: list[str]):
        """批量执行 DDL 语句（幂等）"""
        async with self._lock:
            for stmt in statements:
                try:
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, lambda: self._conn.execute(stmt))
                except Exception as e:
                    logger.warning(f"DDL statement failed (may be harmless): {e}")

    async def _execute(self, query: str, params=None):
        """执行 SQL，返回 duckdb 结果（调用方已持有锁）"""
        if not self._conn:
            raise RuntimeError("DuckDB not initialized, call init_pools() first")
        loop = asyncio.get_running_loop()
        if params:
            return await loop.run_in_executor(None, lambda: self._conn.execute(query, params))
        return await loop.run_in_executor(None, lambda: self._conn.execute(query))

    async def async_fetch(self, query: str, params=None) -> list[dict]:
        """执行查询并返回字典列表"""
        async with self._lock:
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
        async with self._lock:
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
        async with self._lock:
            await self._execute(query, params)

    @asynccontextmanager
    async def transaction(self):
        """事务上下文管理器 — 返回 Transaction 代理，禁止暴露裸 connection。

        用法:
            async with pool.transaction() as tx:
                await tx.execute(sql, params)
                row = await tx.fetch_one(sql, params)
                # 正常退出时自动 commit，异常时自动 rollback
        """
        if not self._conn:
            await self.init_pools()
        loop = asyncio.get_running_loop()
        async with self._lock:
            try:
                await loop.run_in_executor(None, lambda: self._conn.execute("BEGIN TRANSACTION"))
                tx = Transaction(self, self._conn, self._lock)
                yield tx
                if not tx._committed:
                    await tx.commit()
            except Exception:
                await loop.run_in_executor(None, lambda: self._conn.execute("ROLLBACK"))
                raise


__all__ = ["DuckDBPool", "Transaction"]