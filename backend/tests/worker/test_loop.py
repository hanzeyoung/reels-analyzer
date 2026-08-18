import asyncio
from unittest.mock import AsyncMock, patch

from app.db import jobs as jobs_db
from app.schemas.requests import AnalysisRequest, UserConstraints
from app.worker.loop import process_job, run_forever
from tests.conftest import requires_db


def _sample_request() -> AnalysisRequest:
    return AnalysisRequest(
        keyword="성수동카페", business_type="카페", constraints=UserConstraints()
    )


@requires_db
async def test_process_job_runs_all_stages_to_done(clean_jobs_table):
    job = await jobs_db.create_job(_sample_request())
    claimed = await jobs_db.claim_next_queued_job()

    await process_job(claimed)

    finished = await jobs_db.get_job(job.id)
    assert finished.status == "done"
    assert finished.stage is None


@requires_db
async def test_process_job_resumes_from_saved_stage(clean_jobs_table):
    # G0 B-2: stage가 저장돼 있으면 그 단계부터 재개한다. 앞선 단계는 다시 호출되면 안 된다.
    job = await jobs_db.create_job(_sample_request())
    await jobs_db.claim_next_queued_job()
    await jobs_db.set_stage(job.id, "analyzing")
    resumed = await jobs_db.get_job(job.id)
    assert resumed.stage == "analyzing"

    with (
        patch("app.worker.loop.collect.run", new=AsyncMock()) as collect_run,
        patch("app.worker.loop.score.run", new=AsyncMock()) as score_run,
        patch("app.worker.loop.frames.run", new=AsyncMock()) as frames_run,
        patch("app.worker.loop.analyze.run", new=AsyncMock()) as analyze_run,
        patch("app.worker.loop.compare.run", new=AsyncMock()) as compare_run,
        patch("app.worker.loop.guide.run", new=AsyncMock()) as guide_run,
    ):
        await process_job(resumed)

    collect_run.assert_not_called()
    score_run.assert_not_called()
    frames_run.assert_not_called()
    analyze_run.assert_called_once()
    compare_run.assert_called_once()
    guide_run.assert_called_once()

    finished = await jobs_db.get_job(job.id)
    assert finished.status == "done"


@requires_db
async def test_process_job_sends_background_heartbeat_during_long_stage(clean_jobs_table):
    # G0 B-3: 단계 하나가 오래 걸려도 heartbeat가 백그라운드에서 주기적으로 갱신돼야 한다.
    await jobs_db.create_job(_sample_request())
    claimed = await jobs_db.claim_next_queued_job()

    async def _slow_stage(job_id: str) -> None:
        await asyncio.sleep(0.3)

    heartbeat_spy = AsyncMock(wraps=jobs_db.heartbeat)
    with (
        patch("app.worker.loop.analyze.run", new=_slow_stage),
        patch("app.worker.loop.jobs_db.heartbeat", new=heartbeat_spy),
    ):
        await process_job(claimed, heartbeat_interval=0.05)

    assert heartbeat_spy.call_count >= 3  # 0.3s / 0.05s 간격이면 최소 여러 번 불려야 한다


@requires_db
async def test_run_forever_survives_stage_failure_and_claims_next_job(clean_jobs_table):
    # G0 C-3: run_forever를 실제로 몇 사이클 구동해서 예외 처리 코드를 직접 검증한다.
    # (기존 테스트는 try/except를 테스트 코드가 대신 실행해서 run_forever 자체는 검증하지 못했다.)
    job_a = await jobs_db.create_job(_sample_request())
    job_b = await jobs_db.create_job(_sample_request())

    with patch(
        "app.worker.loop.score.run",
        new=AsyncMock(side_effect=[RuntimeError("boom"), None]),
    ):
        # iteration 1: job_a claim → score 단계에서 예외 → failed, 루프는 계속 산다
        # iteration 2: job_b claim → 끝까지 성공 → done
        await run_forever(poll_interval=0, stale_minutes=5, iterations=2)

    failed = await jobs_db.get_job(job_a.id)
    assert failed.status == "failed"
    assert failed.error == "boom"

    done = await jobs_db.get_job(job_b.id)
    assert done.status == "done"
