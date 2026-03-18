import asyncpg
import os
import asyncio

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await _create_pool()
    return _pool


async def _create_pool() -> asyncpg.Pool:
    database_url = os.getenv("DATABASE_URL")
    retries = 10
    last_error = None
    while retries > 0:
        try:
            pool = await asyncpg.create_pool(
                dsn=database_url,
                min_size=2,
                max_size=20,
            )
            print("✅ Database connection pool established")
            return pool
        except Exception as e:
            last_error = e
            retries -= 1
            print(f"⏳ Waiting for database... ({retries} retries left): {e}")
            await asyncio.sleep(3)
    raise RuntimeError(f"❌ Could not connect to database: {last_error}")


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
