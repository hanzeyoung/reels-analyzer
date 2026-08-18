from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import analyses, health
from app.db.connection import close_pool, init_pool


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_pool()
    try:
        yield
    finally:
        await close_pool()


app = FastAPI(title="Buja API", lifespan=lifespan)

app.include_router(health.router)
app.include_router(analyses.router)
