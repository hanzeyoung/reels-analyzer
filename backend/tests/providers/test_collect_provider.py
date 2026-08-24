"""ApifyCollectProvider의 재시도(지수 백오프) 검증. 실 API 호출 없음 — httpx를 mock한다."""

from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from app.providers.collect import APIFY_MAX_ATTEMPTS, ApifyCollectProvider, FakeCollectProvider


class _FakeResponse:
    def __init__(self, payload: list[dict[str, Any]]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> list[dict[str, Any]]:
        return self._payload


class _FakeClient:
    """처음 `fail_times`번은 httpx.ConnectError, 이후엔 성공 응답을 준다."""

    def __init__(
        self, state: dict[str, int], fail_times: int, payload: list[dict[str, Any]]
    ) -> None:
        self._state = state
        self._fail_times = fail_times
        self._payload = payload

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def post(self, *args: Any, **kwargs: Any) -> _FakeResponse:
        self._state["calls"] += 1
        if self._state["calls"] <= self._fail_times:
            raise httpx.ConnectError("테스트용 연결 실패")
        return _FakeResponse(self._payload)


async def test_run_retries_on_failure_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    state = {"calls": 0}
    payload = [{"ok": True}]
    monkeypatch.setattr(
        "app.providers.collect.httpx.AsyncClient",
        lambda *a, **k: _FakeClient(state, fail_times=2, payload=payload),
    )
    monkeypatch.setattr("app.providers.collect.asyncio.sleep", AsyncMock())

    provider = ApifyCollectProvider(token="test-token")
    result = await provider._run({"search": "test"})

    assert result == payload
    assert state["calls"] == 3  # 2번 실패 + 1번 성공(docs: 3회 재시도 = 최대 4회 시도 이내)


async def test_run_raises_after_max_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    state = {"calls": 0}
    monkeypatch.setattr(
        "app.providers.collect.httpx.AsyncClient",
        lambda *a, **k: _FakeClient(state, fail_times=99, payload=[]),
    )
    monkeypatch.setattr("app.providers.collect.asyncio.sleep", AsyncMock())

    provider = ApifyCollectProvider(token="test-token")
    with pytest.raises(httpx.ConnectError):
        await provider._run({"search": "test"})

    assert state["calls"] == APIFY_MAX_ATTEMPTS


async def test_fetch_reel_by_url_parses_post_item(monkeypatch: pytest.MonkeyPatch) -> None:
    """P5(내 릴스 진단). directUrls+resultsType=posts 응답 구조 실측(2026-08-18) 기준
    — 해시태그 검색 아이템과 필드가 동일해서 같은 파싱 헬퍼를 재사용한다."""
    item = {
        "type": "Video",
        "shortCode": "Cmyreel1",
        "url": "https://www.instagram.com/p/Cmyreel1/",
        "ownerUsername": "my_cafe",
        "caption": "우리 카페 신메뉴",
        "videoUrl": "https://cdn.example.com/my.mp4",
        "videoPlayCount": 500,
        "likesCount": 30,
        "commentsCount": 2,
        "timestamp": "2026-08-10T09:00:00",
        "musicInfo": None,
        "displayUrl": None,
        "videoDuration": 15.0,
    }
    provider = ApifyCollectProvider(token="test-token")
    monkeypatch.setattr(provider, "_run", AsyncMock(return_value=[item]))

    reel = await provider.fetch_reel_by_url("https://www.instagram.com/p/Cmyreel1/")

    assert reel is not None
    assert reel.code == "Cmyreel1"
    assert reel.username == "my_cafe"
    assert reel.video_url == "https://cdn.example.com/my.mp4"
    assert reel.play_count == 500


async def test_fetch_reel_by_url_returns_none_when_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = ApifyCollectProvider(token="test-token")
    monkeypatch.setattr(provider, "_run", AsyncMock(return_value=[]))

    assert await provider.fetch_reel_by_url("https://www.instagram.com/p/Deleted/") is None


async def test_fake_collect_provider_fetch_reel_by_url_returns_fixture() -> None:
    from app.config import get_settings

    provider = FakeCollectProvider(fixtures_dir=get_settings().fixtures_dir)

    reel = await provider.fetch_reel_by_url("아무 URL이나 무시됨")

    assert reel is not None
    assert reel.code == "Cmyreel1"
