"""reel_metrics 테이블 CRUD. score 단계가 계산한 파생 지표(참여율/도달배수/버킷)를 커밋한다."""

from app.db.connection import get_conn
from app.schemas.score import ScoredReel


async def upsert_many(scored_reels: list[ScoredReel]) -> None:
    if not scored_reels:
        return
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            for scored in scored_reels:
                await cur.execute(
                    """
                    INSERT INTO reel_metrics (reel_code, play_count, like_count, comment_count,
                                               share_count, engagement_rate, share_rate,
                                               reach_multiple, bucket)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (reel_code) DO UPDATE SET
                        play_count = EXCLUDED.play_count,
                        like_count = EXCLUDED.like_count,
                        comment_count = EXCLUDED.comment_count,
                        share_count = EXCLUDED.share_count,
                        engagement_rate = EXCLUDED.engagement_rate,
                        share_rate = EXCLUDED.share_rate,
                        reach_multiple = EXCLUDED.reach_multiple,
                        bucket = EXCLUDED.bucket,
                        measured_at = NOW()
                    """,
                    (
                        scored.reel.code,
                        scored.reel.play_count,
                        scored.reel.like_count,
                        scored.reel.comment_count,
                        scored.reel.share_count,
                        scored.metrics.engagement_rate,
                        scored.metrics.share_rate,
                        scored.metrics.reach_multiple,
                        scored.bucket,
                    ),
                )
        await conn.commit()
