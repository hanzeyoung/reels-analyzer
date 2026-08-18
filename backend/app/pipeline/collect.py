"""JobStage 'collecting'. docs/03-pipeline.md의 collect 참조.

`run()`은 Apify 실호출과 함께 P1 T-1.1에서 구현한다 (fixtures/에 실물 응답을 박제한 뒤).
아래 순수 함수들은 외부 API 없이 지금 구현 가능한 필터·정규화 로직이다
(G0 지시서 4단계 — DB도 필요 없다).
"""

import re
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from uuid import UUID

from app.db import accounts as accounts_db
from app.db import jobs as jobs_db
from app.db import reels as reels_db
from app.schemas.collect import Account, RawReel

_HASHTAG_RE = re.compile(r"#(\w+)")

RECENCY_DAYS = 30
DEDUP_SIMILARITY_THRESHOLD = 0.82
RELEVANCE_FULL_MATCH_MAX_WORDS = 3
RELEVANCE_PARTIAL_MATCH_RATIO = 0.75


def extract_hashtags(caption: str) -> list[str]:
    """캡션에서 `#\\w+` 정규식으로 해시태그를 뽑는다 (docs/03-pipeline.md collect 3번)."""
    return [f"#{tag}" for tag in _HASHTAG_RE.findall(caption)]


def _as_aware_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def filter_recent(
    reels: list[RawReel], *, now: datetime | None = None, days: int = RECENCY_DAYS
) -> list[RawReel]:
    """`taken_at`이 최근 `days`일 이내인 것만 남긴다.

    docs/03-pipeline.md collect 4번, docs/00-product.md의 게시 시점 교란변수 대응
    ("6개월 된 릴스는 조회수가 누적된 것이지 잘 만든 게 아니다").
    """
    cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
    return [reel for reel in reels if _as_aware_utc(reel.taken_at) >= cutoff]


def is_relevant(keyword: str, reel: RawReel) -> bool:
    """키워드가 캡션/해시태그/계정명에 있는지 어절 단위로 판정한다.

    docs/03-pipeline.md collect 5번: "복합어는 어절 분해 후 3개 이하면 전부,
    초과면 75% 이상 매칭".

    **계약 갭**: 문서는 "위치명"도 매칭 대상에 넣으라고 하지만 `RawReel`(docs/02-contracts.md)
    에는 위치 필드가 없다. 임의로 필드를 지어내지 않고 캡션/해시태그/계정명 3곳만 본다 —
    위치 필드가 계약에 추가되면 여기 haystack에 포함시킨다.
    """
    words = keyword.split()
    if not words:
        return False
    haystack = " ".join([reel.caption, " ".join(reel.hashtags), reel.username]).lower()
    matched = sum(1 for word in words if word.lower() in haystack)
    if len(words) <= RELEVANCE_FULL_MATCH_MAX_WORDS:
        return matched == len(words)
    return (matched / len(words)) >= RELEVANCE_PARTIAL_MATCH_RATIO


def _normalize_caption(caption: str) -> str:
    return re.sub(r"\s+", " ", caption).strip().lower()


def dedupe_by_caption_similarity(
    reels: list[RawReel], *, threshold: float = DEDUP_SIMILARITY_THRESHOLD
) -> list[RawReel]:
    """캡션 정규화 후 `SequenceMatcher.ratio() >= threshold`면 동일 콘텐츠로 보고
    먼저 나온 것만 남긴다 (docs/03-pipeline.md collect 6번). 입력 순서를 유지한다."""
    kept: list[RawReel] = []
    kept_norms: list[str] = []
    for reel in reels:
        norm = _normalize_caption(reel.caption)
        if any(
            SequenceMatcher(None, norm, existing).ratio() >= threshold
            for existing in kept_norms
        ):
            continue
        kept.append(reel)
        kept_norms.append(norm)
    return kept


async def run(job_id: str) -> None:
    # providers는 여기서 지연 import한다 — app.providers.collect가 extract_hashtags()를
    # 쓰려고 이 모듈을 import하기 때문에, 모듈 최상단에서 맞물려 import하면 순환참조가 난다.
    from app.providers import get_collect_provider

    job = await jobs_db.get_job(UUID(job_id))
    assert job is not None, f"job {job_id} not found"
    keyword = job.request.keyword
    business_type = job.request.business_type

    provider = get_collect_provider()
    raw = await provider.collect_reels(keyword, business_type)

    recent = filter_recent(raw)
    relevant = [reel for reel in recent if is_relevant(keyword, reel)]
    deduped = dedupe_by_caption_similarity(relevant)

    usernames = sorted({reel.username for reel in deduped})
    cached = await accounts_db.get_cached(usernames)
    missing = [u for u in usernames if u not in cached]
    fresh = await provider.fetch_accounts(missing) if missing else []
    await accounts_db.upsert_many(fresh)

    # reels.username은 accounts(username) FK다 — 조회 실패(비공개/삭제 계정 등)로 남은
    # username도 "모른다"(follower_count=None) 상태로 한 행 넣어야 reels insert가 안 막힌다.
    resolved = {a.username for a in fresh} | set(cached)
    unresolved = [
        Account(username=u, follower_count=None, fetched_at=None)
        for u in usernames
        if u not in resolved
    ]
    if unresolved:
        await accounts_db.upsert_many(unresolved)

    await reels_db.upsert_many(deduped, keyword=keyword, business_type=business_type)
