"""JobStage 'diagnosing' (P5, 내 릴스 진단). docs/03-pipeline.md의 diagnosing 참조.

`my_reel_url`이 없으면 즉시 스킵한다. 있으면:
1. Apify로 URL 하나만 조회
2. `reels`에 `is_my_reel=true`로 커밋 (키워드 풀 조회에서 항상 제외됨)
3. frames.process_reel/analyze.process_reel을 그대로 재사용해 컷 분해 + VLM 샷 서술

comparing과는 순서상 독립적이다(풀 비교와 무관) — generating이 이 결과를 읽는다.
"""

import logging
from uuid import UUID

from app.db import accounts as accounts_db
from app.db import jobs as jobs_db
from app.db import reels as reels_db
from app.pipeline import analyze, frames
from app.schemas.collect import Account

logger = logging.getLogger(__name__)


async def run(job_id: str) -> None:
    # 순환 임포트 회피(다른 pipeline 모듈과 동일 패턴)
    from app.providers import get_collect_provider

    job = await jobs_db.get_job(UUID(job_id))
    assert job is not None, f"job {job_id} not found"
    my_reel_url = job.request.my_reel_url
    if my_reel_url is None:
        logger.info("job %s my_reel_url 없음 — diagnosing 스킵", job_id)
        return

    try:
        provider = get_collect_provider()
        raw = await provider.fetch_reel_by_url(my_reel_url)
        if raw is None:
            logger.warning(
                "job %s 내 릴스 조회 실패(삭제/비공개/영상 아님) — 진단 없이 진행", job_id
            )
            return

        cached = await accounts_db.get_cached([raw.username])
        if raw.username not in cached:
            await accounts_db.upsert_many([Account(username=raw.username)])

        await reels_db.upsert_many(
            [raw], keyword=job.request.keyword, business_type=job.request.business_type,
            is_my_reel=True,
        )
        await frames.process_reel(raw, job_id)
        await analyze.process_reel(raw, job_id)
    except Exception:  # noqa: BLE001 — 실패해도 잡 전체를 막지 않는다(docs 실패 원칙)
        logger.exception("job %s 내 릴스 진단 실패 — 진단 없이 진행", job_id)
