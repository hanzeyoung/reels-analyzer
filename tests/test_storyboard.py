import base64
import json
from urllib.parse import parse_qs, urlparse

from app.core.storyboard import build_mobile_coach_url, build_project_storyboard


def test_storyboard_uses_each_projects_hook_shots_and_composition():
    latte = {
        "id": "latte-project",
        "title": "비 오는 날 크림라떼",
        "concept": "크림이 천천히 무너지는 라떼",
        "hook": "비 오는 날엔 이 라떼부터 보세요",
        "shot_list": ["완성된 라떼 탑뷰", "크림 질감 클로즈업", "우유를 따르는 손", "창가 좌석과 매장 분위기", "저장하고 방문하기"],
    }
    nail = {
        "id": "nail-project",
        "title": "가을 네일 전후",
        "concept": "손톱 전후 차이",
        "hook": "손이 길어 보이는 컬러는 따로 있어요",
        "shot_list": ["시술 전후 손 비교", "컬러 디테일 확대", "브러시를 바르는 손", "완성된 손 정면", "예약 문의"],
    }

    latte_steps = build_project_storyboard(latte, "카페")
    nail_steps = build_project_storyboard(nail, "뷰티")

    assert latte_steps[0]["subtitle"] == latte["hook"]
    assert nail_steps[0]["subtitle"] == nail["hook"]
    assert latte_steps[0]["scene"] != nail_steps[0]["scene"]
    assert latte_steps != nail_steps
    assert "크림 질감" in latte_steps[1]["subtitle"]
    assert "컬러 디테일" in nail_steps[1]["subtitle"]


def test_storyboard_is_stable_for_the_same_project():
    project = {
        "id": "stable-project",
        "title": "소금빵 굽는 날",
        "concept": "오븐에서 막 나온 소금빵",
        "hook": "이 소리 때문에 아침마다 굽습니다",
        "shot_list": ["완성 소금빵", "단면 디테일", "빵을 자르는 손", "매장 전경", "방문 유도"],
    }

    assert build_project_storyboard(project, "카페") == build_project_storyboard(project, "카페")


def test_signal_study_storyboard_rebuilds_from_each_projects_saved_reels():
    sensory = {
        "id": "sensory-study", "title": "소금빵 연구", "concept": "패턴 연구",
        "source": {"type": "signal_study", "query": "소금빵", "signals": [
            {"username": "a", "caption": "바삭한 단면과 크림 질감", "thumbnail_url": "https://img.example/salt-a.jpg", "url": "https://instagram.com/a"},
            {"username": "b", "caption": "촉촉한 단면과 크림을 가까이 공개", "thumbnail_url": "https://img.example/salt-b.jpg", "url": "https://instagram.com/b"},
        ]},
        "shot_list": ["예전에 저장된 공통 장면"],
    }
    atmosphere = {
        "id": "space-study", "title": "브런치 연구", "concept": "패턴 연구",
        "source": {"type": "signal_study", "query": "브런치 카페", "signals": [
            {"username": "c", "caption": "햇살 좋은 창가와 우드톤 인테리어"},
            {"username": "d", "caption": "넓은 공간과 창가 분위기"},
        ]},
        "shot_list": ["예전에 저장된 공통 장면"],
    }

    sensory_steps = build_project_storyboard(sensory, "카페")
    atmosphere_steps = build_project_storyboard(atmosphere, "카페")

    assert sensory_steps[0]["scene"] == "scene-close"
    assert atmosphere_steps[0]["scene"] == "scene-space"
    assert sensory_steps[0]["subtitle"] != atmosphere_steps[0]["subtitle"]
    assert "2개 릴스" in sensory_steps[0]["analysis_note"]
    assert all("reference_image_url" not in step for step in sensory_steps)
    assert len(sensory_steps) == 5
    assert sensory_steps[0]["scene_label"] == "물품 촬영 범위"
    assert sensory_steps[0]["focus_label"] == "훅 중심"


def test_storyboard_uses_cross_reel_geometry_for_object_and_subtitle_regions():
    project = {
        "id": "geometry-study", "title": "공통 구도", "concept": "공통 구도",
        "source": {
            "type": "signal_study", "query": "크림라떼",
            "signals": [
                {"username": "a", "caption": "크림 질감과 단면"},
                {"username": "b", "caption": "크림 질감과 단면"},
            ],
            "visual_synthesis": {
                "analyzed_count": 2, "subject_bbox_count": 2, "subtitle_bbox_count": 2,
                "subject_bbox": {"x": 15, "y": 35, "width": 60, "height": 30},
                "subtitle_bbox": {"x": 8, "y": 10, "width": 84, "height": 12},
            },
        },
    }

    steps = build_project_storyboard(project, "카페")

    assert len(steps) == 5
    assert len({step["scene_style"] for step in steps}) == 5
    assert len({step["subtitle_style"] for step in steps}) == 5
    assert "left:15.0%;top:35.0%" in steps[0]["scene_style"]
    assert "물품 2개" in steps[0]["geometry_note"]


def test_storyboard_turns_zoom_evidence_into_looping_geometry_styles():
    project = {
        "id": "zoom-study",
        "title": "확대 근거",
        "source": {"type": "signal_study", "visual_synthesis": {
            "analyzed_count": 2,
            "sequence_geometry": [
                {"subject_bbox": {"x": 30, "y": 35, "width": 40, "height": 25}, "subject_bbox_count": 2},
                {"subject_bbox": {"x": 15, "y": 25, "width": 70, "height": 45}, "subject_bbox_count": 2},
            ],
            "sequence_motion": [{
                "motion_type": "zoom_in", "motion_basis": "common", "evidence_count": 2,
                "start_bbox": {"x": 30, "y": 35, "width": 40, "height": 25},
                "end_bbox": {"x": 15, "y": 25, "width": 70, "height": 45},
            }],
        }},
    }

    first = build_project_storyboard(project, "카페")[0]

    assert first["motion_type"] == "zoom_in"
    assert first["motion_start_bbox"]["width"] == 40
    assert first["motion_end_bbox"]["width"] == 70
    assert "2개 릴스에서 반복된 확대" in first["motion_note"]


def test_mobile_coach_url_contains_project_specific_shots():
    project = {
        "id": "latte-1",
        "title": "크림라떼 촬영",
        "concept": "크림이 무너지는 순간",
        "hook": "무너지기 전 3초를 보세요",
        "shot_list": ["완성 라떼 탑뷰", "크림 질감 클로즈업", "저장하고 방문하기"],
    }
    steps = build_project_storyboard(project, "카페")
    url = build_mobile_coach_url("https://coach.example/mobile-coach.html", project, steps, "https://app.example/?view=analysis")
    params = parse_qs(urlparse(url).query)
    token = params["shots"][0]
    token += "=" * ((4 - len(token) % 4) % 4)
    shots = json.loads(base64.urlsafe_b64decode(token).decode("utf-8"))

    assert params["project"] == ["latte-1"]
    assert "project=latte-1" in params["return"][0]
    assert shots[0]["x"] == project["hook"]
    assert shots[0]["m"] == "topview"
    assert shots[1]["m"] == "closeup"
    assert shots[0]["l"] != shots[1]["l"]
