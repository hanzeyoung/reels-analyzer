"""bucket_configs 테이블 CRUD. docs/02-contracts.md: "해당 업종 누적 200건 초과 시
업종별 33/66 분위수로 교체. 경계는 bucket_configs에 저장." 테이블/초기 seed는 0001에서
이미 만들어짐(P0) — 여기선 조회/저장만 다룬다.
"""

from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.db.connection import get_conn


async def get_boundaries(business_type: str) -> dict[str, int]:
    """`business_type` 전용 경계가 있으면(percentile로 교체된 것) 최신값을 쓰고,
    없으면 전역 기본값(business_type IS NULL, source='fixed') 행으로 fallback한다."""
    async with get_conn() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT boundaries FROM bucket_configs
                WHERE business_type = %s
                ORDER BY created_at DESC LIMIT 1
                """,
                (business_type,),
            )
            row = await cur.fetchone()
            if row is None:
                await cur.execute(
                    """
                    SELECT boundaries FROM bucket_configs
                    WHERE business_type IS NULL
                    ORDER BY created_at DESC LIMIT 1
                    """
                )
                row = await cur.fetchone()
    assert row is not None, "bucket_configs에 전역 기본값(business_type IS NULL)이 없다"
    return _coerce_boundaries(row["boundaries"])


def _coerce_boundaries(raw: dict[str, Any]) -> dict[str, int]:
    return {k: int(v) for k, v in raw.items()}


async def save_percentile_boundaries(
    business_type: str, boundaries: dict[str, int], sample_size: int
) -> None:
    async with get_conn() as conn:
        await conn.execute(
            """
            INSERT INTO bucket_configs (business_type, boundaries, source, sample_size)
            VALUES (%s, %s, 'percentile', %s)
            """,
            (business_type, Jsonb(boundaries), sample_size),
        )
        await conn.commit()
