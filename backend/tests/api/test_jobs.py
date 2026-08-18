from app.db import jobs as jobs_db
from app.schemas.guide import Guide
from app.schemas.requests import AnalysisRequest, UserConstraints
from tests.conftest import requires_db


def _sample_request() -> AnalysisRequest:
    return AnalysisRequest(
        keyword="성수동카페", business_type="카페", constraints=UserConstraints()
    )


@requires_db
async def test_create_and_get_job(clean_jobs_table):
    created = await jobs_db.create_job(_sample_request())
    assert created.status == "queued"
    assert created.stage is None

    fetched = await jobs_db.get_job(created.id)
    assert fetched is not None
    assert fetched.request.keyword == "성수동카페"


@requires_db
async def test_progress_updates(clean_jobs_table):
    job = await jobs_db.create_job(_sample_request())
    claimed = await jobs_db.claim_next_queued_job()
    assert claimed is not None and claimed.id == job.id

    await jobs_db.set_stage(job.id, "analyzing")
    await jobs_db.update_progress(job.id, current=7, total=20)

    fetched = await jobs_db.get_job(job.id)
    assert fetched.status == "running"
    assert fetched.stage == "analyzing"
    assert fetched.progress_current == 7
    assert fetched.progress_total == 20


@requires_db
async def test_claim_increments_attempts(clean_jobs_table):
    # G0 C-2: claim마다 attempts가 늘어야 재시도 상한을 셀 수 있다.
    job = await jobs_db.create_job(_sample_request())
    await jobs_db.claim_next_queued_job()
    await jobs_db.reap_stale_jobs(stale_minutes=999)  # 아직 stale 아님, 영향 없음

    from app.db.connection import get_conn

    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT attempts FROM jobs WHERE id = %s", (job.id,))
            (attempts,) = await cur.fetchone()
    assert attempts == 1


@requires_db
async def test_stale_recovery_when_attempts_below_max(clean_jobs_table):
    job = await jobs_db.create_job(_sample_request())
    await jobs_db.claim_next_queued_job()  # attempts=1
    await jobs_db.set_stage(job.id, "analyzing")

    from app.db.connection import get_conn

    async with get_conn() as conn:
        await conn.execute(
            "UPDATE jobs SET heartbeat_at = NOW() - INTERVAL '10 minutes' WHERE id = %s",
            (job.id,),
        )
        await conn.commit()

    recovered, killed = await jobs_db.reap_stale_jobs(stale_minutes=5, max_attempts=3)
    assert (recovered, killed) == (1, 0)

    fetched = await jobs_db.get_job(job.id)
    assert fetched.status == "queued"
    assert fetched.stage == "analyzing"  # stage는 유지 → 그 단계부터 재개 (G0 B-2 전제조건)


@requires_db
async def test_stale_job_permanently_failed_after_max_attempts(clean_jobs_table):
    # G0 C-2: attempts가 상한(3)에 도달하면 더 이상 복구하지 않고 failed로 확정한다.
    from app.db.connection import get_conn

    job = await jobs_db.create_job(_sample_request())

    async def _crash_it() -> None:
        async with get_conn() as conn:
            await conn.execute(
                "UPDATE jobs SET heartbeat_at = NOW() - INTERVAL '10 minutes' WHERE id = %s",
                (job.id,),
            )
            await conn.commit()

    # 1번째, 2번째 죽음: attempts(1, 2) < max_attempts(3) → 복구
    for _ in range(2):
        claimed = await jobs_db.claim_next_queued_job()
        assert claimed is not None
        await _crash_it()
        recovered, killed = await jobs_db.reap_stale_jobs(stale_minutes=5, max_attempts=3)
        assert (recovered, killed) == (1, 0)
        assert (await jobs_db.get_job(job.id)).status == "queued"

    # 3번째 죽음: attempts(3) >= max_attempts(3) → 영구 failed
    claimed = await jobs_db.claim_next_queued_job()
    assert claimed is not None
    await _crash_it()
    recovered, killed = await jobs_db.reap_stale_jobs(stale_minutes=5, max_attempts=3)
    assert (recovered, killed) == (0, 1)

    fetched = await jobs_db.get_job(job.id)
    assert fetched.status == "failed"
    assert fetched.error == "max attempts exceeded"


@requires_db
async def test_mark_done_stores_result(clean_jobs_table):
    job = await jobs_db.create_job(_sample_request())
    guide = Guide(
        business_type="카페",
        keyword="성수동카페",
        week_of="2026-08-04",
        shot_list=[],
        caption_drafts=[],
        audio=[],
        diagnosis=[],
        evidence_note="최근 30일 기준",
        confidence="불충분",
        caveat="표본 부족",
    )
    await jobs_db.mark_done(job.id, guide)

    fetched = await jobs_db.get_job(job.id)
    assert fetched.status == "done"
    assert fetched.result is not None
    assert fetched.result.confidence == "불충분"


@requires_db
async def test_cancel_job_returns_none_when_already_done(clean_jobs_table):
    # G0 D: 이미 끝난 잡을 취소하려는 경합 상황. 라우트는 이 None을 409로 변환한다.
    job = await jobs_db.create_job(_sample_request())
    guide = Guide(
        business_type="카페",
        keyword="성수동카페",
        week_of="2026-08-04",
        shot_list=[],
        caption_drafts=[],
        audio=[],
        diagnosis=[],
        evidence_note="최근 30일 기준",
        confidence="충분",
        caveat=None,
    )
    await jobs_db.mark_done(job.id, guide)

    cancelled = await jobs_db.cancel_job(job.id)
    assert cancelled is None
