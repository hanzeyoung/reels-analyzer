"""guides 테이블 CRUD. generating 단계가 최종 산출물을 커밋한다."""

from datetime import date
from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.db.connection import get_conn
from app.schemas.guide import Guide


async def create(
    job_id: UUID, business_type: str, keyword: str, week_of: date, guide: Guide
) -> None:
    async with get_conn() as conn:
        await conn.execute(
            """
            INSERT INTO guides (job_id, business_type, keyword, week_of, payload, confidence)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                job_id,
                business_type,
                keyword,
                week_of,
                Jsonb(guide.model_dump(mode="json")),
                guide.confidence,
            ),
        )
        await conn.commit()


async def get_latest_by_job(job_id: UUID) -> Guide | None:
    """worker/loop.py가 잡을 done 처리할 때 jobs.result에 채워 넣을 값을 여기서 읽는다."""
    async with get_conn() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT payload FROM guides WHERE job_id = %s ORDER BY created_at DESC LIMIT 1",
                (job_id,),
            )
            row = await cur.fetchone()
    return Guide.model_validate(row["payload"]) if row else None
