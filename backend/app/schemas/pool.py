from pydantic import BaseModel, ConfigDict

from app.schemas.score import ScoredReel


class ReelPool(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keyword: str
    business_type: str

    collected_count: int
    after_recency_count: int
    after_relevance_count: int
    after_dedup_count: int

    follower_data_available: bool
    bucket_config_id: str | None

    breakout: list[ScoredReel]
    big_account: list[ScoredReel]
    control: list[ScoredReel]
