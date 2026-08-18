"""워커 프로세스 본체. queued 잡을 집어 저장된 stage부터 순서대로 실행한다.

모듈명(collect/score/frames/analyze/compare/guide) ↔ JobStage 매핑
(G0 A-1: 원래 downloading 하나로 묶여 있던 것을 계약 충돌로 재정의):
    collect.py -> collecting   score.py  -> scoring
    frames.py  -> preparing    (mp4 다운로드 + ffmpeg 컷 추출, 로컬·결정론적)
    analyze.py -> analyzing    (VLM 호출, 과금·비결정론적)
    compare.py -> comparing    guide.py  -> generating
"""

import asyncio
import contextlib
import logging
import os
import socket
from types import ModuleType
from uuid import UUID

from app.db import guides as guides_db
from app.db import jobs as jobs_db
from app.db import workers as workers_db
from app.pipeline import analyze, collect, compare, frames, guide, score
from app.schemas.common import JobStage
from app.schemas.job import Job

logger = logging.getLogger(__name__)

# 모듈 객체 자체를 담아둔다(함수를 미리 꺼내 담지 않는다) — 매 호출마다 `module.run`을
# 새로 조회해야 테스트에서 `patch("app.worker.loop.collect.run", ...)`가 실제로 먹힌다.
STAGE_MODULES: list[tuple[JobStage, ModuleType]] = [
    ("collecting", collect),
    ("scoring", score),
    ("preparing", frames),
    ("analyzing", analyze),
    ("comparing", compare),
    ("generating", guide),
]

_STAGE_INDEX: dict[JobStage, int] = {stage: i for i, (stage, _) in enumerate(STAGE_MODULES)}

HEARTBEAT_INTERVAL_SECONDS = 30.0


def default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def _resume_index(job: Job) -> int:
    """job.stage가 저장돼 있으면 그 단계부터 재개, 없으면 처음부터 (G0 B-2)."""
    if job.stage is None:
        return 0
    return _STAGE_INDEX[job.stage]


async def _heartbeat_loop(job_id: UUID, interval: float) -> None:
    """긴 단계(예: Apify 폴링) 도중에도 heartbeat_at이 stale로 오판되지 않게
    단계 완료를 기다리지 않고 백그라운드에서 주기적으로 갱신한다 (G0 B-3)."""
    while True:
        await asyncio.sleep(interval)
        await jobs_db.heartbeat(job_id)


async def process_job(job: Job, heartbeat_interval: float = HEARTBEAT_INTERVAL_SECONDS) -> None:
    hb_task = asyncio.create_task(_heartbeat_loop(job.id, heartbeat_interval))
    try:
        for stage, module in STAGE_MODULES[_resume_index(job) :]:
            await jobs_db.set_stage(job.id, stage)
            await module.run(str(job.id))
        # guide.run()(generating)이 `guides` 테이블에 커밋한 걸 다시 읽어서 jobs.result에
        # 채운다 — pipeline 모듈은 job_id만 받고 값을 반환하지 않는 기존 관례를 그대로
        # 지키면서(P0부터 일관됨), 최종 결과를 jobs에 붙이는 책임은 오케스트레이터인
        # 여기(process_job)가 진다. 이전엔 이 조회 없이 무조건 result=None으로
        # mark_done했었다 — guide.py가 빈 스텁이던 P0~P3에서는 문제가 안 됐지만
        # guide.py가 실제로 Guide를 만드는 지금부터는 고쳐야 했다(판단, 2026-08-14).
        guide_result = await guides_db.get_latest_by_job(job.id)
        await jobs_db.mark_done(job.id, result=guide_result)
    finally:
        hb_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await hb_task


async def run_forever(
    poll_interval: float = 2.0,
    stale_minutes: int = 5,
    worker_id: str | None = None,
    iterations: int | None = None,
) -> None:
    """메인 루프. `iterations`가 None이면 무한 루프(프로덕션),
    정수면 그만큼만 돌고 반환한다 (테스트에서 실제 루프 코드를 유한 횟수로 구동하기 위함)."""
    resolved_worker_id = worker_id or default_worker_id()
    logger.info("worker loop 시작 (id=%s)", resolved_worker_id)

    count = 0
    while iterations is None or count < iterations:
        count += 1

        # 잡 유무와 무관하게 워커 자신의 생존을 알린다 (G0 A-2)
        await workers_db.touch_worker(resolved_worker_id)

        recovered, killed = await jobs_db.reap_stale_jobs(stale_minutes)
        if recovered:
            logger.warning("stale 잡 %d개 queued로 복구", recovered)
        if killed:
            logger.warning("stale 잡 %d개 재시도 상한 초과로 failed 처리", killed)

        job = await jobs_db.claim_next_queued_job()
        if job is None:
            await asyncio.sleep(poll_interval)
            continue

        try:
            await process_job(job)
        except Exception as exc:  # noqa: BLE001 — 한 잡의 실패가 워커를 죽이면 안 된다
            logger.exception("job %s 실패", job.id)
            try:
                await jobs_db.mark_failed(job.id, str(exc))
            except Exception:  # noqa: BLE001 — DB 일시 장애로 워커 자체가 죽으면 안 된다
                logger.exception("job %s의 실패 기록 자체가 실패함", job.id)
            continue
