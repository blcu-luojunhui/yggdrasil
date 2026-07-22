import logging
from contextlib import asynccontextmanager

from aiomysql import create_pool
from aiomysql.cursors import DictCursor

from src.core.config.database import YggdrasilMySQLConfig
from src.infra.observability import LogService

logger = logging.getLogger(__name__)


class AsyncMySQLPool:
    def __init__(self, config: YggdrasilMySQLConfig, log_service: LogService):
        self.log_service = log_service
        self.config = config
        self.pools = {}

    async def _log(self, contents: dict):
        await self.log_service.log(contents)

    async def init_pools(self):
        try:
            pool = await create_pool(
                host=self.config.host,
                port=self.config.port,
                user=self.config.user,
                password=self.config.password,
                db=self.config.db,
                minsize=self.config.minsize,
                maxsize=self.config.maxsize,
                cursorclass=DictCursor,
                autocommit=True,
            )
            self.pools["default"] = pool
            logger.info("Default MySQL pool created successfully")
        except Exception as e:
            logger.critical(f"Failed to create MySQL pool: {e}")
            raise RuntimeError(
                f"MySQL pool initialization failed: {e}. "
                f"Check database connection settings (host={self.config.host}, "
                f"port={self.config.port}, db={self.config.db})"
            ) from e

    async def close_pools(self):
        for name, pool in self.pools.items():
            if pool:
                pool.close()
                await pool.wait_closed()
                logger.info(f"{name} MySQL pool closed")

    async def async_fetch(self, query, db_name="default", params=None, cursor_type=DictCursor):
        pool = self.pools.get(db_name)
        if not pool:
            await self.init_pools()
            pool = self.pools.get(db_name)

        if not pool:
            raise RuntimeError(f"Database pool '{db_name}' not available after init")

        try:
            async with pool.acquire() as conn:
                async with conn.cursor(cursor_type) as cursor:
                    await cursor.execute(query, params)
                    return await cursor.fetchall()
        except Exception as e:
            await self._log(
                contents={
                    "task": "async_fetch",
                    "db_name": db_name,
                    "error": str(e),
                    "query": query,
                }
            )
            raise

    async def async_fetch_one(self, query, db_name="default", params=None, cursor_type=DictCursor):
        pool = self.pools.get(db_name)
        if not pool:
            await self.init_pools()
            pool = self.pools.get(db_name)

        if not pool:
            raise RuntimeError(f"Database pool '{db_name}' not available after init")

        try:
            async with pool.acquire() as conn:
                async with conn.cursor(cursor_type) as cursor:
                    await cursor.execute(query, params)
                    return await cursor.fetchone()
        except Exception as e:
            await self._log(
                contents={
                    "task": "async_fetch_one",
                    "db_name": db_name,
                    "error": str(e),
                    "query": query,
                }
            )
            raise

    async def async_save(
        self,
        query,
        params=None,
        db_name="default",
        batch: bool = False,
        return_lastrowid: bool = False,
    ):
        pool = self.pools.get(db_name)
        if not pool:
            await self.init_pools()
            pool = self.pools.get(db_name)

        if not pool:
            raise RuntimeError(f"Database pool '{db_name}' not available after init")

        async with pool.acquire() as connection:
            async with connection.cursor() as cursor:
                try:
                    if batch:
                        await cursor.executemany(query, params or ())
                    else:
                        await cursor.execute(query, params or ())
                    affected_rows = cursor.rowcount
                    lastrowid = cursor.lastrowid
                    await connection.commit()
                    return lastrowid if return_lastrowid else affected_rows
                except Exception as e:
                    await connection.rollback()
                    await self._log(
                        contents={
                            "task": "async_save",
                            "db_name": db_name,
                            "error": str(e),
                            "query": query,
                        }
                    )
                    raise

    def get_pool(self, db_name="default"):
        return self.pools.get(db_name)

    def list_databases(self):
        return list(self.pools.keys())

    @asynccontextmanager
    async def transaction(self, db_name="default"):
        """
        事务上下文管理器

        用法:
            async with pool.transaction() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("INSERT ...")
                    await cursor.execute("UPDATE ...")
                # 自动 commit，异常时自动 rollback
        """
        pool = self.pools.get(db_name)
        if not pool:
            await self.init_pools()
            pool = self.pools.get(db_name)

        if not pool:
            raise RuntimeError(f"Database pool '{db_name}' not available after init")

        async with pool.acquire() as conn:
            # 关闭 autocommit，手动控制事务
            await conn.begin()
            try:
                yield conn
                await conn.commit()
            except Exception as e:
                await conn.rollback()
                await self._log(
                    contents={
                        "task": "transaction",
                        "db_name": db_name,
                        "error": str(e),
                    }
                )
                raise


__all__ = [
    "AsyncMySQLPool",
]
