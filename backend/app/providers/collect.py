import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

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

    async def collect_reels(self, keyword: str, business_type: str) -> list[RawReel]:
        # Instagram 해시태그는 공백을 허용하지 않는다 — 복합어 키워드는 붙여서 검색하고,
        # 실제 관련성 판단은 app.pipeline.collect.is_relevant(어절 단위)가 나중에 맡는다.
        tag = keyword.replace(" ", "")
        search = tag if tag.startswith("#") else f"#{tag}"

        items = await self._run(
            {
                "search": search,
                "searchType": "hashtag",
                "searchLimit": 1,
                "resultsType": "posts",
                "resultsLimit": REELS_PER_KEYWORD,
            }
        )

        reels: list[RawReel] = []
        for item in items:
            video_url = item.get("videoUrl")
            # docs/03-pipeline.md collect 2번: is_video=True and video_url 존재하는 것만.
            # Apify 응답엔 is_video 필드가 없어 type=="Video" + videoUrl 존재로 판정한다.
            if item.get("type") != "Video" or not video_url:
                continue
            caption = item.get("caption") or ""
            reels.append(
                RawReel(
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
                    like_count=item.get("likesCount") or 0,
                    comment_count=item.get("commentsCount") or 0,
                )
            )
        return reels

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
