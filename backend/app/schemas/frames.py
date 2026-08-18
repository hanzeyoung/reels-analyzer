from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class Cut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    t_start: float
    t_end: float
    frame_path: str

    @model_validator(mode="after")
    def _check_time_order(self) -> "Cut":
        if not self.t_start < self.t_end:
            raise ValueError("t_start must be < t_end")
        return self


class CutList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reel_code: str
    duration_sec: float
    cuts: list[Cut]
    cut_count: int
    avg_shot_sec: float
    first_shot_sec: float
    source: Literal["ffmpeg_scene_detect"] = "ffmpeg_scene_detect"
