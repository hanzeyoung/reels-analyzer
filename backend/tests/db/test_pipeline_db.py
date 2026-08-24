"""P1/P2/P5에서 추가된 DB 모듈 회귀 테스트 (accounts/reels/reel_metrics/shot_segments/
reel_analyses/guides) + collect.run()/score.run()/diagnose.run() 엔드투엔드(fake 모드).

frames.run()/analyze.run()의 다운로드+VLM 경로는 여기서 다루지 않는다 — 실제 mp4
다운로드(네트워크)와 VLM 호출이 필요해서, 로컬 HTTP 서버·비디오 fixture 없이는
자동화하기 어렵다. `.env`의 VISION_MODE가 G2 확정 이후 real이라 get_vision_provider()를
통하면 실제 Claude 과금이 발생할 위험도 있다 — 이번 세션에서 수동 스크립트로 각각
실측 검증은 했음(SESSION_LOG.md 참조), 자동 테스트는 별도 인프라 필요로 보류.
diagnose.run()도 fixture의 my_reel.video_url이 null이라 같은 이유로 다운로드 이후
경로(frames/VLM)는 커버 못 한다 — is_my_reel 커밋/풀 제외 여부만 확인한다.
analyze.run()의 진행률 갱신(update_progress)만은 select_target_reels/process_reel을
mock해서 다운로드·VLM 없이 검증한다.
"""

from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock

from psycopg.rows import dict_row

from app.db import accounts as accounts_db
from app.db import bucket_configs as bucket_configs_db
from app.db import guides as guides_db
from app.db import jobs as jobs_db
from app.db import reel_analyses as reel_analyses_db
from app.db import reel_metrics as reel_metrics_db
from app.db import reels as reels_db
from app.db import shot_segments as shot_segments_db
from app.db.connection import get_conn
from app.pipeline import analyze, collect, compare, diagnose, score
from app.pipeline.score import build_scored_reel
from app.schemas.analyze import VisionShotDescription
from app.schemas.collect import Account, RawReel
from app.schemas.frames import Cut
from app.schemas.guide import CaptionDraft, Guide, ShotListItem
from app.schemas.requests import AnalysisRequest, UserConstraints
from tests.conftest import requires_db

NOW = datetime(2026, 8, 14, tzinfo=UTC)


def _account(**overrides) -> Account:
    defaults = dict(username="_t_user", follower_count=5000, fetched_at=NOW)
    defaults.update(overrides)
    return Account(**defaults)


def _reel(**overrides) -> RawReel:
    defaults = dict(
        code="_t_reel",
        url="https://instagram.com/reel/_t_reel",
        username="_t_user",
        caption="테스트 캡션",
        video_url="https://example.com/source.mp4",
        taken_at=NOW,
        play_count=10_000,
        like_count=500,
        comment_count=20,
    )
    defaults.update(overrides)
    return RawReel(**defaults)


@requires_db
async def test_accounts_upsert_and_cache(clean_pipeline_tables):
    fresh = _account()
    stale = _account(username="_t_stale", fetched_at=NOW - timedelta(days=31))
    unknown = _account(username="_t_unknown", follower_count=None, fetched_at=None)
    await accounts_db.upsert_many([fresh, stale, unknown])

    cached = await accounts_db.get_cached(["_t_user", "_t_stale", "_t_unknown", "_t_missing"])
    assert set(cached) == {"_t_user"}  # 30일 이내인 것만
    assert cached["_t_user"].follower_count == 5000

    everyone = await accounts_db.get_many(["_t_user", "_t_stale", "_t_unknown"])
    assert set(everyone) == {"_t_user", "_t_stale", "_t_unknown"}
    assert everyone["_t_unknown"].follower_count is None


@requires_db
async def test_reels_upsert_and_query_by_keyword(clean_pipeline_tables):
    await accounts_db.upsert_many([_account()])
    reel = _reel(hashtags=["#테스트"])
    await reels_db.upsert_many([reel], keyword="키워드", business_type="업종")

    found = await reels_db.get_by_keyword("키워드", "업종")
    assert len(found) == 1
    assert found[0].code == reel.code
    assert found[0].video_url == reel.video_url  # 0005 마이그레이션 대상 컬럼
    assert found[0].hashtags == ["#테스트"]

    assert await reels_db.get_by_keyword("다른키워드", "업종") == []


@requires_db
async def test_reels_my_reel_excluded_from_keyword_pool(clean_pipeline_tables):
    """P5: is_my_reel=true 행은 get_by_keyword()가 항상 제외해야 한다
    (안 그러면 버킷 분류·대조 분석 표본이 오염된다)."""
    await accounts_db.upsert_many([_account(), _account(username="my_cafe")])
    pool_reel = _reel()
    my_reel = _reel(code="_t_myreel", username="my_cafe")
    await reels_db.upsert_many([pool_reel], keyword="키워드", business_type="업종")
    await reels_db.upsert_many(
        [my_reel], keyword="키워드", business_type="업종", is_my_reel=True
    )

    found = await reels_db.get_by_keyword("키워드", "업종")
    assert [r.code for r in found] == [pool_reel.code]

    fetched_my_reel = await reels_db.get_my_reel("키워드", "업종")
    assert fetched_my_reel is not None
    assert fetched_my_reel.code == "_t_myreel"


@requires_db
async def test_reel_metrics_upsert(clean_pipeline_tables):
    account = _account()
    reel = _reel()
    await accounts_db.upsert_many([account])
    await reels_db.upsert_many([reel], keyword="키워드", business_type="업종")

    scored = build_scored_reel(reel, account)
    await reel_metrics_db.upsert_many([scored])

    async with get_conn() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT bucket, engagement_rate, reach_multiple FROM reel_metrics "
                "WHERE reel_code = %s",
                (reel.code,),
            )
            row = await cur.fetchone()
    assert row is not None
    assert row["bucket"] == scored.bucket
    assert row["reach_multiple"] == scored.metrics.reach_multiple


@requires_db
async def test_shot_segments_partial_commit_then_vlm_update(clean_pipeline_tables):
    await accounts_db.upsert_many([_account()])
    await reels_db.upsert_many([_reel()], keyword="키워드", business_type="업종")

    assert await shot_segments_db.has_any("_t_reel") is False

    cuts = [
        Cut(index=i, t_start=float(i * 2), t_end=float(i * 2 + 2), frame_path="x")
        for i in range(3)
    ]
    await shot_segments_db.insert_cut_timings("_t_reel", cuts)

    assert await shot_segments_db.has_any("_t_reel") is True
    pending = await shot_segments_db.get_pending("_t_reel")
    assert [row["idx"] for row in pending] == [0, 1, 2]

    shot = VisionShotDescription(
        index=0, angle="클로즈업", subject="테스트 피사체", on_screen_text=None,
        movement="고정", purpose="후킹", technique=None, difficulty="하",
        requires=[], solo_alternative=None,
    )
    await shot_segments_db.update_vlm_fields("_t_reel", 0, shot, model="test-model")

    pending_after = await shot_segments_db.get_pending("_t_reel")
    assert [row["idx"] for row in pending_after] == [1, 2]  # idx 0은 이제 VLM 필드 채워짐


@requires_db
async def test_reel_analyses_upsert(clean_pipeline_tables):
    await accounts_db.upsert_many([_account()])
    await reels_db.upsert_many([_reel()], keyword="키워드", business_type="업종")

    await reel_analyses_db.upsert(
        reel_code="_t_reel", cut_count=3, avg_shot_sec=2.0, first_shot_sec=2.0,
        caption_hooks=["숫자 포함"], color_tone="따뜻함", subtitle_position="하단",
        summary="테스트 요약", model="test-model", analyzed_at=NOW,
    )

    async with get_conn() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT cut_count, color_tone, summary FROM reel_analyses WHERE reel_code = %s",
                ("_t_reel",),
            )
            row = await cur.fetchone()
    assert row == {"cut_count": 3, "color_tone": "따뜻함", "summary": "테스트 요약"}


@requires_db
async def test_collect_then_score_run_fake_mode_end_to_end(clean_pipeline_tables):
    """fake 모드(APIFY_MODE=fake, 기본값)로 collect.run() → score.run()이 실제로
    이어져서 도는지 확인한다. fixtures/collect/sample.json의 릴스 1개 기준."""
    req = AnalysisRequest(
        keyword="성수동카페", business_type="카페", constraints=UserConstraints()
    )
    job = await jobs_db.create_job(req)

    await collect.run(str(job.id))
    reels = await reels_db.get_by_keyword(req.keyword, req.business_type)
    assert len(reels) == 1
    assert reels[0].code == "Cabc123"  # fixtures/collect/sample.json 고정값

    await score.run(str(job.id))
    async with get_conn() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT bucket FROM reel_metrics WHERE reel_code = %s", (reels[0].code,)
            )
            row = await cur.fetchone()
    assert row is not None


@requires_db
async def test_compare_compute_comparison_reads_reel_analyses_and_shot_segments(
    clean_pipeline_tables,
):
    """reel_analyses+shot_segments를 조인해서 ReelAnalysis를 재구성하는 경로 확인.
    릴스 1개뿐이라 breakout 풀이 15개 미만 → sufficient=False로 끝나는 걸 확인한다
    (n>=15 가드 자체는 tests/pipeline/test_compare_logic.py에서 이미 순수 함수로 검증함)."""
    await accounts_db.upsert_many([_account()])
    reel = _reel()
    await reels_db.upsert_many([reel], keyword="키워드", business_type="업종")

    cuts = [Cut(index=0, t_start=0.0, t_end=2.0, frame_path="x")]
    await shot_segments_db.insert_cut_timings(reel.code, cuts)
    shot = VisionShotDescription(
        index=0, angle="정면샷", subject="테스트", on_screen_text=None,
        movement="고정", purpose="정보", technique=None, difficulty="하",
        requires=[], solo_alternative=None,
    )
    await shot_segments_db.update_vlm_fields(reel.code, 0, shot, model="test-model")
    await reel_analyses_db.upsert(
        reel_code=reel.code, cut_count=1, avg_shot_sec=2.0, first_shot_sec=2.0,
        caption_hooks=[], color_tone="밝음", subtitle_position="없음",
        summary="테스트", model="test-model", analyzed_at=NOW,
    )

    result = await compare.compute_comparison("키워드", "업종")

    assert result.sufficient is False
    assert result.high_n <= 1
    assert result.findings == []


@requires_db
async def test_guides_create_and_get_latest_by_job(clean_pipeline_tables):
    req = AnalysisRequest(
        keyword="성수동카페", business_type="카페", constraints=UserConstraints()
    )
    job = await jobs_db.create_job(req)

    guide = Guide(
        business_type="카페", keyword="성수동카페", week_of=date(2026, 8, 10),
        shot_list=[
            ShotListItem(
                order=1, t_start_sec=0.0, duration_sec=2.0, angle="클로즈업",
                subject="테스트", on_screen_text=None, note="테스트 요령",
            )
        ],
        caption_drafts=[CaptionDraft(text="테스트 캡션", pattern="숫자 포함")],
        audio=[], diagnosis=[],
        evidence_note="테스트 근거", confidence="충분", caveat=None,
    )
    await guides_db.create(
        job_id=job.id, business_type="카페", keyword="성수동카페",
        week_of=date(2026, 8, 10), guide=guide,
    )

    fetched = await guides_db.get_latest_by_job(job.id)
    assert fetched is not None
    assert fetched.confidence == "충분"
    assert fetched.shot_list[0].subject == "테스트"

    other_job = await jobs_db.create_job(req)
    assert await guides_db.get_latest_by_job(other_job.id) is None


@requires_db
async def test_bucket_configs_get_boundaries_falls_back_to_global_default(clean_pipeline_tables):
    boundaries = await bucket_configs_db.get_boundaries("_t_업종_없음")
    # 0001 마이그레이션이 심어둔 전역 기본값(business_type IS NULL, source='fixed').
    assert boundaries == {"B1": 1000, "B2": 10000, "B3": 100000}


@requires_db
async def test_bucket_configs_save_and_get_percentile_boundaries(clean_pipeline_tables):
    business_type = "_t_분위수업종"
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM bucket_configs WHERE business_type = %s", (business_type,)
            )
        await conn.commit()

    await bucket_configs_db.save_percentile_boundaries(
        business_type, {"B1": 300, "B2": 3000, "B3": 100000}, sample_size=250
    )
    boundaries = await bucket_configs_db.get_boundaries(business_type)
    assert boundaries == {"B1": 300, "B2": 3000, "B3": 100000}

    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM bucket_configs WHERE business_type = %s", (business_type,)
            )
        await conn.commit()


@requires_db
async def test_resolve_bucket_boundaries_switches_to_percentile_past_threshold(
    clean_pipeline_tables,
):
    """docs/02-contracts.md: 업종 누적 200건 초과 시 33/66 분위수로 교체."""
    business_type = "_t_percentile_biz"
    accounts = [_account(username=f"_t_pb_{i}", follower_count=(i + 1) * 100) for i in range(30)]
    await accounts_db.upsert_many(accounts)

    reels = [
        _reel(code=f"_t_pb_reel_{i}", username=f"_t_pb_{i % 30}") for i in range(210)
    ]
    await reels_db.upsert_many(reels, keyword="아무키워드", business_type=business_type)

    boundaries = await score.resolve_bucket_boundaries(business_type)

    assert boundaries != {"B1": 1000, "B2": 10000, "B3": 100000}
    assert boundaries["B1"] < boundaries["B2"]
    assert boundaries["B3"] == 100_000  # B3는 분위수로 안 바뀌고 고정(판단, score.py 참조)

    # 이력으로 저장까지 됐는지 확인 — 이후 compute_tracks()가 이 값을 읽어야 한다.
    saved = await bucket_configs_db.get_boundaries(business_type)
    assert saved == boundaries

    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM bucket_configs WHERE business_type = %s", (business_type,)
            )
        await conn.commit()


@requires_db
async def test_resolve_bucket_boundaries_stays_fixed_under_threshold(clean_pipeline_tables):
    business_type = "_t_small_biz"
    await accounts_db.upsert_many([_account()])
    await reels_db.upsert_many([_reel()], keyword="키워드", business_type=business_type)

    boundaries = await score.resolve_bucket_boundaries(business_type)

    assert boundaries == {"B1": 1000, "B2": 10000, "B3": 100000}


@requires_db
async def test_analyze_run_updates_progress_per_reel(clean_pipeline_tables, monkeypatch):
    """docs/05-api.md·07-ui.md: analyzing은 "7/20" 형태 개별 진행을 노출해야 하는데
    `jobs_db.update_progress()`가 어느 파이프라인 모듈에서도 호출된 적이 없었다
    (발견, 2026-08-18). 프레임/VLM 의존 없이 진행률 갱신 자체만 검증한다."""
    req = AnalysisRequest(
        keyword="성수동카페", business_type="카페", constraints=UserConstraints()
    )
    job = await jobs_db.create_job(req)

    reels = [_reel(code=f"_t_progress_{i}") for i in range(3)]
    monkeypatch.setattr(analyze, "select_target_reels", AsyncMock(return_value=reels))
    monkeypatch.setattr(analyze, "process_reel", AsyncMock(return_value=None))

    await analyze.run(str(job.id))

    updated = await jobs_db.get_job(job.id)
    assert updated is not None
    assert updated.progress_current == 3
    assert updated.progress_total == 3


@requires_db
async def test_diagnose_run_noop_when_no_my_reel_url(clean_pipeline_tables):
    req = AnalysisRequest(
        keyword="성수동카페", business_type="카페", constraints=UserConstraints()
    )
    job = await jobs_db.create_job(req)

    await diagnose.run(str(job.id))

    assert await reels_db.get_my_reel("성수동카페", "카페") is None


@requires_db
async def test_diagnose_run_fake_mode_commits_my_reel(clean_pipeline_tables):
    """fake 모드(APIFY_MODE=fake)로 diagnose.run()이 fixtures/collect/sample.json의
    "my_reel"을 `is_my_reel=true`로 커밋하는지 확인한다. fixture의 video_url이 null이라
    frames.process_reel은 다운로드 없이 스킵한다(실 mp4/VLM 없이 자동화하기 위한 한계 —
    파일 상단 설명과 동일한 이유)."""
    req = AnalysisRequest(
        keyword="성수동카페", business_type="카페", constraints=UserConstraints(),
        my_reel_url="https://instagram.com/reel/Cmyreel1",
    )
    job = await jobs_db.create_job(req)

    await diagnose.run(str(job.id))

    my_reel = await reels_db.get_my_reel("성수동카페", "카페")
    assert my_reel is not None
    assert my_reel.code == "Cmyreel1"
    assert my_reel.username == "my_cafe"
    # 키워드 풀 조회에서는 여전히 제외돼야 한다.
    assert my_reel.code not in [r.code for r in await reels_db.get_by_keyword("성수동카페", "카페")]
