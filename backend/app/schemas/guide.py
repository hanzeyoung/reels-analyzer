from datetime import date

from pydantic import BaseModel, ConfigDict, model_validator

from app.schemas.common import Confidence


class ShotListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: int
    t_start_sec: float
    duration_sec: float
    angle: str
    subject: str
    on_screen_text: str | None
    note: str


class CaptionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    pattern: str


class AudioRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    seen_count: int
    total: int

    @model_validator(mode="after")
    def _check_seen_count_le_total(self) -> "AudioRecommendation":
        if self.seen_count > self.total:
            raise ValueError("seen_count must be <= total")
        return self


class DiagnosisCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    mine: str
    benchmark: str
    gap_note: str


class Guide(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_type: str
    keyword: str
    week_of: date

    shot_list: list[ShotListItem]
    caption_drafts: list[CaptionDraft]
    audio: list[AudioRecommendation]
    diagnosis: list[DiagnosisCard] = []

    evidence_note: str
    confidence: Confidence
    caveat: str | None

    @model_validator(mode="after")
    def _check_caveat_required(self) -> "Guide":
        if self.confidence != "충분" and self.caveat is None:
            raise ValueError('confidence != "충분"이면 caveat이 필수다')
        return self
