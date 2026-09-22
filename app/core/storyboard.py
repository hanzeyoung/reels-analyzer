"""Deterministic, project-specific storyboard planning."""

from __future__ import annotations

import hashlib
import base64
import json
import re
from urllib.parse import quote, urlencode

from app.core.signal_studies import build_signal_synthesis


SCENE_LAYOUTS = {
    "hero": [
        "width:58%;height:34%;left:21%;top:34%;border-radius:50%;",
        "width:64%;height:30%;left:10%;top:42%;border-radius:50%;",
        "width:55%;height:36%;left:34%;top:29%;border-radius:50%;",
    ],
    "close": [
        "width:82%;height:46%;left:9%;top:31%;border-radius:1rem;",
        "width:68%;height:52%;left:24%;top:25%;border-radius:1rem;",
        "width:74%;height:42%;left:7%;top:38%;border-radius:1rem;",
    ],
    "space": [
        "width:78%;height:44%;left:11%;top:28%;border-radius:.75rem;",
        "width:88%;height:34%;left:6%;top:44%;border-radius:.75rem;",
        "width:64%;height:52%;left:18%;top:24%;border-radius:.75rem;",
    ],
    "hand": [
        "width:45%;height:12%;left:38%;top:61%;border-radius:999px;transform:rotate(-18deg);",
        "width:48%;height:12%;left:13%;top:49%;border-radius:999px;transform:rotate(20deg);",
        "width:52%;height:12%;left:28%;top:35%;border-radius:999px;transform:rotate(-8deg);",
    ],
    "person": [
        "width:42%;height:58%;left:29%;top:25%;border-radius:45% 45% 1rem 1rem;",
        "width:38%;height:54%;left:12%;top:30%;border-radius:45% 45% 1rem 1rem;",
        "width:38%;height:54%;left:50%;top:27%;border-radius:45% 45% 1rem 1rem;",
    ],
    "cta": [
        "width:72%;height:28%;left:14%;top:36%;border-radius:.8rem;",
        "width:64%;height:24%;left:28%;top:29%;border-radius:.8rem;",
        "width:70%;height:25%;left:8%;top:49%;border-radius:.8rem;",
    ],
}

SCENE_LABELS = {
    "hero": "핵심 피사체",
    "close": "디테일 영역",
    "space": "공간 / 배경",
    "hand": "손 이동 방향",
    "person": "인물 위치",
    "cta": "마지막 대표 장면",
}


def _stable_index(seed: str, count: int) -> int:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return int.from_bytes(digest[:2], "big") % count


def _compact(value: str, limit: int = 34) -> str:
    text = re.sub(r"^\s*\d+(?:\.\d+)?\s*[-~–]\s*\d+(?:\.\d+)?초\s*[|·:]?\s*", "", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip(" -|·")
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _subject(project: dict, btype: str) -> str:
    title = _compact(project.get("title", ""), 28)
    concept = _compact(project.get("concept", ""), 28)
    generic_titles = {"Untitled reel", "새 프로젝트", "프로젝트"}
    return concept or (title if title not in generic_titles else "") or f"{btype} 대표 장면"


def _scene_for(text: str, index: int, total: int) -> str:
    value = str(text or "").lower()
    keyword_groups = [
        ("cta", ("cta", "저장", "방문", "예약", "문의", "마지막", "로고", "매장명")),
        ("hand", ("손", "따르", "붓", "집", "자르", "만들", "조리", "바르", "사용")),
        ("person", ("사람", "직원", "손님", "얼굴", "전후", "착용", "자세", "시술")),
        ("space", ("공간", "입구", "외관", "좌석", "매장", "전경", "분위기")),
        ("close", ("클로즈", "디테일", "질감", "단면", "재료", "확대", "가까이")),
        ("hero", ("탑뷰", "완성", "대표", "메뉴", "제품", "결과")),
    ]
    for scene, words in keyword_groups:
        if any(word in value for word in words):
            return scene
    if index == 0:
        return "hero"
    if index == total - 1:
        return "cta"
    return ("close", "hand", "space")[(index - 1) % 3]


def _caption_position(scene: str, seed: str) -> str:
    choices = {
        "hero": ("subtitle-top", "subtitle-bottom"),
        "close": ("subtitle-top", "subtitle-bottom"),
        "space": ("subtitle-top", "subtitle-bottom"),
        "hand": ("subtitle-top", "subtitle-mid"),
        "person": ("subtitle-top", "subtitle-bottom"),
        "cta": ("subtitle-top", "subtitle-mid", "subtitle-bottom"),
    }[scene]
    return choices[_stable_index(seed, len(choices))]


def _box_style(box: dict) -> str:
    return (
        f"left:{float(box['x']):.1f}%;top:{float(box['y']):.1f}%;"
        f"width:{float(box['width']):.1f}%;height:{float(box['height']):.1f}%;border-radius:.55rem;"
    )


def _focus_style(box: dict) -> str:
    focus = _focus_box(box)
    return (
        f"left:{focus['x']:.1f}%;top:{focus['y']:.1f}%;"
        f"width:{focus['width']:.1f}%;height:{focus['height']:.1f}%;"
    )


def _focus_box(box: dict) -> dict:
    center_x = float(box["x"]) + float(box["width"]) / 2
    center_y = float(box["y"]) + float(box["height"]) / 2
    size = max(12.0, min(24.0, float(box["width"]) * 0.34))
    return {"x": max(0, center_x - size / 2), "y": max(0, center_y - size / 2), "width": size, "height": size}


def _motion_style(start: dict, end: dict) -> str:
    return (
        _box_style(start)
        + f"--motion-start-x:{float(start['x']):.1f}%;--motion-start-y:{float(start['y']):.1f}%;"
        + f"--motion-start-w:{float(start['width']):.1f}%;--motion-start-h:{float(start['height']):.1f}%;"
        + f"--motion-end-x:{float(end['x']):.1f}%;--motion-end-y:{float(end['y']):.1f}%;"
        + f"--motion-end-w:{float(end['width']):.1f}%;--motion-end-h:{float(end['height']):.1f}%;"
    )


def _inferred_sequence_motion(sequence_geometry: list[dict]) -> list[dict]:
    """Animate older saved projects from their aggregated observed boxes."""
    motions = []
    for index in range(5):
        current = sequence_geometry[index] if index < len(sequence_geometry) else {}
        following = sequence_geometry[index + 1] if index + 1 < len(sequence_geometry) else current
        start, end = current.get("subject_bbox"), following.get("subject_bbox")
        if not isinstance(start, dict) or not isinstance(end, dict):
            motions.append({})
            continue
        start_area = max(float(start.get("width", 0)) * float(start.get("height", 0)), 1.0)
        end_area = max(float(end.get("width", 0)) * float(end.get("height", 0)), 1.0)
        scale = (end_area / start_area) ** 0.5
        start_center = (float(start.get("x", 0)) + float(start.get("width", 0)) / 2, float(start.get("y", 0)) + float(start.get("height", 0)) / 2)
        end_center = (float(end.get("x", 0)) + float(end.get("width", 0)) / 2, float(end.get("y", 0)) + float(end.get("height", 0)) / 2)
        shift = ((end_center[0] - start_center[0]) ** 2 + (end_center[1] - start_center[1]) ** 2) ** 0.5
        kind = "zoom_in" if scale >= 1.12 else "zoom_out" if scale <= 0.89 else "pan" if shift >= 8 else "hold"
        motions.append({
            "motion_type": kind,
            "motion_basis": "common_geometry",
            "evidence_count": min(int(current.get("subject_bbox_count") or 0), int(following.get("subject_bbox_count") or 0)),
            "start_bbox": start,
            "end_bbox": end,
            "scale_ratio": round(scale, 2),
        })
    return motions


def _subtitle_box(position: str) -> dict:
    return {
        "subtitle-top": {"x": 8, "y": 10, "width": 84, "height": 12},
        "subtitle-mid": {"x": 8, "y": 44, "width": 84, "height": 12},
        "subtitle-bottom": {"x": 8, "y": 78, "width": 84, "height": 12},
    }[position]


def _clamp_box(x: float, y: float, width: float, height: float) -> dict:
    width = max(18.0, min(width, 92.0))
    height = max(12.0, min(height, 86.0))
    return {
        "x": round(max(4.0, min(x, 96.0 - width)), 1),
        "y": round(max(4.0, min(y, 96.0 - height)), 1),
        "width": round(width, 1),
        "height": round(height, 1),
    }


def _sequence_box(base: dict, scene: str, index: int, seed: str) -> dict:
    """Turn one common visual anchor into a five-cut camera progression."""
    bx, by = float(base["x"]), float(base["y"])
    bw, bh = float(base["width"]), float(base["height"])
    base_cx, base_cy = bx + bw / 2, by + bh / 2
    direction = -1 if _stable_index(seed, 2) == 0 else 1
    if index == 0:  # Hook: preserve the observed common placement most strongly.
        width, height = min(max(bw, 46), 78), min(max(bh, 28), 58)
        return _clamp_box(base_cx - width / 2, base_cy - height / 2, width, height)
    if index == 1:  # Proof/detail: move closer and off-center for a visible cut.
        width, height = (84, 48) if scene != "person" else (48, 62)
        cx, cy = 50 + direction * 8, max(34, min(60, base_cy - 9))
        return _clamp_box(cx - width / 2, cy - height / 2, width, height)
    if index == 2:  # Action: leave a directional lane for the hand/movement.
        width, height = (58, 22) if scene == "hand" else (62, 38)
        cx, cy = 50 - direction * 12, max(38, min(68, base_cy + 5))
        return _clamp_box(cx - width / 2, cy - height / 2, width, height)
    if index == 3:  # Context: pull back to reveal the surrounding space.
        width, height = (88, 52) if scene == "space" else (76, 46)
        return _clamp_box(50 - width / 2, 48 - height / 2, width, height)
    # CTA: return to a stable hero composition, distinct from the opening crop.
    width, height = 64, 30
    cx, cy = max(38, min(62, base_cx - direction * 6)), 57
    return _clamp_box(cx - width / 2, cy - height / 2, width, height)


def _sequence_subtitle_box(common: dict | None, object_box: dict, index: int) -> tuple[dict, str]:
    object_center_y = float(object_box["y"]) + float(object_box["height"]) / 2
    hook_at_top = object_center_y >= 50
    top_first = [
        {"x": 8, "y": 8, "width": 84, "height": 12},
        {"x": 10, "y": 80, "width": 80, "height": 11},
        {"x": 5, "y": 25, "width": 66, "height": 11},
        {"x": 25, "y": 67, "width": 70, "height": 11},
        {"x": 12, "y": 44, "width": 76, "height": 13},
    ]
    bottom_first = [
        {"x": 8, "y": 80, "width": 84, "height": 12},
        {"x": 10, "y": 8, "width": 80, "height": 11},
        {"x": 29, "y": 65, "width": 66, "height": 11},
        {"x": 5, "y": 18, "width": 70, "height": 11},
        {"x": 12, "y": 44, "width": 76, "height": 13},
    ]
    box = (top_first if hook_at_top else bottom_first)[index]
    position = "subtitle-top" if box["y"] < 34 else "subtitle-mid" if box["y"] < 68 else "subtitle-bottom"
    return box, position


def build_project_storyboard(
    project: dict,
    btype: str,
    primary_camera: str = "클로즈업",
    analysis: dict | None = None,
) -> list[dict]:
    """Build stable storyboard cards from one project's own creative fields."""
    subject = _subject(project, btype)
    source = project.get("source") or {}
    synthesis = source.get("synthesis") or {}
    if source.get("type") == "signal_study" and source.get("signals"):
        # Rebuild from the saved source reels so older projects immediately use
        # cross-reel evidence instead of their previously saved generic list.
        synthesis = build_signal_synthesis(source["signals"], query=str(source.get("query") or ""))
    evidence_plan = synthesis.get("storyboard_plan") or []
    hook = _compact(synthesis.get("recommended_hook") or project.get("hook", ""), 54) or f"{subject}, 첫 장면에서 확인하세요"
    raw_shots = [_compact(item.get("shot", ""), 54) for item in evidence_plan if isinstance(item, dict) and _compact(item.get("shot", ""), 54)]
    if not raw_shots:
        raw_shots = [_compact(item, 54) for item in (project.get("shot_list") or []) if _compact(item, 54)]
    if not raw_shots:
        raw_shots = [
            f"{subject} 완성 장면",
            f"{subject} 디테일 클로즈업",
            f"{subject}을 준비하거나 사용하는 손동작",
            f"{btype} 공간과 분위기",
            f"{subject} 저장·방문 유도",
        ]
    raw_shots = raw_shots[:5]
    standard_shots = [
        f"{subject} 완성 장면", f"{subject} 핵심 디테일", f"{subject}을 다루는 손동작",
        f"{btype} 공간과 사용 맥락", f"{subject} 저장·방문 유도",
    ]
    while len(raw_shots) < 5:
        raw_shots.append(standard_shots[len(raw_shots)])

    project_seed = str(project.get("id") or project.get("title") or subject)
    analysis = analysis or {}
    visual = source.get("visual_synthesis") or {}
    sequence_geometry = visual.get("sequence_geometry") or []
    sequence_motion = visual.get("sequence_motion") or _inferred_sequence_motion(sequence_geometry)
    actions = analysis.get("priority_actions") or []
    risks = [item for item in analysis.get("timeline_diagnostics", []) if item.get("kind") == "risk"]
    steps = []
    transition_directions = (
        "공통 훅 구도를 0.8~1.0초 유지한 뒤 바로 확대 컷으로 전환합니다.",
        "앞 컷 기준점에서 15~25% 밀어 들어가는 푸시인으로 디테일을 연결합니다.",
        "손이나 물품의 이동 방향을 따라 짧게 패닝해 화면의 흐름을 만듭니다.",
        "한 걸음 물러나는 풀아웃 또는 와이드 컷으로 장소와 맥락을 공개합니다.",
        "첫 장면과 다른 안정 구도에서 1.5초 멈춰 CTA를 읽게 합니다.",
    )
    for index, shot in enumerate(raw_shots):
        planned = evidence_plan[index] if index < len(evidence_plan) else {}
        planned_scene = str(planned.get("scene") or "")
        scene = planned_scene if planned_scene in SCENE_LAYOUTS else _scene_for(shot, index, len(raw_shots))
        seed = f"{project_seed}:{index}:{shot}"
        layout = SCENE_LAYOUTS[scene][_stable_index(seed, len(SCENE_LAYOUTS[scene]))]
        planned_position = {"상단": "subtitle-top", "중앙": "subtitle-mid", "하단": "subtitle-bottom"}.get(str(planned.get("subtitle_position") or ""))
        position = planned_position or _caption_position(scene, seed)
        layout_values = _layout_values(layout)
        fallback_box = {"x": layout_values[0], "y": layout_values[1], "width": layout_values[2], "height": layout_values[3]}
        segment_geometry = sequence_geometry[index] if index < len(sequence_geometry) and isinstance(sequence_geometry[index], dict) else {}
        uses_sequence_geometry = isinstance(segment_geometry.get("subject_bbox"), dict)
        uses_common_geometry = int(visual.get("analyzed_count") or 0) >= 2 and isinstance(visual.get("subject_bbox"), dict)
        base_box = visual["subject_bbox"] if uses_common_geometry else fallback_box
        object_box = segment_geometry["subject_bbox"] if uses_sequence_geometry else _sequence_box(base_box, scene, index, seed)
        motion = sequence_motion[index] if index < len(sequence_motion) and isinstance(sequence_motion[index], dict) else {}
        motion_start = motion.get("start_bbox") if isinstance(motion.get("start_bbox"), dict) else object_box
        motion_end = motion.get("end_bbox") if isinstance(motion.get("end_bbox"), dict) else object_box
        motion_type = str(motion.get("motion_type") or "hold")
        uses_sequence_subtitle = isinstance(segment_geometry.get("subtitle_bbox"), dict)
        uses_common_subtitle = int(visual.get("analyzed_count") or 0) >= 2 and isinstance(visual.get("subtitle_bbox"), dict)
        if uses_sequence_subtitle:
            subtitle_box = segment_geometry["subtitle_bbox"]
            subtitle_y = float(subtitle_box.get("y", 50))
            position = "subtitle-top" if subtitle_y < 34 else "subtitle-mid" if subtitle_y < 68 else "subtitle-bottom"
        else:
            subtitle_box, position = _sequence_subtitle_box(visual.get("subtitle_bbox") if uses_common_subtitle else None, object_box, index)
        if planned:
            subtitle = _compact(planned.get("subtitle", ""), 54) or (hook if index == 0 else shot)
            role = str(planned.get("purpose") or "공통 패턴을 촬영 장면으로 증명")
        elif index == 0:
            subtitle = hook
            role = "스크롤을 멈추는 프로젝트 훅"
        elif index == len(raw_shots) - 1:
            subtitle = f"{subject}이 궁금하면 저장해두세요"
            role = "저장 또는 방문 행동 유도"
        else:
            subtitle = shot
            role = "장면의 핵심 정보를 한 문장으로 전달"

        camera = str(planned.get("camera") or "") or (primary_camera if index == 0 else {
            "hero": "탑뷰 또는 정면샷",
            "close": "클로즈업",
            "space": "와이드 정면샷",
            "hand": "손을 따라가는 팔로잉샷",
            "person": "눈높이 정면샷",
            "cta": "고정 정면샷",
        }[scene])
        if segment_geometry.get("camera"):
            camera = str(segment_geometry["camera"])
        if index == 0 and int(visual.get("analyzed_count") or 0) >= 2 and visual.get("top_camera"):
            camera = str(visual["top_camera"])
        position_name = {"subtitle-top": "상단", "subtitle-mid": "중앙", "subtitle-bottom": "하단"}[position]
        step = {
            "title": f"{index + 1}. {shot}",
            "hook": role,
            "scene": f"scene-{scene}",
            "scene_style": _box_style(motion_start) if motion_type != "hold" else _box_style(object_box),
            "scene_label": "물품 촬영 범위",
            "focus_style": _focus_style(motion_start) if motion_type != "hold" else _focus_style(object_box),
            "focus_label": "훅 중심" if index == 0 else "물품 중심",
            "motion_type": motion_type,
            "motion_start_bbox": motion_start,
            "motion_end_bbox": motion_end,
            "focus_motion_start_bbox": _focus_box(motion_start),
            "focus_motion_end_bbox": _focus_box(motion_end),
            "subtitle": subtitle,
            "subtitle_class": f"{position} " + ("subtitle-accent" if index == 0 else "subtitle-light" if scene == "space" else ""),
            "subtitle_style": _box_style(subtitle_box).replace("border-radius:.55rem;", "height:auto;border-radius:.45rem;"),
            "shoot": f"{camera}으로 ‘{shot}’이 명확히 보이게 프레임의 표시 영역에 배치합니다.",
            "text": f"자막은 {position_name} 안전 영역에 배치합니다. 실제 문구: ‘{subtitle}’",
            "edit": f"{planned.get('time', '') + ' 구간에 ' if planned.get('time') else ''}핵심 동작이 보이는 부분만 사용합니다."
                    + f" {transition_directions[index]}"
                    + (f" 공통 시각 근거의 컷 속도({visual['top_cut_speed']})를 적용합니다." if int(visual.get("analyzed_count") or 0) >= 2 and visual.get("top_cut_speed") else ""),
        }
        geometry_parts = []
        if uses_sequence_geometry:
            geometry_parts.append(
                f"원본 영상 {segment_geometry.get('normalized_start', 0)}~{segment_geometry.get('normalized_end', 100)}% 구간 · "
                f"물품 좌표 {segment_geometry.get('subject_bbox_count', 0)}개 합성"
            )
        elif uses_common_geometry:
            subject_basis = "반복 위치 묶음" if visual.get("subject_bbox_basis") == "repeated_cluster" else "관측 좌표 중앙값 추천"
            geometry_parts.append(f"물품 {visual.get('subject_bbox_count', 0)}개 · {subject_basis}을 시작점으로 컷별 줌·이동")
        if uses_sequence_subtitle:
            geometry_parts.append(f"같은 구간 자막 좌표 {segment_geometry.get('subtitle_bbox_count', 0)}개 합성")
        elif uses_common_subtitle:
            subtitle_basis = "반복 위치 묶음" if visual.get("subtitle_bbox_basis") == "repeated_cluster" else "관측 좌표 중앙값 추천"
            geometry_parts.append(f"자막 {visual.get('subtitle_bbox_count', 0)}개 · {subtitle_basis}에서 컷별 안전 영역으로 이동")
        step["geometry_note"] = " / ".join(geometry_parts) or "공통 좌표 분석 전에는 장면 목적에 맞춘 촬영 안전 영역을 표시"
        motion_names = {"zoom_in": "확대(푸시인)", "zoom_out": "축소(풀아웃)", "pan": "좌우·상하 이동", "hold": "고정 구도"}
        motion_basis = str(motion.get("motion_basis") or "")
        motion_count = int(motion.get("evidence_count") or 0)
        source_label = str(motion.get("source_label") or "")
        if motion_basis == "common":
            step["motion_note"] = f"{motion_count}개 릴스에서 반복된 {motion_names[motion_type]} 흐름"
        elif motion_basis == "top_reel":
            source_text = f"(@{source_label})" if source_label else ""
            step["motion_note"] = f"상위 릴스{source_text}의 {motion_names[motion_type]} 흐름"
        elif motion_basis == "common_geometry" and motion_type != "hold":
            step["motion_note"] = f"구간별 공통 좌표 변화로 확인한 {motion_names[motion_type]} 흐름"
        else:
            step["motion_note"] = "이 구간은 물품 크기를 유지하는 안정 구도"
        if planned.get("evidence_pattern"):
            count = planned.get("evidence_count")
            step["analysis_note"] = f"공통 근거: {planned['evidence_pattern']}" + (f" · {count}개 릴스에서 확인" if count else "")
        if index < len(actions):
            step["edit"] += f" 이전 영상 분석 반영: {actions[index]}"
        if index == 0 and risks and not step.get("analysis_note"):
            step["analysis_note"] = f"이전 영상 {float(risks[0].get('timestamp_seconds', 0)):.1f}초 위험 구간을 보완하는 구성입니다."
        steps.append(step)
    return steps


def _layout_values(style: str) -> list[int]:
    values = []
    for name in ("left", "top", "width", "height"):
        match = re.search(rf"(?:^|;){name}:(\d+(?:\.\d+)?)%", style or "")
        values.append(round(float(match.group(1))) if match else 0)
    return values


def build_mobile_coach_url(
    base_url: str,
    project: dict,
    steps: list[dict],
    return_url: str = "",
) -> str:
    """Serialize a compact project storyboard into a shareable coach URL."""
    mode_map = {
        "scene-hero": "topview",
        "scene-close": "closeup",
        "scene-space": "front",
        "scene-hand": "following",
        "scene-person": "front",
        "scene-cta": "front",
    }
    compact_shots = []
    for step in steps[:7]:
        subtitle_class = str(step.get("subtitle_class") or "")
        position = "mid" if "subtitle-mid" in subtitle_class else "bottom" if "subtitle-bottom" in subtitle_class else "top"
        scene = str(step.get("scene") or "scene-hero")
        compact_shots.append({
            "t": _compact(step.get("title", "촬영 장면"), 30),
            "g": _compact(step.get("shoot", "표시 영역에 피사체를 맞춰주세요."), 72),
            "x": _compact(step.get("subtitle", ""), 42),
            "m": mode_map.get(scene, "front"),
            "l": _layout_values(str(step.get("scene_style") or "")),
            "p": position,
            "a": _compact(step.get("scene_label", "피사체"), 18),
            "s": "circle" if scene == "scene-hero" else "pill" if scene == "scene-hand" else "person" if scene == "scene-person" else "box",
        })
    token = base64.urlsafe_b64encode(
        json.dumps(compact_shots, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    params = {
        "project": str(project.get("id") or project.get("title") or "project")[:80],
        "name": _compact(project.get("title", "촬영 프로젝트"), 40),
        "shots": token,
    }
    if return_url:
        separator = "&" if "?" in return_url else "?"
        params["return"] = f"{return_url}{separator}project={quote(params['project'], safe='')}"
    return f"{base_url}?{urlencode(params)}"
