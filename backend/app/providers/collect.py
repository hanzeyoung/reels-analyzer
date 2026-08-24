import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

import httpx

from app.pipeline.collect import extract_hashtags
from app.providers.base import CollectProvider
from app.schemas.collect import Account, RawReel

logger = logging.getLogger(__name__)

# 액터: apify/instagram-scraper (id: shu8hvrXbJbY3Eb9W). G1 실측(2026-08-14)으로 확정 —
# posts/reels 목록과 계정 프로필(팔로워 포함) 둘 다 이 액터 하나로 나온다(resultsType으로 전환).
APIFY_ACTOR = "apify~instagram-scraper"
APIFY_RUN_SYNC_URL = f"https://api.apify.com/v2/acts/{APIFY_ACTOR}/run-sync-get-dataset-items"

REELS_PER_KEYWORD = 200  # docs/03-pipeline.md collect 1번: 키워드당 150~200건

# docs/03-pipeline.md collect "실패" 절: "Apify 실패 시 3회 재시도(지수 백오프).
# 그래도 실패면 잡 failed." 최초 1회 + 재시도 3회 = 최대 4회 시도, 지연은 1s/2s/4s.
APIFY_MAX_ATTEMPTS = 4
APIFY_RETRY_BASE_DELAY_SECONDS = 1.0


class ApifyCollectProvider(CollectProvider):
    """T-1.1 실측(fixtures/collect/dataset_instagram-scraper_*.json,
    fixtures/collect/profile_humansofny.json)으로 확인한 응답 구조를 기준으로 정규화한다."""

    def __init__(self, token: str) -> None:
        self._token = token

    async def _run(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        last_exc: httpx.HTTPError | None = None
        for attempt in range(APIFY_MAX_ATTEMPTS):
            try:
                async with httpx.AsyncClient(timeout=120) as client:
                    response = await client.post(
                        APIFY_RUN_SYNC_URL, params={"token": self._token}, json=payload
                    )
                    response.raise_for_status()
                    return cast(list[dict[str, Any]], response.json())
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < APIFY_MAX_ATTEMPTS - 1:
                    delay = APIFY_RETRY_BASE_DELAY_SECONDS * (2**attempt)
                    logger.warning(
                        "Apify 호출 실패(%d/%d), %.0f초 후 재시도: %s",
                        attempt + 1,
                        APIFY_MAX_ATTEMPTS,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)
        assert last_exc is not None
        raise last_exc

    def _item_to_raw_reel(self, item: dict[str, Any]) -> RawReel | None:
        video_url = item.get("videoUrl")
        # docs/03-pipeline.md collect 2번: is_video=True and video_url 존재하는 것만.
        # Apify 응답엔 is_video 필드가 없어 type=="Video" + videoUrl 존재로 판정한다.
        if item.get("type") != "Video" or not video_url:
            return None
        caption = item.get("caption") or ""
        # P6.5 실측(2026-08-24): 좋아요 비공개 계정은 likesCount가 -1로 온다. 0으로
        # 뭉개면 "좋아요 0개인 저성과 릴스"로 오인돼 engagement_rate가 왜곡되고 control
        # 그룹에 인위적으로 쏠린다 — None("모른다")으로 정규화한다.
        raw_likes = item.get("likesCount")
        like_count = raw_likes if raw_likes is not None and raw_likes >= 0 else None
        return RawReel(
            code=item["shortCode"],
            url=item["url"],
            username=item["ownerUsername"],
            caption=caption,
            hashtags=extract_hashtags(caption),
            audio_title=(item.get("musicInfo") or {}).get("song_name"),
            video_url=video_url,
            thumbnail_url=item.get("displayUrl"),
            duration_sec=item.get("videoDuration"),
            taken_at=item["timestamp"],
            play_count=item.get("videoPlayCount") or item.get("videoViewCount") or 0,
            like_count=like_count,
            comment_count=item.get("commentsCount") or 0,
        )

    async def collect_reels(self, keyword: str, business_type: str) -> list[RawReel]:
        # Instagram 해시태그는 공백을 허용하지 않는다 — 복합어 키워드는 붙여서 검색하고,
        # 실제 관련성 판단은 app.pipeline.collect.is_relevant(어절 단위)가 나중에 맡는다.
        #
        # P6.5 실측(2026-08-24)으로 확인한 버그: `search`+`searchType=hashtag`는 게시물이
        # 아니라 해시태그 "리서치"(퍼지 매칭으로 관련 해시태그를 찾는 기능)를 반환한다 —
        # 한글 해시태그에서는 완전히 무관한 해시태그로 매칭돼 원본 수집이 0건이 됐다.
        # Apify 공식 문서가 권장하는 `directUrls`(explore/tags) 방식으로 교체한다 —
        # 퍼지 매칭 없이 결정론적으로 해당 해시태그의 게시물만 가져온다.
        tag = keyword.replace(" ", "").removeprefix("#")
        tag_url = f"https://www.instagram.com/explore/tags/{quote(tag, safe='')}/"

        # `resultsType="posts"`는 해시태그의 일반 게시물 그리드(사진 위주)를 반환한다 —
        # 실측(2026-08-24)으로 27건 중 Video 0건을 확인했다. 공식 input schema에 릴스
        # 전용 값 `"reels"`가 따로 있고, 8건 최소비용 재시도로 8/8 전부 Video+videoUrl
        # 확인함 — 이걸로 교체한다.
        items = await self._run(
            {
                "directUrls": [tag_url],
                "resultsType": "reels",
                "resultsLimit": REELS_PER_KEYWORD,
            }
        )
        reels = [reel for item in items if (reel := self._item_to_raw_reel(item)) is not None]
        logger.info(
            "Apify 원본 %d건 수신, type==Video+videoUrl 통과 %d건", len(items), len(reels)
        )
        return reels

    async def fetch_reel_by_url(self, url: str) -> RawReel | None:
        # P5(내 릴스 진단). directUrls + resultsType=posts로 단일 포스트 URL 조회 —
        # 실측(2026-08-18)으로 해시태그 검색과 동일한 아이템 구조(shortCode/ownerUsername/
        # videoUrl/videoPlayCount 등)가 나오는 것 확인. 같은 파싱 헬퍼를 그대로 쓴다.
        items = await self._run(
            {"directUrls": [url], "resultsType": "posts", "resultsLimit": 1}
        )
        if not items:
            return None
        return self._item_to_raw_reel(items[0])

    async def fetch_accounts(self, usernames: list[str]) -> list[Account]:
        if not usernames:
            return []
        urls = [f"https://www.instagram.com/{username}/" for username in usernames]
        items = await self._run(
            {"directUrls": urls, "resultsType": "details", "resultsLimit": 1}
        )
        now = datetime.now(UTC)
        return [
            Account(
                username=item["username"],
                follower_count=item.get("followersCount"),
                fetched_at=now,
            )
            for item in items
        ]


class FakeCollectProvider(CollectProvider):
    def __init__(self, fixtures_dir: str) -> None:
        self._fixtures_dir = Path(fixtures_dir)

    def _load(self) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            json.loads((self._fixtures_dir / "collect" / "sample.json").read_text()),
        )

    async def collect_reels(self, keyword: str, business_type: str) -> list[RawReel]:
        payload = self._load()
        return [RawReel.model_validate(r) for r in payload["reels"]]

    async def fetch_accounts(self, usernames: list[str]) -> list[Account]:
        payload = self._load()
        accounts = [Account.model_validate(a) for a in payload["accounts"]]
        return [a for a in accounts if a.username in usernames]

    async def fetch_reel_by_url(self, url: str) -> RawReel | None:
        payload = self._load()
        my_reel = payload.get("my_reel")
        return RawReel.model_validate(my_reel) if my_reel else None
