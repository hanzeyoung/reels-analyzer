"""JobStage 'scoring'. docs/03-pipeline.md의 score 참조.

`run()`은 P1에서 구현한다. 아래 순수 함수들은 지표 계산·버킷 분류·트랙 선정 로직이다
(G0 지시서 4단계 — 외부 API도 DB도 필요 없다).
"""

import logging
from uuid import UUID

from app.db import accounts as accounts_db
from app.db import jobs as jobs_db
from app.db import reel_metrics as reel_metrics_db
from app.db import reels as reels_db
from app.schemas.collect import Account, RawReel
from app.schemas.common import Bucket, Track
from app.schemas.score import ReelMetrics, ScoredReel

logger = logging.getLogger(__name__)

# ROADMAP/docs 어디에도 고정 숫자가 없어 P1 진행 중 사용자 확인 후 확정(2026-08-14).
# comparing 단계 가드(high_n/low_n >= 15)를 여유 있게 넘기도록 20으로 잡았다.
TRACK_TOP_N = 20

# docs/02-contracts.md "버킷 경계 (초기 고정값)" 표. "B1 ~1,000" "B2 1,000~10,000"처럼
# 경계값 자체의 포함/미포함이 명시돼 있지 않아서 하한 포함·상한 미포함으로 판단했다
# (표준적인 구간 관례). 업종 200건 누적 후 분위수로 교체되기 전까지는 이 고정값을 쓴다.
BUCKET_UPPER_BOUNDS: dict[str, int] = {"B1": 1_000, "B2": 10_000, "B3": 100_000}


def calculate_metrics(reel: RawReel, account: Account) -> ReelMetrics:
    """docs/03-pipeline.md score 1~3번. 0으로 나누기 방지는 `max(count, 1)`."""
    play = max(reel.play_count, 1)
    engagement_rate = (reel.like_count + reel.comment_count + reel.share_count) / play
    share_rate = reel.share_count / play
    reach_multiple = None
    if account.follower_count is not None:
        reach_multiple = reel.play_count / max(account.follower_count, 1)
    return ReelMetrics(
        engagement_rate=engagement_rate, share_rate=share_rate, reach_multiple=reach_multiple
    )


def classify_bucket(follower_count: int | None) -> Bucket:
    """docs/02-contracts.md 버킷 경계. 팔로워 없으면 'unknown' (docs/03-pipeline.md score 4번)."""
    if follower_count is None:
        return "unknown"
    if follower_count < BUCKET_UPPER_BOUNDS["B1"]:
        return "B1"
    if follower_count < BUCKET_UPPER_BOUNDS["B2"]:
        return "B2"
    if follower_count < BUCKET_UPPER_BOUNDS["B3"]:
        return "B3"
    return "B4"


def build_scored_reel(reel: RawReel, account: Account) -> ScoredReel:
    """지표 계산 + 버킷 분류를 묶은 편의 함수. track은 선정 단계 전이라 None."""
    metrics = calculate_metrics(reel, account)
    bucket = classify_bucket(account.follower_count)
    return ScoredReel(reel=reel, account=account, metrics=metrics, bucket=bucket, track=None)


def _with_track(scored: ScoredReel, track: Track) -> ScoredReel:
    return scored.model_copy(update={"track": track})


def select_breakout(
    scored_reels: list[ScoredReel], *, top_n: int, follower_data_available: bool
) -> list[ScoredReel]:
    """B1+B2 중 `reach_multiple` 상위 `top_n`. 팔로워 데이터가 없으면 버킷 구분 없이
    전체에서 `engagement_rate` 상위 (docs/03-pipeline.md score 5번,
    follower_data_available=False 분기).

    `top_n`은 문서에 고정 숫자가 없다(ROADMAP P1도 "N개"로만 표기) — 실제 개수는
    P1에서 수집량·팔로워 분포를 보고 정한다. 여기서는 "상위 N개를 고르는 방법"만 구현한다.
    """
    if not follower_data_available:
        ranked = sorted(scored_reels, key=lambda r: r.metrics.engagement_rate, reverse=True)
    else:
        pool = [r for r in scored_reels if r.bucket in ("B1", "B2")]
        ranked = sorted(pool, key=lambda r: r.metrics.reach_multiple or 0.0, reverse=True)
    return [_with_track(r, "breakout") for r in ranked[:top_n]]


def select_big_account(
    scored_reels: list[ScoredReel], *, top_n: int, follower_data_available: bool
) -> list[ScoredReel]:
    """B4 중 `play_count` 상위 `top_n`. 팔로워 데이터가 없으면 빈 리스트
    (docs/03-pipeline.md score 5번 — big_account 트랙 비활성)."""
    if not follower_data_available:
        return []
    pool = [r for r in scored_reels if r.bucket == "B4"]
    ranked = sorted(pool, key=lambda r: r.reel.play_count, reverse=True)
    return [_with_track(r, "big_account") for r in ranked[:top_n]]


def select_control(
    scored_reels: list[ScoredReel],
    breakout: list[ScoredReel],
    *,
    top_n: int,
    follower_data_available: bool,
) -> list[ScoredReel]:
    """breakout과 같은 버킷(들)의 하위 `top_n`. breakout에 이미 뽑힌 릴스는 제외한다
    (docs/03-pipeline.md score 5번: "control — breakout과 같은 버킷의 하위").
    정렬 기준은 breakout 선정에 쓴 지표(reach_multiple 또는 engagement_rate)를 그대로 쓴다."""
    breakout_codes = {r.reel.code for r in breakout}
    breakout_buckets = {r.bucket for r in breakout}
    pool = [
        r
        for r in scored_reels
        if r.bucket in breakout_buckets and r.reel.code not in breakout_codes
    ]
    if not follower_data_available:
        ranked = sorted(pool, key=lambda r: r.metrics.engagement_rate)
    else:
        ranked = sorted(pool, key=lambda r: r.metrics.reach_multiple or 0.0)
    return [_with_track(r, "control") for r in ranked[:top_n]]


async def compute_tracks(
    keyword: str, business_type: str
) -> tuple[list[ScoredReel], list[ScoredReel], list[ScoredReel]]:
    """(breakout, big_account, control) `ScoredReel` 리스트를 그대로 반환한다.

    reel_metrics에 track 컬럼이 없어(재계산 가능한 값을 굳이 저장 안 함) score.run()이
    끝난 뒤에도 이 값은 어디에도 저장되지 않는다 — frames.py/analyze.py/compare.py가
    각자 필요할 때 이 함수로 다시 계산한다.
    """
    reels = await reels_db.get_by_keyword(keyword, business_type)
    usernames = sorted({reel.username for reel in reels})
    accounts = await accounts_db.get_many(usernames)
    scored = [build_scored_reel(reel, accounts[reel.username]) for reel in reels]
    follower_data_available = any(a.follower_count is not None for a in accounts.values())

    breakout = select_breakout(
        scored, top_n=TRACK_TOP_N, follower_data_available=follower_data_available
    )
    big_account = select_big_account(
        scored, top_n=TRACK_TOP_N, follower_data_available=follower_data_available
    )
    control = select_control(
        scored, breakout, top_n=TRACK_TOP_N, follower_data_available=follower_data_available
    )
    return breakout, big_account, control


async def select_target_reels(keyword: str, business_type: str) -> list[RawReel]:
    """breakout+big_account+control 대상만 고른다 (docs preparing: "이 대상만 다운로드")."""
    breakout, big_account, control = await compute_tracks(keyword, business_type)

    seen: set[str] = set()
    targets: list[RawReel] = []
    for scored_reel in [*breakout, *big_account, *control]:
        if scored_reel.reel.code in seen:
            continue
        seen.add(scored_reel.reel.code)
        targets.append(scored_reel.reel)
    return targets


async def run(job_id: str) -> None:
    job = await jobs_db.get_job(UUID(job_id))
    assert job is not None, f"job {job_id} not found"
    keyword = job.request.keyword
    business_type = job.request.business_type

    reels = await reels_db.get_by_keyword(keyword, business_type)
    usernames = sorted({reel.username for reel in reels})
    accounts = await accounts_db.get_many(usernames)

    scored = [build_scored_reel(reel, accounts[reel.username]) for reel in reels]
    await reel_metrics_db.upsert_many(scored)

    targets = await select_target_reels(keyword, business_type)
    logger.info(
        "job %s 스코어링 완료: reels=%d, preparing 대상(breakout+big_account+control)=%d",
        job_id,
        len(reels),
        len(targets),
    )
