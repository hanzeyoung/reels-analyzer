"""reel_analyses 테이블 CRUD. analyzing 단계가 릴스 단위 요약을 커밋한다.

테이블엔 track/bucket 컬럼이 없다(그 값들은 reel_metrics.bucket과 score.select_target_reels()
재계산으로만 존재한다) — 그래서 여기 upsert()는 `ReelAnalysis` 전체가 아니라 테이블이
실제로 갖는 컬럼만 받는다.
"""

from datetime import datetime
from typing import Any

from psycopg.rows import dict_row

from app.db.connection import get_conn


async def get(reel_code: str) -> dict[str, Any] | None:
    """comparing 단계가 `ReelAnalysis` 재구성할 때 쓴다. 없으면 None(analyzing 실패/미완료)."""
    async with get_conn() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT cut_count, avg_shot_sec, first_shot_sec, caption_hooks, color_tone,
                       subtitle_position, summary, model, analyzed_at
                FROM reel_analyses WHERE reel_code = %s
                """,
                (reel_code,),
            )
            return await cur.fetchone()


async def upsert(
    *,
    reel_code: str,
    cut_count: int,
    avg_shot_sec: float,
    first_shot_sec: float,
    caption_hooks: list[str],
    color_tone: str,
    subtitle_position: str,
    summary: str,
    model: str,
    analyzed_at: datetime,
) -> None:
    async with get_conn() as conn:
        await conn.execute(
            """
            INSERT INTO reel_analyses (reel_code, cut_count, avg_shot_sec, first_shot_sec,
                                        caption_hooks, color_tone, subtitle_position, summary,
                                        model, analyzed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (reel_code) DO UPDATE SET
                cut_count = EXCLUDED.cut_count,
                avg_shot_sec = EXCLUDED.avg_shot_sec,
                first_shot_sec = EXCLUDED.first_shot_sec,
                caption_hooks = EXCLUDED.caption_hooks,
                color_tone = EXCLUDED.color_tone,
                subtitle_position = EXCLUDED.subtitle_position,
                summary = EXCLUDED.summary,
                model = EXCLUDED.model,
                analyzed_at = EXCLUDED.analyzed_at
            """,
            (
                reel_code,
                cut_count,
                avg_shot_sec,
                first_shot_sec,
                caption_hooks,
                color_tone,
                subtitle_position,
                summary,
                model,
                analyzed_at,
            ),
        )
        await conn.commit()
