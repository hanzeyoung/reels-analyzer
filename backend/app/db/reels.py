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


async def upsert_many(
    reels: list[RawReel], keyword: str, business_type: str, *, is_my_reel: bool = False
) -> None:
    """accounts에 먼저 해당 username 행이 있어야 한다 (reels.username FK).

    `is_my_reel=True`(P5, 진단용 내 릴스)는 `get_by_keyword()`에서 항상 제외된다 —
    같은 keyword/business_type 풀에 섞여 들어가 버킷 분류·대조 분석 표본을 오염시키면 안 된다.
    """
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
                                        play_count, like_count, comment_count, share_count,
                                        is_my_reel)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                        share_count = EXCLUDED.share_count,
                        is_my_reel = EXCLUDED.is_my_reel
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
                        is_my_reel,
                    ),
                )
        await conn.commit()


async def get_by_keyword(keyword: str, business_type: str) -> list[RawReel]:
    """score/frames 등 뒤 단계가 job_id로부터 keyword/business_type을 얻어 재조회할 때 쓴다.
    `is_my_reel=true`인 행(P5 진단용)은 항상 제외한다."""
    async with get_conn() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT * FROM reels WHERE keyword = %s AND business_type = %s "
                "AND is_my_reel = false",
                (keyword, business_type),
            )
            rows = await cur.fetchall()
    return [_row_to_raw_reel(row) for row in rows]


async def count_by_business_type(business_type: str) -> int:
    """docs/02-contracts.md 분위수 교체 판정용 — 키워드 무관, 업종 전체 누적 건수.
    `is_my_reel=true`는 제외한다."""
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT COUNT(*) FROM reels WHERE business_type = %s AND is_my_reel = false",
                (business_type,),
            )
            row = await cur.fetchone()
    assert row is not None
    return int(row[0])


async def get_follower_counts_by_business_type(business_type: str) -> list[int]:
    """분위수 계산용 — 해당 업종 전체(키워드 무관)에서 팔로워 수를 아는 계정의 값만 모은다.
    `reels.username`이 `accounts.username`을 FK로 참조하므로 조인한다."""
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT a.follower_count FROM reels r
                JOIN accounts a ON a.username = r.username
                WHERE r.business_type = %s AND r.is_my_reel = false
                  AND a.follower_count IS NOT NULL
                """,
                (business_type,),
            )
            rows = await cur.fetchall()
    return [row[0] for row in rows]


async def get_my_reel(keyword: str, business_type: str) -> RawReel | None:
    """diagnosing이 커밋한 `is_my_reel=true` 행을 generating이 다시 읽을 때 쓴다."""
    async with get_conn() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT * FROM reels WHERE keyword = %s AND business_type = %s "
                "AND is_my_reel = true ORDER BY collected_at DESC LIMIT 1",
                (keyword, business_type),
            )
            row = await cur.fetchone()
    return _row_to_raw_reel(row) if row else None
