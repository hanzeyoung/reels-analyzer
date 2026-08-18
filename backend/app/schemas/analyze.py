from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from app.schemas.common import Bucket, Difficulty, Movement, ShotPurpose, Track


class VisionShotDescription(BaseModel):
    """VLM이 반환하는 형태. t_start/t_end가 없는 것이 의도적이다."""

    model_config = ConfigDict(extra="forbid")

    index: int
    angle: str
    subject: str
    on_screen_text: str | None
    movement: Movement
    purpose: ShotPurpose
    technique: str | None
    difficulty: Difficulty
    requires: list[str] = []
    solo_alternative: str | None


class VisionAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shots: list[VisionShotDescription]
    caption_hooks: list[str] = []
    color_tone: str
    subtitle_position: Literal["상단", "중앙", "하단", "혼합", "없음"]
    summary: str


class ShotSegment(VisionShotDescription):
    t_start: float
    t_end: float

    @model_validator(mode="after")
    def _check_time_order(self) -> "ShotSegment":
        if not self.t_start < self.t_end:
            raise ValueError("t_start must be < t_end")
        return self


class ReelAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reel_code: str
    track: Track
    bucket: Bucket
    shots: list[ShotSegment]
    caption_hooks: list[str]
    color_tone: str
    subtitle_position: str
    summary: str
    cut_count: int
    avg_shot_sec: float
    first_shot_sec: float
    audio_title: str | None
    model: str
    analyzed_at: datetime

    @model_validator(mode="after")
    def _check_shots_sorted_by_t_start(self) -> "ReelAnalysis":
        # 계약 불변식 3: 리스트는 t_start 오름차순.
        starts = [shot.t_start for shot in self.shots]
        if starts != sorted(starts):
            raise ValueError("shots는 t_start 오름차순이어야 한다")
        return self
