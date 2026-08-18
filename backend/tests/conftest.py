"""DB가 필요한 테스트 공통 설정.

DATABASE_URL이 없으면 이 픽스처를 쓰는 테스트는 스킵된다.
Apify/Claude 등 외부 API는 절대 호출하지 않는다 (fake provider만 테스트 대상).
로컬 Postgres 하나는 실제로 필요하다 — jobs 테이블 자체가 계약이기 때문이다.

풀(AsyncConnectionPool)은 asyncio 이벤트 루프에 종속되기 때문에, pytest-asyncio가
테스트마다 새 이벤트 루프를 만드는 기본 설정에서는 세션 스코프로 풀을 열어두면 안 된다.
그래서 테스트 함수마다 열고 닫는다 — 조금 느리지만 정확하다.
"""

import pytest
import pytest_asyncio

from app.config import get_settings
from app.db.connection import close_pool, get_conn, init_pool

# get_settings()는 OS 환경변수뿐 아니라 프로젝트 루트 .env도 읽는다(app/config.py).
# os.environ만 보면 .env로만 설정된 DATABASE_URL을 놓쳐서 "설정 안 됨"으로 오판하고
# 조용히 스킵해버린다 — 실제로 이 버그로 스킵되는 걸 한 번 겪었다(G0 E 재검증 중 발견).
requires_db = pytest.mark.skipif(
    not get_settings().database_url,
    reason="DATABASE_URL이 설정되지 않음 — 로컬/테스트 Postgres 필요",
)


@pytest_asyncio.fixture
async def clean_jobs_table():
    get_settings.cache_clear()
    await init_pool()
    try:
        async with get_conn() as conn:
            # guides.job_id가 jobs(id)를 참조해서 CASCADE 없이는 TRUNCATE가 거부된다 (G0 B-1).
            await conn.execute("TRUNCATE TABLE jobs, workers CASCADE")
            await conn.commit()
        yield
        async with get_conn() as conn:
            await conn.execute("TRUNCATE TABLE jobs, workers CASCADE")
            await conn.commit()
    finally:
        await close_pool()


@pytest_asyncio.fixture
async def clean_pipeline_tables():
    """P1/P2 파이프라인 테이블용. accounts CASCADE가 reels→{reel_metrics,shot_segments,
    reel_analyses}까지 연쇄로 비운다(FK 체인), jobs CASCADE가 guides까지 비운다."""
    get_settings.cache_clear()
    await init_pool()
    try:
        async with get_conn() as conn:
            await conn.execute("TRUNCATE TABLE jobs, workers, accounts CASCADE")
            await conn.commit()
        yield
        async with get_conn() as conn:
            await conn.execute("TRUNCATE TABLE jobs, workers, accounts CASCADE")
            await conn.commit()
    finally:
        await close_pool()
