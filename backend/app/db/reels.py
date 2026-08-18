"""reels 테이블 CRUD. code(shortcode)가 기본 키 — 같은 릴스 재수집은 upsert로 흡수한다."""

from typing import Any

from psycopg.rows import dict_row

from app.db.connection import get_conn
from app.schemas.collect import RawReel


def _row_to_raw_reel(row: dict[str, Any]) -> RawReel:
    return RawReel(
        code=row["code"],
        url=row["url"],
        username=row["username"],
        caption=row["caption"],
        hashtags=row["hashtags"],
        audio_title=row["audio_title"],
        video_url=row["video_url"],
        thumbnail_url=row["thumbnail_url"],
        duration_sec=row["duration_sec"],
        taken_at=row["taken_at"],
        play_count=row["play_count"],
        like_count=row["like_count"],
        comment_count=row["comment_count"],
        share_count=row["share_count"],
    )


async def upsert_many(reels: list[RawReel], keyword: str, business_type: str) -> None:
    """accounts에 먼저 해당 username 행이 있어야 한다 (reels.username FK)."""
    if not reels:
        return
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            for reel in reels:
                await cur.execute(
                    """
                    INSERT INTO reels (code, url, username, business_type, keyword,
                                        caption, hashtags, audio_title, video_url,
                                        thumbnail_url, duration_sec, taken_at,
                                        play_count, like_count, comment_count, share_count)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (code) DO UPDATE SET
                        url = EXCLUDED.url,
                        username = EXCLUDED.username,
                        business_type = EXCLUDED.business_type,
                        keyword = EXCLUDED.keyword,
                        caption = EXCLUDED.caption,
                        hashtags = EXCLUDED.hashtags,
                        audio_title = EXCLUDED.audio_title,
                        video_url = EXCLUDED.video_url,
                        thumbnail_url = EXCLUDED.thumbnail_url,
                        duration_sec = EXCLUDED.duration_sec,
                        taken_at = EXCLUDED.taken_at,
                        play_count = EXCLUDED.play_count,
                        like_count = EXCLUDED.like_count,
                        comment_count = EXCLUDED.comment_count,
                        share_count = EXCLUDED.share_count
                    """,
                    (
                        reel.code,
                        reel.url,
                        reel.username,
                        business_type,
                        keyword,
                        reel.caption,
                        reel.hashtags,
                        reel.audio_title,
                        reel.video_url,
                        reel.thumbnail_url,
                        reel.duration_sec,
                        reel.taken_at,
                        reel.play_count,
                        reel.like_count,
                        reel.comment_count,
                        reel.share_count,
                    ),
                )
        await conn.commit()


async def get_by_keyword(keyword: str, business_type: str) -> list[RawReel]:
    """score/frames 등 뒤 단계가 job_id로부터 keyword/business_type을 얻어 재조회할 때 쓴다."""
    async with get_conn() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT * FROM reels WHERE keyword = %s AND business_type = %s",
                (keyword, business_type),
            )
            rows = await cur.fetchall()
    return [_row_to_raw_reel(row) for row in rows]
