from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.common import JobStage, JobStatus
from app.schemas.guide import Guide
from app.schemas.requests import AnalysisRequest


class Job(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    status: JobStatus
    stage: JobStage | None = None
    progress_current: int = 0
    progress_total: int = 0
    error: str | None = None
    heartbeat_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    request: AnalysisRequest
    result: Guide | None = None
