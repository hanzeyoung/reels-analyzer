from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RawReel(BaseModel):
    """Apify 응답을 정규화한 형태. 어댑터가 이 모양으로 변환한다."""

    model_config = ConfigDict(extra="forbid")

    code: str
    url: str
    username: str
    caption: str = ""
    hashtags: list[str] = []
    audio_title: str | None = None
    video_url: str | None = None
    thumbnail_url: str | None = None
    duration_sec: float | None = None
    taken_at: datetime

    play_count: int = 0
    like_count: int | None = None  # None = "모른다"(좋아요 비공개 계정). 0으로 채우지 마라
    comment_count: int = 0
    share_count: int = 0


class Account(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    follower_count: int | None = None
    fetched_at: datetime | None = None
