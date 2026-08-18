"""accounts 테이블 CRUD. 30일 캐시 판정은 여기 get_cached()가 fetched_at 기준으로 한다."""

from psycopg.rows import dict_row

from app.db.connection import get_conn
from app.schemas.collect import Account

CACHE_DAYS = 30


async def get_cached(usernames: list[str], within_days: int = CACHE_DAYS) -> dict[str, Account]:
    """fetched_at이 within_days일 이내인 것만 캐시 히트로 본다 (docs/03-pipeline.md collect 7)"""
    if not usernames:
        return {}
    async with get_conn() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT username, follower_count, fetched_at FROM accounts
                WHERE username = ANY(%s)
                  AND fetched_at IS NOT NULL
                  AND fetched_at > NOW() - (%s || ' days')::interval
                """,
                (usernames, within_days),
            )
            rows = await cur.fetchall()
    return {row["username"]: Account.model_validate(row) for row in rows}


async def get_many(usernames: list[str]) -> dict[str, Account]:
    """신선도 무관하게 저장된 그대로 조회한다 (score 단계 — 캐시 판정은 collect 몫)."""
    if not usernames:
        return {}
    async with get_conn() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT username, follower_count, fetched_at FROM accounts
                WHERE username = ANY(%s)
                """,
                (usernames,),
            )
            rows = await cur.fetchall()
    return {row["username"]: Account.model_validate(row) for row in rows}


async def upsert_many(accounts: list[Account]) -> None:
    if not accounts:
        return
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            for account in accounts:
                await cur.execute(
                    """
                    INSERT INTO accounts (username, follower_count, fetched_at)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (username) DO UPDATE
                        SET follower_count = EXCLUDED.follower_count,
                            fetched_at = EXCLUDED.fetched_at
                    """,
                    (account.username, account.follower_count, account.fetched_at),
                )
        await conn.commit()
