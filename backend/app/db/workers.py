"""워커 프로세스 자체의 heartbeat. jobs.heartbeat_at(잡 생존)과는 목적이 다르다 (G0 A-2)."""

from datetime import datetime

from psycopg.rows import dict_row

from app.db.connection import get_conn

WORKER_ALIVE_WINDOW_SECONDS = 60


async def touch_worker(worker_id: str) -> None:
    async with get_conn() as conn:
        await conn.execute(
            """
            INSERT INTO workers (id, last_seen_at) VALUES (%s, NOW())
            ON CONFLICT (id) DO UPDATE SET last_seen_at = NOW()
            """,
            (worker_id,),
        )
        await conn.commit()


async def latest_seen_at() -> datetime | None:
    async with get_conn() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("SELECT MAX(last_seen_at) AS seen FROM workers")
            row = await cur.fetchone()
    return row["seen"] if row else None


async def any_worker_alive(within_seconds: int = WORKER_ALIVE_WINDOW_SECONDS) -> bool:
    async with get_conn() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM workers
                    WHERE last_seen_at > NOW() - (%s || ' seconds')::interval
                ) AS alive
                """,
                (within_seconds,),
            )
            row = await cur.fetchone()
    return bool(row["alive"]) if row else False
