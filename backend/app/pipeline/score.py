"""JobStage 'scoring'. docs/03-pipeline.md의 score 참조.

`run()`은 P1에서 구현한다. 아래 순수 함수들은 지표 계산·버킷 분류·트랙 선정 로직이다
(G0 지시서 4단계 — 외부 API도 DB도 필요 없다).
"""

import logging
import statistics
from collections import Counter
from uuid import UUID

from app.db import accounts as accounts_db
from app.db import bucket_configs as bucket_configs_db
from app.db import jobs as jobs_db
from app.db import reel_metrics as reel_metrics_db
from app.db import reels as reels_db
from app.schemas.collect import Account, RawReel
from app.schemas.common import Bucket, Track
from app.schemas.score import ReelMetrics, ScoredReel

logger = logging.getLogger(__name__)

# docs/02-contracts.md: "해당 업종 누적 200건 초과 시 업종별 33/66 분위수로 교체."
PERCENTILE_SWITCH_THRESHOLD = 200
# 분위수 계산에 필요한 최소 샘플(팔로워 수를 아는 것만) — 문서에 숫자가 없어 판단한 값.
# 200건 넘었어도 팔로워 데이터가 거의 없으면 분위수 자체가 의미 없어 고정값을 유지한다.
PERCENTILE_MIN_SAMPLE = 30

# ROADMAP/docs 어디에도 고정 숫자가 없어 P1 진행 중 사용자 확인 후 확정(2026-08-14).
# comparing 단계 가드(high_n/low_n >= 15)를 여유 있게 넘기도록 20으로 잡았다.
TRACK_TOP_N = 20

# docs/02-contracts.md "버킷 경계 (초기 고정값)" 표. "B1 ~1,000" "B2 1,000~10,000"처럼
# 경계값 자체의 포함/미포함이 명시돼 있지 않아서 하한 포함·상한 미포함으로 판단했다
# (표준적인 구간 관례). 업종 200건 누적 후 분위수로 교체되기 전까지는 이 고정값을 쓴다.
BUCKET_UPPER_BOUNDS: dict[str, int] = {"B1": 1_000, "B2": 10_000, "B3": 100_000}


def calculate_metrics(reel: RawReel, account: Account) -> ReelMetrics:
    """docs/03-pipeline.md score 1~3번. 0으로 나누기 방지는 `max(count, 1)`.

    `like_count`가 None("모른다", 좋아요 비공개 계정)이면 0으로 지어내지 않고 분자에서
    뺀다 — 아는 값(comment/share)만으로 계산한다(판단, 2026-08-24). 이 reel이 랭킹에서
    부당하게 낮게 나올 위험은 `select_control()`이 별도로 가드한다.
    """
    play = max(reel.play_count, 1)
    like = reel.like_count or 0
    engagement_rate = (like + reel.comment_count + reel.share_count) / play
    share_rate = reel.share_count / play
    reach_multiple = None
    if account.follower_count is not None:
        reach_multiple = reel.play_count / max(account.follower_count, 1)
    return ReelMetrics(
        engagement_rate=engagement_rate, share_rate=share_rate, reach_multiple=reach_multiple
    )


def classify_bucket(follower_count: int | None, boundaries: dict[str, int] | None = None) -> Bucket:
    """docs/02-contracts.md 버킷 경계. 팔로워 없으면 'unknown' (docs/03-pipeline.md score 4번).

    `boundaries`를 안 주면 초기 고정값(`BUCKET_UPPER_BOUNDS`)을 쓴다 — 업종 200건 초과 후엔
    호출부가 `resolve_bucket_boundaries()`로 구한 값을 넘긴다.
    """
    if follower_count is None:
        return "unknown"
    bounds = boundaries or BUCKET_UPPER_BOUNDS
    if follower_count < bounds["B1"]:
        return "B1"
    if follower_count < bounds["B2"]:
        return "B2"
    if follower_count < bounds["B3"]:
        return "B3"
    return "B4"


def compute_percentile_boundaries(follower_counts: list[int]) -> dict[str, int]:
    """docs/02-contracts.md "33/66 분위수로 교체". `bucket_configs.boundaries`가
    B1/B2/B3 3개 키만 갖는데(B4는 항상 그 위) 문서엔 분위수가 33/66 두 개만 명시돼 있어
    B1·B2 경계만 분위수로 교체하고 B3(메가 계정 절대 기준, 10만) 경계는 고정 유지한다 —
    "33/66 분위수" 자체는 3분할(하위/중위/상위) 개념이라 대칭적으로 3번째 컷은 없다고
    판단함(계약 3-1, docs/02-contracts.md "버킷 경계" 항목과 다르게 해석했으므로 명시).
    """
    b1, b2 = statistics.quantiles(sorted(follower_counts), n=3)
    return {"B1": round(b1), "B2": round(b2), "B3": BUCKET_UPPER_BOUNDS["B3"]}


async def resolve_bucket_boundaries(business_type: str) -> dict[str, int]:
    """업종 누적 200건 초과 시 33/66 분위수로 교체, 아니면 `bucket_configs`의 기존값(기본
    고정값)을 그대로 쓴다. 교체 시 이번 계산 결과를 이력으로 `bucket_configs`에 저장한다."""
    total = await reels_db.count_by_business_type(business_type)
    if total > PERCENTILE_SWITCH_THRESHOLD:
        follower_counts = await reels_db.get_follower_counts_by_business_type(business_type)
        if len(follower_counts) >= PERCENTILE_MIN_SAMPLE:
            boundaries = compute_percentile_boundaries(follower_counts)
            await bucket_configs_db.save_percentile_boundaries(
                business_type, boundaries, sample_size=total
            )
            return boundaries
    return await bucket_configs_db.get_boundaries(business_type)


def build_scored_reel(
    reel: RawReel, account: Account, boundaries: dict[str, int] | None = None
) -> ScoredReel:
    """지표 계산 + 버킷 분류를 묶은 편의 함수. track은 선정 단계 전이라 None."""
    metrics = calculate_metrics(reel, account)
    bucket = classify_bucket(account.follower_count, boundaries)
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
        # like_count가 None인 릴스는 engagement_rate가 comment/share만으로 계산돼
        # 실제보다 낮게 나온다 — control(하위) 후보에 부당하게 쏠리면 안 되니 여기서만
        # 제외한다(판단, 2026-08-24). reach_multiple 분기는 좋아요와 무관해 영향 없다.
        pool = [r for r in pool if r.reel.like_count is not None]
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

    버킷 경계는 `bucket_configs`를 읽기만 한다(재계산·재저장은 score.run()만의 책임) —
    한 잡 안에서는 scoring이 항상 이후 단계보다 먼저 끝나므로 score.run()이 이미 확정한
    경계를 그대로 읽게 된다.
    """
    reels = await reels_db.get_by_keyword(keyword, business_type)
    usernames = sorted({reel.username for reel in reels})
    accounts = await accounts_db.get_many(usernames)
    boundaries = await bucket_configs_db.get_boundaries(business_type)
    scored = [build_scored_reel(reel, accounts[reel.username], boundaries) for reel in reels]
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

    boundaries = await resolve_bucket_boundaries(business_type)
    scored = [build_scored_reel(reel, accounts[reel.username], boundaries) for reel in reels]
    await reel_metrics_db.upsert_many(scored)

    bucket_counts = Counter(s.bucket for s in scored)
    breakout, big_account, control = await compute_tracks(keyword, business_type)
    targets = await select_target_reels(keyword, business_type)
    logger.info(
        "job %s 스코어링 완료: reels=%d, 버킷분포=%s, breakout=%d, big_account=%d, "
        "control=%d, preparing 대상(합집합)=%d",
        job_id,
        len(reels),
        dict(bucket_counts),
        len(breakout),
        len(big_account),
        len(control),
        len(targets),
    )
