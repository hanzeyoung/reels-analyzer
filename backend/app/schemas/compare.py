from pydantic import BaseModel, ConfigDict, model_validator

from app.schemas.common import Bucket


class FeatureCount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    count: int
    total: int

    @model_validator(mode="after")
    def _check_count_le_total(self) -> "FeatureCount":
        if self.count > self.total:
            raise ValueError("count must be <= total")
        return self


class DifferenceFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature: str
    high: FeatureCount
    low: FeatureCount
    gap_pp: float


class TimingStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_shot_sec_high: float
    first_shot_sec_low: float
    avg_shot_sec_high: float
    avg_shot_sec_low: float
    cut_count_high: float
    cut_count_low: float


class ComparisonResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bucket: Bucket
    high_n: int
    low_n: int
    sufficient: bool
    findings: list[DifferenceFinding]
    timing: TimingStats | None
    insufficient_reason: str | None

    @model_validator(mode="after")
    def _check_sufficiency_guard(self) -> "ComparisonResult":
        if not self.sufficient and self.findings:
            raise ValueError("sufficient=False이면 findings는 비어 있어야 한다")
        return self
