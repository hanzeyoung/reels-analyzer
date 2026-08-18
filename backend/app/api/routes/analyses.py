"""docs/05-api.md 참조. 동기 작업 0 — 잡 생성/조회만 한다."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.db import jobs as jobs_db
from app.schemas.common import JobStage, JobStatus
from app.schemas.guide import Guide
from app.schemas.requests import AnalysisRequest

router = APIRouter(prefix="/api/analyses", tags=["analyses"])


class CreateJobResponse(BaseModel):
    job_id: UUID
    status: JobStatus


class Progress(BaseModel):
    current: int
    total: int


class JobDetailResponse(BaseModel):
    job_id: UUID
    status: JobStatus
    stage: JobStage | None
    progress: Progress
    error: str | None
    result: Guide | None


class JobListItem(BaseModel):
    job_id: UUID
    keyword: str
    status: JobStatus
    created_at: str


class JobListResponse(BaseModel):
    items: list[JobListItem]


@router.post("", status_code=202, response_model=CreateJobResponse)
async def create_analysis(request: AnalysisRequest) -> CreateJobResponse:
    job = await jobs_db.create_job(request)
    return CreateJobResponse(job_id=job.id, status=job.status)


@router.get("/{job_id}", response_model=JobDetailResponse)
async def get_analysis(job_id: UUID) -> JobDetailResponse:
    job = await jobs_db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return JobDetailResponse(
        job_id=job.id,
        status=job.status,
        stage=job.stage,
        progress=Progress(current=job.progress_current, total=job.progress_total),
        error=job.error,
        result=job.result,
    )


@router.get("", response_model=JobListResponse)
async def list_analyses(limit: int = Query(default=20, ge=1, le=100)) -> JobListResponse:
    job_list = await jobs_db.list_jobs(limit=limit)
    return JobListResponse(
        items=[
            JobListItem(
                job_id=job.id,
                keyword=job.request.keyword,
                status=job.status,
                created_at=job.created_at.isoformat(),
            )
            for job in job_list
        ]
    )


@router.post("/{job_id}/cancel", response_model=CreateJobResponse)
async def cancel_analysis(job_id: UUID) -> CreateJobResponse:
    job = await jobs_db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status not in ("queued", "running"):
        raise HTTPException(status_code=409, detail="job already finished")

    cancelled = await jobs_db.cancel_job(job_id)
    if cancelled is None:
        # 조회와 취소 사이에 잡이 이미 끝난 경합 상황 (G0 D). 500 대신 409로 응답한다.
        raise HTTPException(status_code=409, detail="job already finished")
    return CreateJobResponse(job_id=cancelled.id, status=cancelled.status)
