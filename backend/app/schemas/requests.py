from typing import Literal

from pydantic import BaseModel, ConfigDict


class UserConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shooting_alone: bool = True
    equipment: list[str] = ["스마트폰"]
    space: Literal["좁음", "보통", "넓음"] = "보통"
    can_show_face: bool = False
    weekly_minutes: int = 60


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keyword: str
    business_type: str
    constraints: UserConstraints
    my_reel_url: str | None = None
