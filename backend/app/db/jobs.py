"""jobs 테이블 CRUD. 워커·API가 공유하는 유일한 잡 접근 경로."""

from typing import Any
from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.db.connection import get_conn
from app.schemas.common import JobStage
from app.schemas.guide import Guide
from app.schemas.job import Job
from app.schemas.requests import AnalysisRequest


def _row_to_job(row: dict[str, Any]) -> Job:
    return Job(
        id=row["id"],
        status=row["status"],
        stage=row["stage"],
        progress_current=row["progress_current"],
        progress_total=row["progress_total"],
        error=row["error"],
        heartbeat_at=row["heartbeat_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        request=AnalysisRequest.model_validate(row["request"]),
        result=Guide.model_validate(row["result"]) if row["result"] else None,
    )


async def create_job(request: AnalysisRequest) -> Job:
    async with get_conn() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                INSERT INTO jobs (status, request)
                VALUES ('queued', %s)
                RETURNING *
                """,
                (Jsonb(request.model_dump(mode="json")),),
            )
            row = await cur.fetchone()
            await conn.commit()
    assert row is not None
    return _row_to_job(row)


async def get_job(job_id: UUID) -> Job | None:
    async with get_conn() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("SELECT * FROM jobs WHERE id = %s", (job_id,))
            row = await cur.fetchone()
    return _row_to_job(row) if row else None


async def list_jobs(limit: int = 20) -> list[Job]:
    async with get_conn() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT %s", (limit,)
            )
            rows = await cur.fetchall()
    return [_row_to_job(row) for row in rows]


async def claim_next_queued_job() -> Job | None:
    """queued 잡 하나를 running으로 바꾸며 집는다. attempts를 1 증가시킨다 (G0 C-2).

    `created_at`만으로 정렬하면 같은 마이크로초에 생성된 두 잡의 클레임 순서가
    이론상 비결정적일 수 있어(id가 랜덤 UUID) `id`를 2차 정렬 키로 추가했다(2026-08-20).
    **주의**: `tests/worker/test_loop.py`가 이전에 flaky했던 진짜 원인은 이게 아니었다 —
    같은 원격 Supabase DB를 폴링하는 실제 워커 프로세스(`make dev`)가 백그라운드에서
    계속 살아있는 상태로 pytest를 돌리면, 테스트가 만든 job을 그 워커가 가로채 처리해버려
    결과가 매번 달라졌다(실측으로 원인 특정, `make dev` 종료 후 3회 연속 통과 확인).
    **`make check`/pytest는 `make dev`가 안 떠 있는 상태에서 돌려야 한다** — 테스트가
    별도 DB로 격리돼 있지 않고 실제 개발 DB를 그대로 쓰기 때문.
    """
    async with get_conn() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                UPDATE jobs SET status = 'running', heartbeat_at = NOW(),
                                attempts = attempts + 1
                WHERE id = (
                    SELECT id FROM jobs WHERE status = 'queued'
                    ORDER BY created_at ASC, id ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                RETURNING *
                """
            )
            row = await cur.fetchone()
            await conn.commit()
    return _row_to_job(row) if row else None


async def set_stage(job_id: UUID, stage: JobStage) -> None:
    async with get_conn() as conn:
        await conn.execute(
            "UPDATE jobs SET stage = %s, heartbeat_at = NOW() WHERE id = %s",
            (stage, job_id),
        )
        await conn.commit()


async def update_progress(job_id: UUID, current: int, total: int) -> None:
    async with get_conn() as conn:
        await conn.execute(
            """
            UPDATE jobs SET progress_current = %s, progress_total = %s, heartbeat_at = NOW()
            WHERE id = %s
            """,
            (current, total, job_id),
        )
        await conn.commit()


async def heartbeat(job_id: UUID) -> None:
    async with get_conn() as conn:
        await conn.execute("UPDATE jobs SET heartbeat_at = NOW() WHERE id = %s", (job_id,))
        await conn.commit()


async def mark_done(job_id: UUID, result: Guide | None = None) -> None:
    async with get_conn() as conn:
        await conn.execute(
            """
            UPDATE jobs SET status = 'done', stage = NULL, result = %s, heartbeat_at = NOW()
            WHERE id = %s
            """,
            (Jsonb(result.model_dump(mode="json")) if result else None, job_id),
        )
        await conn.commit()


async def mark_failed(job_id: UUID, error: str) -> None:
    async with get_conn() as conn:
        await conn.execute(
            "UPDATE jobs SET status = 'failed', error = %s WHERE id = %s",
            (error, job_id),
        )
        await conn.commit()


async def cancel_job(job_id: UUID) -> Job | None:
    """queued/running만 취소 가능. done이면 None 반환(호출부가 409 처리)."""
    async with get_conn() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                UPDATE jobs SET status = 'failed', error = 'cancelled by user'
                WHERE id = %s AND status IN ('queued', 'running')
                RETURNING *
                """,
                (job_id,),
            )
            row = await cur.fetchone()
            await conn.commit()
    return _row_to_job(row) if row else None


DEFAULT_MAX_ATTEMPTS = 3


async def reap_stale_jobs(
    stale_minutes: int, max_attempts: int = DEFAULT_MAX_ATTEMPTS
) -> tuple[int, int]:
    """heartbeat_at이 stale_minutes 초과한 running 잡을 처리한다.

    stage는 유지한 채 queued로 되돌려 그 단계부터 재개하게 한다(B-2).
    단 attempts가 max_attempts 이상이면 더 복구하지 않고 영구 failed 처리한다(C-2) —
    워커를 죽이는 잡이 reaper에 의해 무한 부활하는 걸 막는다.

    Returns: (복구된 개수, 영구 failed 처리된 개수)
    """
    async with get_conn() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                UPDATE jobs SET status = 'failed', error = 'max attempts exceeded'
                WHERE status = 'running'
                  AND heartbeat_at < NOW() - (%s || ' minutes')::interval
                  AND attempts >= %s
                RETURNING id
                """,
                (stale_minutes, max_attempts),
            )
            failed_rows = await cur.fetchall()

            await cur.execute(
                """
                UPDATE jobs SET status = 'queued'
                WHERE status = 'running'
                  AND heartbeat_at < NOW() - (%s || ' minutes')::interval
                  AND attempts < %s
                RETURNING id
                """,
                (stale_minutes, max_attempts),
            )
            recovered_rows = await cur.fetchall()
            await conn.commit()
    return len(recovered_rows), len(failed_rows)
