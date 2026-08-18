"""DB 커넥션 풀. 호출마다 새 연결을 여는 대신 풀에서 빌려 쓴다 (G0 B-4).

Supabase는 네트워크 너머고 연결 수 제한이 있다 — heartbeat 한 번마다 TCP+TLS
핸드셰이크를 새로 하는 건 낭비다. FastAPI는 lifespan에서, 워커는 시작 시
`init_pool()`을 호출해 풀을 연다.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg
from psycopg_pool import AsyncConnectionPool

from app.config import get_settings

_pool: AsyncConnectionPool | None = None


async def init_pool(min_size: int = 1, max_size: int = 5) -> None:
    global _pool
    if _pool is not None:
        return
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL이 설정되지 않았다")
    pool = AsyncConnectionPool(
        settings.database_url, min_size=min_size, max_size=max_size, open=False
    )
    await pool.open()
    _pool = pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def get_conn() -> AsyncIterator[psycopg.AsyncConnection]:
    if _pool is None:
        raise RuntimeError("DB 풀이 초기화되지 않았다. init_pool()을 먼저 호출해라")
    async with _pool.connection() as conn:
        yield conn
