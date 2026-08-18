"""JobStage 'analyzing'. VLM 샷 분석. docs/03-pipeline.md의 analyzing 참조 (P2 구현).

frames.py가 남긴 shot_segments(t_start/t_end/idx, VLM 필드는 NULL)를 읽어 대표 프레임을
VLM에 보내고, 같은 행을 UPDATE한다. 릴스 요약은 reel_analyses에 커밋한다.
"""

import logging
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from app.db import jobs as jobs_db
from app.db import reel_analyses as reel_analyses_db
from app.db import shot_segments as shot_segments_db
from app.pipeline.score import select_target_reels
from app.providers import get_vision_provider
from app.schemas.collect import RawReel

logger = logging.getLogger(__name__)

# docs analyzing 2번: len(shots) != len(cuts)면 1회 재시도, 그래도 다르면 스킵.
VLM_MISMATCH_MAX_RETRIES = 1


def _frame_dir(job_id: str, reel_code: str) -> Path:
    """frames.py가 쓴 것과 동일한 경로 관례 — job_id/reel_code로 고정."""
    return Path(tempfile.gettempdir()) / "buja_frames" / job_id / reel_code


async def _process_reel(reel: RawReel, job_id: str) -> None:
    pending = await shot_segments_db.get_pending(reel.code)
    if not pending:
        logger.info("릴스 %s는 분석할 shot 없음(이미 완료됐거나 preparing 실패) — 스킵", reel.code)
        return

    frame_dir = _frame_dir(job_id, reel.code)
    frame_paths = [frame_dir / f"frame_{row['idx']:02d}.jpg" for row in pending]
    missing = [p for p in frame_paths if not p.exists()]
    if missing:
        logger.warning("릴스 %s 프레임 파일 없음(%s) — 스킵", reel.code, missing)
        return

    provider = get_vision_provider()
    analysis = await provider.analyze_shots(frame_paths, reel.caption)
    if len(analysis.shots) != len(pending):
        logger.warning(
            "릴스 %s VLM 샷 개수 불일치(%d != %d) — 1회 재시도",
            reel.code,
            len(analysis.shots),
            len(pending),
        )
        analysis = await provider.analyze_shots(frame_paths, reel.caption)
        if len(analysis.shots) != len(pending):
            logger.error("릴스 %s 재시도에도 샷 개수 불일치 — 분석 스킵(analyzing 2번)", reel.code)
            return

    model_name = type(provider).__name__
    for shot, row in zip(analysis.shots, pending, strict=True):
        await shot_segments_db.update_vlm_fields(reel.code, row["idx"], shot, model_name)

    durations = [row["t_end"] - row["t_start"] for row in pending]
    await reel_analyses_db.upsert(
        reel_code=reel.code,
        cut_count=len(pending),
        avg_shot_sec=sum(durations) / len(durations),
        first_shot_sec=durations[0],
        caption_hooks=analysis.caption_hooks,
        color_tone=analysis.color_tone,
        subtitle_position=analysis.subtitle_position,
        summary=analysis.summary,
        model=model_name,
        analyzed_at=datetime.now(UTC),
    )

    # docs analyzing 4번: mp4 즉시 삭제. 프레임 이미지도 다 썼으니 같이 정리한다.
    shutil.rmtree(frame_dir, ignore_errors=True)


async def run(job_id: str) -> None:
    job = await jobs_db.get_job(UUID(job_id))
    assert job is not None, f"job {job_id} not found"
    keyword = job.request.keyword
    business_type = job.request.business_type

    targets = await select_target_reels(keyword, business_type)
    logger.info("job %s analyzing 대상 %d개", job_id, len(targets))

    for reel in targets:
        try:
            await _process_reel(reel, job_id)
        except Exception:  # noqa: BLE001 — 릴스 1개 실패가 전체를 막으면 안 된다 (docs 실패 원칙)
            logger.exception("릴스 %s 분석 실패 — 로그만 남기고 계속", reel.code)
