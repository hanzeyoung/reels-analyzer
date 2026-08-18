"""shot_segments 테이블 CRUD.

preparing(frames.py)이 t_start/t_end/idx만 먼저 INSERT하고, analyzing이 같은 행을
VLM 필드(angle/subject/...)로 UPDATE하는 2단계 커밋 구조다
(docs/03-pipeline.md preparing 정정, 2026-08-14).
"""

from typing import Any

from psycopg.rows import dict_row

from app.db.connection import get_conn
from app.schemas.analyze import VisionShotDescription
from app.schemas.frames import Cut


async def has_any(reel_code: str) -> bool:
    """이미 행이 있으면 True — preparing이 다운로드 자체를 건너뛰는 기준(docs 명시)."""
    async with get_conn() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT EXISTS (SELECT 1 FROM shot_segments WHERE reel_code = %s) AS found",
                (reel_code,),
            )
            row = await cur.fetchone()
    return bool(row["found"]) if row else False


async def insert_cut_timings(reel_code: str, cuts: list[Cut]) -> None:
    """t_start/t_end/idx만 넣는다. VLM 필드는 analyzing이 채울 때까지 NULL로 둔다."""
    if not cuts:
        return
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            for cut in cuts:
                await cur.execute(
                    """
                    INSERT INTO shot_segments (reel_code, idx, t_start, t_end)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (reel_code, idx) DO UPDATE SET
                        t_start = EXCLUDED.t_start,
                        t_end = EXCLUDED.t_end
                    """,
                    (reel_code, cut.index, cut.t_start, cut.t_end),
                )
        await conn.commit()


async def get_pending(reel_code: str) -> list[dict[str, Any]]:
    """VLM 필드(angle)가 아직 NULL인 행만 idx 오름차순으로 — analyzing이 처리할 대상."""
    async with get_conn() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT idx, t_start, t_end FROM shot_segments
                WHERE reel_code = %s AND angle IS NULL
                ORDER BY idx
                """,
                (reel_code,),
            )
            rows = await cur.fetchall()
    return rows


async def get_completed(reel_code: str) -> list[dict[str, Any]]:
    """VLM 필드까지 채워진 행만 idx 오름차순으로 — comparing 등 후속 단계가
    `ReelAnalysis`를 재구성할 때 쓴다."""
    async with get_conn() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT idx, t_start, t_end, angle, subject, on_screen_text, movement,
                       purpose, technique, difficulty, requires, solo_alternative
                FROM shot_segments
                WHERE reel_code = %s AND angle IS NOT NULL
                ORDER BY idx
                """,
                (reel_code,),
            )
            rows = await cur.fetchall()
    return rows


async def update_vlm_fields(
    reel_code: str, idx: int, shot: VisionShotDescription, model: str
) -> None:
    """analyzing이 VLM 응답으로 preparing이 만든 행을 채운다."""
    async with get_conn() as conn:
        await conn.execute(
            """
            UPDATE shot_segments SET
                angle = %s, subject = %s, on_screen_text = %s, movement = %s,
                purpose = %s, technique = %s, difficulty = %s, requires = %s,
                solo_alternative = %s, model = %s, analyzed_at = NOW()
            WHERE reel_code = %s AND idx = %s
            """,
            (
                shot.angle,
                shot.subject,
                shot.on_screen_text,
                shot.movement,
                shot.purpose,
                shot.technique,
                shot.difficulty,
                shot.requires,
                shot.solo_alternative,
                model,
                reel_code,
                idx,
            ),
        )
        await conn.commit()
