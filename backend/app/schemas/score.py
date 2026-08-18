from pydantic import BaseModel, ConfigDict, model_validator

from app.schemas.collect import Account, RawReel
from app.schemas.common import Bucket, Track


class ReelMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engagement_rate: float
    share_rate: float
    reach_multiple: float | None


class ScoredReel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reel: RawReel
    account: Account
    metrics: ReelMetrics
    bucket: Bucket
    track: Track | None = None

    @model_validator(mode="after")
    def _check_follower_reach_consistency(self) -> "ScoredReel":
        # 계약 불변식 2: follower_count가 None이면 reach_multiple도 반드시 None.
        if self.account.follower_count is None and self.metrics.reach_multiple is not None:
            raise ValueError("follower_count가 None이면 reach_multiple도 None이어야 한다")
        return self
