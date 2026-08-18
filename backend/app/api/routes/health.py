from fastapi import APIRouter
from pydantic import BaseModel

from app.db import workers as workers_db

router = APIRouter(prefix="/api", tags=["health"])


class HealthResponse(BaseModel):
    ok: bool
    worker_alive: bool
    last_heartbeat: str | None


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    last_seen = await workers_db.latest_seen_at()
    return HealthResponse(
        ok=True,
        worker_alive=await workers_db.any_worker_alive(),
        last_heartbeat=last_seen.isoformat() if last_seen else None,
    )
