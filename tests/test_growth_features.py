from pathlib import Path

from app.api.gemini import _normalize_analysis
from app.api.guide_media import download_flux_guide, generate_elevenlabs_voiceover, generate_flux_guide
from app.ui.workspace import _build_full_variants, _script_segments
from app.core.audio_rights import classify_audio_rights, recommend_audio_options, save_rights_verification
from app.core.auth import delete_cloud_account
from app.core.creator_memory import learn_creator_patterns, personalize_with_memory
from app.core.content_projects import create_project, list_projects, next_action, pipeline_counts, update_project
from app.core.market_watch import (
    build_market_alerts,
    build_market_snapshot,
    compare_snapshots,
    filter_new_alerts,
    load_jsonl_history,
    load_previous_snapshot,
    save_watch,
    mark_alerts_sent,
    save_snapshot,
)
from app.core.performance_insights import (
    build_prediction_calibration,
    compare_prediction_to_actual,
    compare_snapshot_windows,
    normalize_insights,
)
from app.core.timeline_analyzer import build_signal_timeline
from app.core.job_queue import cancel_job, claim_next_job, complete_job, enqueue_job, get_job, list_jobs
from app.core.observability import enforce_daily_limit, load_recent_events, record_api_usage, redact
from app.core.privacy import delete_user_data, export_user_data, user_namespace
from app.core.token_vault import delete_encrypted_token, load_encrypted_token, save_encrypted_token
from app.core.signal_studies import add_signal, build_signal_synthesis, build_visual_synthesis, load_study, remove_signal


def test_normalize_insights_keeps_measured_metrics_separate():
    result = normalize_insights({
        "plays": 1000,
        "reach": 800,
        "likes": 80,
        "comments": 10,
        "saved": 30,
        "shares": 20,
        "ig_reels_avg_watch_time": 7500,
    })

    assert result["views"] == 1000
    assert result["avg_watch_seconds"] == 7.5
    assert result["engagement_rate"] == 17.5
    assert result["source"] == "measured"


def test_prediction_comparison_labels_ai_and_meta_values():
    result = compare_prediction_to_actual(
        {"overall_score": 70},
        {"views": 1000, "reach": 1000, "likes": 100, "saved": 40, "shares": 20},
    )

    assert result["predicted_label"] == "AI 예상"
    assert result["actual_label"] == "Meta 실측"
    assert result["predicted_score"] == 70
    assert result["actual_score"] > 0


def test_creator_memory_prefers_patterns_from_better_half():
    reels = [
        {"조회수": 1000, "총점": 90, "길이(초)": 18, "촬영구도": "클로즈업", "analysis": {"hook_text": "메뉴 먼저"}},
        {"조회수": 900, "총점": 82, "길이(초)": 20, "촬영구도": "클로즈업", "analysis": {"hook_text": "메뉴 먼저"}},
        {"조회수": 400, "총점": 40, "길이(초)": 50, "촬영구도": "정면샷", "analysis": {"hook_text": "매장 소개"}},
    ]

    memory = learn_creator_patterns(reels)
    guide = personalize_with_memory({"camera": "탑뷰", "camera_reason": "trend"}, memory)

    assert memory["status"] == "provisional"
    assert memory["top_cameras"][0] == "클로즈업"
    assert guide["camera"] == "클로즈업"


def test_audio_rights_does_not_claim_mainstream_track_is_safe():
    result = classify_audio_rights({"곡명": "Espresso", "아티스트": "Sabrina Carpenter"})

    assert result["level"] == "restricted"
    assert "제한" in result["status"]


def test_market_snapshots_find_new_accounts_and_deltas():
    previous = build_market_snapshot(
        [{"username": "shop_a", "ig_play_count": 100, "like_count": 10}],
        "성수동카페",
    )
    current = build_market_snapshot(
        [
            {"username": "shop_a", "ig_play_count": 180, "like_count": 20},
            {"username": "shop_b", "ig_play_count": 300, "like_count": 25},
        ],
        "성수동카페",
    )

    changes = compare_snapshots(previous, current)

    assert changes[0]["username"] == "shop_b"
    assert changes[0]["is_new"] is True
    assert next(item for item in changes if item["username"] == "shop_a")["view_delta"] == 80


def test_market_alerts_use_stable_media_ids():
    previous = build_market_snapshot(
        [{"id": "same", "username": "shop_a", "ig_play_count": 1000}],
        "성수동카페",
    )
    current = build_market_snapshot(
        [
            {"id": "same", "username": "shop_a", "ig_play_count": 12000},
            {"id": "new", "username": "shop_b", "ig_play_count": 25000},
        ],
        "성수동카페",
    )

    alerts = build_market_alerts(previous, current, min_views=10000)

    assert {item["type"] for item in alerts} == {"fast_growth", "new_breakout"}


def test_prediction_calibration_uses_measured_pairs():
    reels = [
        {
            "analysis": {"overall_score": 50},
            "insights": {"views": 1000, "reach": 1000, "likes": 100, "saved": 40, "shares": 20},
        }
        for _ in range(5)
    ]

    calibration = build_prediction_calibration(reels)
    comparison = compare_prediction_to_actual(reels[0]["analysis"], reels[0]["insights"], calibration)

    assert calibration["sample_count"] == 5
    assert calibration["confidence"] == "low"
    assert comparison["predicted_score"] == comparison["actual_score"]


def test_signal_timeline_detects_stagnant_segment():
    visual = [
        {"timestamp_seconds": second + 0.1, "motion": 0.05 if 2 <= second <= 4 else 0.5, "brightness": 0.5}
        for second in range(7)
    ]
    audio = [0.5, 0.5, 0.05, 0.05, 0.05, 0.5, 0.5]

    result = build_signal_timeline(visual, audio, duration=7)

    risks = [item for item in result["timeline_diagnostics"] if item["kind"] == "risk"]
    assert any(item["timestamp_seconds"] == 2 for item in risks)
    assert len(result["timeline_signals"]) == 7


def test_audio_verification_registry_records_evidence(tmp_path):
    path = tmp_path / "rights.json"
    record = save_rights_verification(
        "Safe Track",
        "meta_sound_collection",
        "Meta Sound Collection business use",
        "https://example.com/evidence",
        path=path,
    )

    result = classify_audio_rights({"곡명": "Safe Track", **record})
    assert result["level"] == "safe"


def test_expired_audio_license_is_restricted(tmp_path):
    path = tmp_path / "rights.json"
    record = save_rights_verification(
        "Old Track",
        "licensed_by_business",
        "Commercial license",
        expires_at="2020-01-01",
        path=path,
    )
    result = classify_audio_rights({"곡명": "Old Track", **record})
    assert result["level"] == "restricted"
    assert "만료" in result["status"]


def test_market_snapshot_loading_and_alert_deduplication(tmp_path):
    snapshot_dir = tmp_path / "snapshots"
    snapshot = build_market_snapshot([{"id": "a", "username": "shop", "ig_play_count": 10}], "성수카페")
    save_snapshot(snapshot, snapshot_dir)
    assert load_previous_snapshot("성수카페", snapshot_dir)["query"] == "성수카페"

    state_path = tmp_path / "alerts.json"
    alerts = [{"type": "new_breakout", "media_id": "a", "message": "hit", "url": "https://example.com"}]
    assert len(filter_new_alerts("성수카페", alerts, state_path)) == 1
    mark_alerts_sent("성수카페", alerts, state_path)
    assert filter_new_alerts("성수카페", alerts, state_path) == []


def test_gemini_analysis_normalizes_scores_and_timeline():
    result = _normalize_analysis({
        "category_scores": {"hook": 110, "pacing": 70},
        "subject_bbox": {"x": -5, "y": 30, "width": 120, "height": 40},
        "subtitle_bbox": {"x": 8, "y": 80, "width": 84, "height": 12},
        "timeline_diagnostics": [
            {
                "timestamp_seconds": 2.5,
                "kind": "risk",
                "title": "느린 도입",
                "predicted_retention": 73,
            }
        ],
    })

    assert result["category_scores"]["hook"] == 100
    assert result["overall_score"] == 85
    assert result["timeline_diagnostics"][0]["confidence"] == "low"
    assert result["subject_bbox"] == {"x": 0.0, "y": 30.0, "width": 100.0, "height": 40.0}
    assert result["subtitle_bbox"]["y"] == 80.0


def test_gemini_analysis_converts_standard_box_2d_coordinates():
    result = _normalize_analysis({
        "subject_box_2d": [300, 100, 750, 800],
        "subtitle_box_2d": [80, 80, 200, 920],
    })

    assert result["subject_bbox"] == {"x": 10.0, "y": 30.0, "width": 70.0, "height": 45.0}
    assert result["subtitle_bbox"] == {"x": 8.0, "y": 8.0, "width": 84.0, "height": 12.0}


def test_job_queue_claim_complete_and_deduplicate(tmp_path):
    db_path = tmp_path / "jobs.sqlite3"
    first = enqueue_job("video_analysis_file", {"video_path": "sample.mp4"}, "same", path=db_path)
    duplicate = enqueue_job("video_analysis_file", {"video_path": "sample.mp4"}, "same", path=db_path)
    assert first["id"] == duplicate["id"]

    claimed = claim_next_job(path=db_path)
    assert claimed["id"] == first["id"]
    assert claimed["status"] == "running"

    complete_job(first["id"], {"ok": True}, path=db_path)
    completed = get_job(first["id"], path=db_path)
    assert completed["status"] == "completed"
    assert completed["progress"] == 100
    assert completed["result"]["ok"] is True


def test_pending_job_can_be_cancelled(tmp_path):
    db_path = tmp_path / "jobs.sqlite3"
    job = enqueue_job("video_analysis_url", {"video_url": "https://example.com/reel"}, path=db_path)
    assert cancel_job(job["id"], path=db_path) is True
    assert get_job(job["id"], path=db_path)["status"] == "cancelled"


def test_running_job_cancellation_cannot_be_overwritten(tmp_path):
    db_path = tmp_path / "jobs.sqlite3"
    job = enqueue_job("video_analysis_url", {"video_url": "https://example.com/reel"}, path=db_path)
    claim_next_job(path=db_path)
    assert cancel_job(job["id"], path=db_path) is True
    assert complete_job(job["id"], {"late": True}, path=db_path) is False
    cancelled = get_job(job["id"], path=db_path)
    assert cancelled["status"] == "cancelled"
    assert cancelled["result"] == {}


def test_job_queue_filters_owners(tmp_path):
    db_path = tmp_path / "jobs.sqlite3"
    own = enqueue_job("video_analysis_url", {"video_url": "https://example.com/a"}, owner_id="user-a", path=db_path)
    enqueue_job("video_analysis_url", {"video_url": "https://example.com/b"}, owner_id="user-b", path=db_path)
    visible = list_jobs(owner_id="user-a", path=db_path)
    assert [item["id"] for item in visible] == [own["id"]]
    assert cancel_job(own["id"], owner_id="user-b", path=db_path) is False


def test_snapshot_windows_compare_fixed_lookbacks():
    history = [
        {"captured_at": "2026-01-01T00:00:00", "insights": {"views": 100, "reach": 80}},
        {"captured_at": "2026-01-02T00:00:00", "insights": {"views": 180, "reach": 140}},
        {"captured_at": "2026-01-08T00:00:00", "insights": {"views": 500, "reach": 400}},
    ]
    result = compare_snapshot_windows(history)
    assert result["24"]["views_delta"] == 320
    assert result["168"]["views_delta"] == 400


def test_observability_redacts_secrets_and_enforces_limits(tmp_path):
    redacted = redact({"access_token": "secret", "message": "Bearer abc123", "safe": "value"})
    assert redacted["access_token"] == "[REDACTED]"
    assert "abc123" not in redacted["message"]
    assert redacted["safe"] == "value"

    usage_path = tmp_path / "usage.jsonl"
    record_api_usage("gemini", path=usage_path)
    try:
        enforce_daily_limit("gemini", max_calls=1, path=usage_path)
        assert False, "Expected daily limit failure"
    except RuntimeError:
        pass


def test_market_preferences_and_delivery_history(tmp_path):
    watch_path = tmp_path / "market_watchlist.json"
    watches = save_watch(
        "성수카페",
        "카페",
        "성수",
        path=watch_path,
        alerts_enabled=False,
        min_views=25000,
    )
    assert watches[0]["alerts_enabled"] is False
    assert watches[0]["min_views"] == 25000

    history_path = tmp_path / "delivery.jsonl"
    history_path.write_text('{"status":"sent"}\nnot-json\n', encoding="utf-8")
    assert load_jsonl_history(history_path) == [{"status": "sent"}]


def test_recent_events_can_filter_failures(tmp_path):
    log_path = tmp_path / "events.jsonl"
    log_path.write_text(
        '{"event":"gemini.completed"}\n{"event":"apify.failed","error":"timeout"}\n',
        encoding="utf-8",
    )
    assert [item["event"] for item in load_recent_events(path=log_path, failures_only=True)] == ["apify.failed"]


def test_meta_token_vault_encrypts_and_deletes(tmp_path):
    from cryptography.fernet import Fernet

    path = tmp_path / "meta_token.enc"
    key = Fernet.generate_key().decode("ascii")
    save_encrypted_token("very-secret-token", key, path, {"account": "shop"})
    assert b"very-secret-token" not in path.read_bytes()
    stored = load_encrypted_token(key, path)
    assert stored["token"] == "very-secret-token"
    assert stored["metadata"]["account"] == "shop"
    assert delete_encrypted_token(path) is True
    assert not path.exists()


def test_cloud_account_deletion_uses_admin_api(monkeypatch):
    deleted = []

    class Admin:
        def delete_user(self, user_id):
            deleted.append(user_id)

    class Auth:
        admin = Admin()

    class Client:
        auth = Auth()

    monkeypatch.setattr("app.core.auth.require_env", lambda name, context: "configured")
    monkeypatch.setattr("app.core.auth.create_client", lambda url, key: Client())
    delete_cloud_account("user-123")
    assert deleted == ["user-123"]


def test_meta_sync_writes_to_user_specific_paths(monkeypatch, tmp_path):
    from app.core import meta_sync

    user_dir = tmp_path / "user-a"
    user_dir.mkdir()
    (user_dir / "store_profile.json").write_text('{"store_id":"store-a"}', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(meta_sync, "collect_my_reels", lambda access_token, limit: {
        "profile": {"id": "ig-a", "username": "shop_a"},
        "graph_version": "v-test",
        "reels": [{
            "id": "reel-a",
            "caption": "오늘의 메뉴",
            "permalink": "https://example.com/reel-a",
            "insights": {"views": 100, "likes": 10, "saved": 2, "shares": 1},
        }],
    })
    monkeypatch.setattr(meta_sync, "record_api_usage", lambda *args, **kwargs: {})
    monkeypatch.setattr(meta_sync, "has_env", lambda name: False)

    result = meta_sync.run_meta_sync(
        access_token="token-a",
        business_type="카페",
        library_path=user_dir / "library.jsonl",
        store_profile_path=user_dir / "store_profile.json",
        performance_history_path=user_dir / "performance_history.jsonl",
    )
    assert result["synced_reels"] == 1
    assert "reel-a" in (user_dir / "library.jsonl").read_text(encoding="utf-8")
    assert "reel-a" in (user_dir / "performance_history.jsonl").read_text(encoding="utf-8")
    assert not (tmp_path / "user_reels" / "library.jsonl").exists()


def test_content_project_moves_through_workflow(tmp_path):
    path = tmp_path / "projects.json"
    project = create_project(
        "신메뉴 릴스",
        path,
        business_type="카페",
        concept="크림이 올라가는 순간",
        source={"type": "competitor_signal", "url": "https://example.com/reel"},
    )
    assert project["stage"] == "idea"
    assert "훅" in next_action(project)

    updated = update_project(
        project["id"],
        {"hook": "크림이 무너지기 전 3초", "shot_list": ["완성 컷", "크림 클로즈업"], "stage": "shoot"},
        path,
    )
    assert updated["stage"] == "shoot"
    assert updated["shot_list"] == ["완성 컷", "크림 클로즈업"]
    projects = list_projects(path)
    assert projects[0]["source"]["type"] == "competitor_signal"
    assert pipeline_counts(projects)["shoot"] == 1


def test_content_project_persists_workspace_fields(tmp_path):
    path = tmp_path / "projects.json"
    project = create_project("주말 메뉴", path, business_type="카페", concept="김이 나는 장면")

    saved = update_project(
        project["id"],
        {
            "script_variants": {"sales": "오늘만", "story": "아침부터 준비"},
            "edit_notes": [{"text": "첫 장면을 당기기", "done": True}],
            "audio": {"name": "Owned track", "rights_source": "owned"},
            "guide_assets": {"image": {"path": str(tmp_path / "guide.jpeg")}},
        },
        path,
    )

    assert saved["script_variants"]["sales"] == "오늘만"
    assert saved["edit_notes"][0]["done"] is True
    assert saved["audio"]["rights_source"] == "owned"
    assert saved["guide_assets"]["image"]["path"].endswith("guide.jpeg")


def test_signal_study_persists_selections_and_builds_evidence_brief(tmp_path):
    path = tmp_path / "radar_study.json"
    first = {
        "media_id": "one", "username": "shop_a", "url": "https://example.com/one",
        "caption": "크림라떼 만드는 순간 #성수카페 #크림라떼", "views": 1000,
    }
    second = {
        "media_id": "two", "username": "shop_b", "url": "https://example.com/two",
        "caption": "크림라떼 비밀 공개 #성수카페 #크림라떼", "views": 3000,
    }
    add_signal(first, path)
    add_signal(second, path)

    study = load_study(path)
    brief = build_signal_synthesis(study["items"])

    assert len(study["items"]) == 2
    assert brief["sample_count"] == 2
    assert "크림라떼" in brief["repeated_terms"]
    assert "#성수카페" in brief["repeated_hashtags"]
    assert brief["confidence"] == "medium"
    assert {item["id"] for item in brief["common_patterns"]} >= {"sensory", "local_discovery"}
    assert brief["term_evidence"][0]["reel_count"] == 2
    assert len(remove_signal("one", path)["items"]) == 1


def test_signal_commonality_counts_distinct_reels_not_repeated_words_in_one_caption():
    brief = build_signal_synthesis([
        {"username": "a", "caption": "크림 크림 크림 단면 단면"},
        {"username": "b", "caption": "햇살이 좋은 넓은 공간"},
    ])

    assert "크림" not in brief["repeated_terms"]
    assert "단면" not in brief["repeated_terms"]
    assert brief["common_patterns"] == []


def test_signal_patterns_include_per_reel_evidence_and_change_the_plan():
    sensory = build_signal_synthesis([
        {"username": "a", "caption": "바삭한 단면과 크림 질감을 가까이 공개"},
        {"username": "b", "caption": "크림을 자르면 촉촉한 단면이 보여요"},
    ], query="소금빵")
    atmosphere = build_signal_synthesis([
        {"username": "c", "caption": "햇살 좋은 창가 좌석과 우드톤 인테리어"},
        {"username": "d", "caption": "넓은 공간과 창가 분위기가 좋은 데이트 장소"},
    ], query="브런치 카페")

    assert sensory["common_patterns"][0]["id"] == "sensory"
    assert sensory["common_patterns"][0]["reel_count"] == 2
    assert len(sensory["common_patterns"][0]["evidence"]) == 2
    assert atmosphere["common_patterns"][0]["id"] == "atmosphere"
    assert sensory["storyboard_plan"] != atmosphere["storyboard_plan"]
    assert len(sensory["storyboard_plan"]) == 5
    assert len(atmosphere["storyboard_plan"]) == 5


def test_signal_study_aggregates_only_selected_visual_evidence():
    items = [{"media_id": "one"}, {"media_id": "two"}]
    result = build_visual_synthesis(
        {
            "one": {"camera_angles": ["클로즈업", "탑뷰"], "subtitle_position": "상단", "cut_speed": "빠름", "bgm_mood": "신나는", "subject_bbox": {"x": 10, "y": 30, "width": 60, "height": 40}, "subtitle_bbox": {"x": 8, "y": 8, "width": 84, "height": 12}},
            "two": {"camera_angles": ["클로즈업"], "subtitle_position": "상단", "cut_speed": "빠름", "bgm_mood": "신나는", "subject_bbox": {"x": 20, "y": 40, "width": 50, "height": 30}, "subtitle_bbox": {"x": 10, "y": 12, "width": 80, "height": 10}},
            "not-selected": {"camera_angles": ["정면샷"]},
        },
        items,
    )

    assert result["analyzed_count"] == 2
    assert result["top_camera"] == "클로즈업"
    assert result["top_subtitle_position"] == "상단"
    assert result["subject_bbox"] == {"x": 15.0, "y": 35.0, "width": 55.0, "height": 35.0}
    assert result["subtitle_bbox"]["y"] == 10.0
    assert result["confidence"] == "low"


def test_visual_synthesis_does_not_call_a_one_reel_label_common():
    result = build_visual_synthesis(
        {
            "one": {"camera_angles": ["탑뷰", "탑뷰"], "subtitle_position": "상단"},
            "two": {"camera_angles": ["정면샷"], "subtitle_position": "하단"},
        },
        [{"media_id": "one"}, {"media_id": "two"}],
    )

    assert result["top_camera"] == ""
    assert result["top_subtitle_position"] == ""


def test_visual_synthesis_rejects_spatially_unrelated_boxes():
    result = build_visual_synthesis(
        {
            "one": {"subject_bbox": {"x": 2, "y": 5, "width": 25, "height": 20}},
            "two": {"subject_bbox": {"x": 70, "y": 75, "width": 25, "height": 20}},
        },
        [{"media_id": "one"}, {"media_id": "two"}],
    )

    assert result["subject_bbox"] == {"x": 36.0, "y": 40.0, "width": 25.0, "height": 20.0}
    assert result["subject_bbox_count"] == 2
    assert result["subject_bbox_basis"] == "observed_median"


def test_visual_synthesis_aggregates_each_normalized_video_segment_separately():
    def sequence(offset):
        return [{
            "segment_index": index,
            "timestamp_seconds": index * 2 + offset,
            "subject_bbox": {"x": 10 + index * 8 + offset, "y": 20 + index * 6, "width": 50, "height": 30},
            "subtitle_bbox": {"x": 8, "y": 8 + index * 15, "width": 84, "height": 10},
            "camera": "클로즈업" if index < 2 else "와이드샷",
        } for index in range(5)]

    result = build_visual_synthesis(
        {
            "one": {"duration_seconds": 10, "composition_sequence": sequence(0)},
            "two": {"duration_seconds": 24, "composition_sequence": sequence(2)},
        },
        [{"media_id": "one"}, {"media_id": "two"}],
    )

    assert result["sequence_analyzed_count"] == 2
    assert len(result["sequence_geometry"]) == 5
    assert result["sequence_geometry"][0]["subject_bbox"]["x"] == 11.0
    assert result["sequence_geometry"][4]["subject_bbox"]["x"] == 43.0
    assert result["sequence_geometry"][0]["normalized_start"] == 0
    assert result["sequence_geometry"][4]["normalized_end"] == 100


def test_visual_synthesis_detects_common_zoom_from_real_sequence_boxes():
    def sequence(offset):
        widths = [35, 55, 60, 58, 50]
        return [{
            "segment_index": index,
            "subject_bbox": {"x": 20 + offset, "y": 30, "width": widths[index], "height": widths[index] * .6},
        } for index in range(5)]

    result = build_visual_synthesis(
        {"one": {"composition_sequence": sequence(0)}, "two": {"composition_sequence": sequence(2)}},
        [{"media_id": "one", "rank_score": 9}, {"media_id": "two", "rank_score": 8}],
    )

    first_motion = result["sequence_motion"][0]
    assert first_motion["motion_type"] == "zoom_in"
    assert first_motion["motion_basis"] == "common"
    assert first_motion["evidence_count"] == 2


def test_visual_synthesis_uses_top_reel_zoom_when_motion_disagrees():
    def sequence(first_width, second_width):
        return [
            {"segment_index": 0, "subject_bbox": {"x": 20, "y": 30, "width": first_width, "height": 30}},
            {"segment_index": 1, "subject_bbox": {"x": 20, "y": 30, "width": second_width, "height": 30}},
        ]

    result = build_visual_synthesis(
        {"top": {"composition_sequence": sequence(70, 35)}, "lower": {"composition_sequence": sequence(35, 70)}},
        [
            {"media_id": "top", "username": "winner", "rank_score": 10},
            {"media_id": "lower", "username": "runnerup", "rank_score": 2},
        ],
    )

    first_motion = result["sequence_motion"][0]
    assert first_motion["motion_type"] == "zoom_out"
    assert first_motion["motion_basis"] == "top_reel"
    assert first_motion["source_label"] == "winner"


def test_full_script_variants_include_sequence_and_cta():
    variants = _build_full_variants({"title": "크림라떼", "concept": "크림이 올라가는 장면", "hook": "크림이 무너지기 전"})

    assert all("0-2초" in value and "CTA:" in value for value in variants.values())
    assert "5-10초" in variants["sales"]


def test_script_segments_split_timed_script_into_cards():
    segments = _script_segments("0-2초 | 완성 컷\n2~5초 | 디테일 확대\n마지막 2초 | 저장하세요")

    assert [segment["time"] for segment in segments] == ["0–2초", "2–5초", "마지막 2초"]
    assert segments[1]["content"] == "디테일 확대"


def test_guide_media_uses_provider_results_and_caches_image(monkeypatch, tmp_path):
    class Response:
        def __init__(self, payload=None, content=b""):
            self.payload = payload or {}
            self.content = content

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    monkeypatch.setenv("BFL_API_KEY", "test-key")
    monkeypatch.setattr("app.api.guide_media.time.sleep", lambda _: None)
    monkeypatch.setattr(
        "app.api.guide_media.requests.post",
        lambda *args, **kwargs: Response({"polling_url": "https://example.com/poll"}),
    )
    monkeypatch.setattr(
        "app.api.guide_media.requests.get",
        lambda url, **kwargs: Response({"status": "Ready", "result": {"sample": "https://example.com/image.jpeg"}})
        if url.endswith("/poll") else Response(content=b"jpeg-bytes"),
    )

    image = generate_flux_guide("vertical coffee reel")
    saved = download_flux_guide(image["sample_url"], tmp_path / "guide.jpeg")

    assert image["provider"] == "bfl_flux"
    assert Path(saved).read_bytes() == b"jpeg-bytes"


def test_guide_media_returns_elevenlabs_audio(monkeypatch):
    class Response:
        content = b"mp3-bytes"

        def raise_for_status(self):
            return None

    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "voice-id")
    monkeypatch.setattr("app.api.guide_media.requests.post", lambda *args, **kwargs: Response())

    assert generate_elevenlabs_voiceover("안녕하세요") == b"mp3-bytes"


def test_audio_recommendations_offer_multiple_ranked_choices():
    project = {
        "title": "망원동 브런치",
        "concept": "햇살 좋은 공간과 메뉴 디테일",
        "source": {"query": "망원동 카페", "visual_synthesis": {"top_cut_speed": "보통"}},
    }

    options = recommend_audio_options(project)

    assert len(options) == 5
    assert len({option["id"] for option in options}) == 5
    assert options[0]["keywords"]
    assert options[0]["reason"]


def test_user_data_export_and_delete_dry_run(tmp_path):
    auth_user_id = "auth-user-1"
    source = tmp_path / "data" / user_namespace(auth_user_id)
    source.mkdir(parents=True)
    (source / "library.jsonl").write_text("{}\n", encoding="utf-8")
    archive = export_user_data(auth_user_id, base_dir=tmp_path / "data", output_dir=tmp_path / "exports")
    assert archive.exists()
    files = delete_user_data(auth_user_id, base_dir=tmp_path / "data", dry_run=True)
    assert files and source.exists()


def test_worker_processes_a_queued_file(monkeypatch, tmp_path):
    from scripts import run_job_worker

    video = tmp_path / "sample.mp4"
    video.write_bytes(b"placeholder")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(run_job_worker, "analyze_reel_from_file", lambda path, caption="": {"overall_score": 77})
    monkeypatch.setattr(run_job_worker, "format_report", lambda analysis: f"score={analysis['overall_score']}")
    job = {"id": "job-1", "kind": "video_analysis_file", "payload": {"video_path": str(video), "title": "sample"}}
    monkeypatch.setattr(run_job_worker, "update_progress", lambda *args, **kwargs: None)
    result = run_job_worker.process_job(job)
    assert result["analysis"]["overall_score"] == 77
    assert Path(result["report_path"]).exists()


def test_reel_list_html_escapes_content_and_blocks_unsafe_links():
    from app.ui.workspace import _reel_list_html

    html_out = _reel_list_html([
        {"username": "cafe<script>", "caption": "<img src=x onerror=alert(1)> 크림라떼", "url": "javascript:alert(1)",
         "thumbnail_url": "https://cdn.example.com/a.jpg", "views": 12345, "published_at": "2026-09-30T10:00:00"},
        {"username": "plain", "caption": "", "url": "https://www.instagram.com/reel/ABC/", "thumbnail_url": "", "video_url": ""},
    ])
    assert "<script>" not in html_out and "onerror=alert" not in html_out.replace("&lt;img src=x onerror=alert(1)&gt;", "")
    assert "javascript:" not in html_out
    assert "조회 12,345" in html_out and "2026-09-30" in html_out
    assert 'href="https://www.instagram.com/reel/ABC/"' in html_out and 'rel="noopener noreferrer"' in html_out
    assert "캡션 없음" in html_out and "영상·썸네일 없음" in html_out and "분석 가능" in html_out
