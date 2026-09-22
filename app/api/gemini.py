"""Gemini multimodal reel analysis for visual and text evidence."""

import io
import os
import json
import re
import base64
import tempfile
from pathlib import Path

try:
    import google.generativeai as genai
except ImportError:  # Keep non-AI workspace and test utilities available.
    genai = None
try:
    import httpx
except ImportError:  # requests supports the two simple GET calls used below.
    import requests as httpx
try:
    import cv2
except ImportError:
    cv2 = None
from dotenv import load_dotenv
from PIL import Image

try:
    from app.core.frame_extractor import extract_unique_frames
except ImportError:  # imagehash/OpenCV are only needed for a real video job.
    extract_unique_frames = None
from app.core.config import get_env, get_gemini_api_key, get_gemini_model
from app.core.observability import enforce_daily_limit, observed_operation, record_api_usage
from app.core.timeline_analyzer import analyze_video_timeline

load_dotenv()

GEMINI_API_KEY = get_gemini_api_key()
if GEMINI_API_KEY:
    os.environ.setdefault("GOOGLE_API_KEY", GEMINI_API_KEY)
if genai is not None:
    genai.configure(api_key=GEMINI_API_KEY)
MODEL_NAME = get_gemini_model()


# ── 프롬프트 ─────────────────────────────────

ANALYSIS_PROMPT = """
당신은 인스타그램 릴스 마케팅 전문 분석가입니다.
아래 릴스 영상 및 정보를 분석하여 소상공인이 참고할 수 있는 인사이트를 추출해주세요.
프레임은 첫 1~4초 후킹 구간을 더 촘촘히 보고, 이후 중반/후반도 함께 참고하는 방식으로 추출됩니다.

[분석 항목]
1. camera_angles: 영상에서 발견된 촬영 구도 목록 (탑뷰, 클로즈업, 팔로잉샷, 정면샷 등)
2. cut_speed: 컷 편집 속도 (느림 / 보통 / 빠름)
3. hook_text: 첫 1~4초 후킹 구간에 등장하는 문구, 제품, 행동 또는 핵심 장면 설명
4. subtitle_position: 자막 위치 (상단 / 중앙 / 하단 / 없음)
5. color_tone: 전반적인 색감 분위기 (따뜻함 / 차가움 / 생동감 / 차분함 등)
6. bgm_mood: 배경음악 분위기 (신나는 / 감성적 / 조용한 / 없음 등)
7. caption_hooks: 본문 캡션에서 발견된 후킹 패턴 목록
8. analysis_summary: 이 영상이 잘 될 수 있었던 이유 2~3줄 요약 (소상공인 눈높이)
9. category_scores: hook, pacing, audio, visual, engagement를 각각 0~100으로 평가
10. overall_score: 다섯 점수를 종합한 게시 전 예상 점수 (0~100)
11. timeline_diagnostics: 제공된 프레임 시간 정보를 이용해 구간별 강점/문제/수정안을 작성
12. priority_actions: 가장 효과가 클 것으로 예상되는 수정 행동 3개
13. subject_bbox: 광고하려는 핵심 물품/대상의 위치. 세로 화면 전체를 0~100 좌표로 보고
    {"x": 왼쪽, "y": 위쪽, "width": 너비, "height": 높이}로 표시
14. subtitle_bbox: 실제로 보이는 주 자막 영역을 같은 0~100 좌표로 표시. 자막이 없으면 null
15. subject_description: subject_bbox 안에 있는 핵심 물품/대상 이름

중요:
- retention 값과 overall_score는 실제 Instagram 통계가 아닌 AI 예상치입니다.
- timeline_diagnostics의 timestamp_seconds는 제공된 프레임 시각 안에서 선택하세요.
- 근거가 부족하면 confidence를 낮게 표시하고 사실처럼 단정하지 마세요.

반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트 없이 JSON만 출력하세요.

{
  "camera_angles": ["탑뷰", "클로즈업"],
  "cut_speed": "빠름",
  "hook_text": "후킹 문구 또는 장면 설명",
  "subtitle_position": "하단",
  "color_tone": "따뜻함",
  "bgm_mood": "신나는",
  "subject_bbox": {"x": 18, "y": 32, "width": 64, "height": 38},
  "subtitle_bbox": {"x": 8, "y": 10, "width": 84, "height": 12},
  "subject_description": "대표 메뉴가 담긴 접시",
  "caption_hooks": ["후킹패턴1", "후킹패턴2"],
  "analysis_summary": "이 영상은 ...",
  "category_scores": {
    "hook": 74,
    "pacing": 68,
    "audio": 60,
    "visual": 82,
    "engagement": 70
  },
  "overall_score": 71,
  "timeline_diagnostics": [
    {
      "timestamp_seconds": 0.8,
      "kind": "risk",
      "title": "첫 제품 노출이 늦음",
      "reason": "첫 화면에서 핵심 메뉴가 작게 보임",
      "predicted_retention": 84,
      "confidence": "medium",
      "action": "0.5초 안에 메뉴 클로즈업을 배치"
    }
  ],
  "priority_actions": ["첫 0.5초에 대표 장면 배치", "중간 정지 구간 1초 단축", "마지막 CTA를 하나로 정리"]
}
"""

THUMBNAIL_LAYOUT_PROMPT = """
이 이미지는 공개 Instagram 릴스의 세로형 대표 프레임입니다. 촬영 스토리보드의 공통 구도를 계산할 수 있도록 화면 배치만 분석하세요.

- 광고의 핵심 물품/대상을 하나 고르세요. 사람보다 판매·홍보하려는 메뉴, 제품, 시술 결과, 공간이 우선입니다.
- Gemini 이미지 좌표 표준인 0~1000 [y_min, x_min, y_max, x_max] 순서를 사용합니다.
- subject_box_2d는 핵심 물품이 실제로 차지하는 최소 사각형입니다.
- subtitle_box_2d는 화면에 실제로 보이는 주 자막 사각형입니다. 자막이 없으면 null입니다.
- 보이지 않는 위치나 문구를 추측하지 마세요.

JSON만 반환하세요:
{
  "camera_angles": ["클로즈업"],
  "subtitle_position": "상단",
  "hook_text": "화면에서 읽힌 첫 자막 또는 핵심 장면",
  "subject_description": "핵심 물품 이름",
  "subject_box_2d": [320, 180, 700, 820],
  "subtitle_box_2d": [100, 80, 220, 920],
  "cut_speed": "알 수 없음",
  "bgm_mood": "알 수 없음"
}
"""

SEQUENCE_LAYOUT_PROMPT = """
아래 5개 이미지는 한 공개 Instagram 릴스를 영상 길이에 맞춰 정규화한 순서 프레임입니다.
각 이미지는 순서대로 0~13%, 13~33%, 33~60%, 60~87%, 87~100% 구간을 대표합니다.

각 프레임마다 다음을 독립적으로 측정하세요.
- 광고하려는 핵심 물품/대상 하나의 실제 최소 사각형
- 화면에 실제로 보이는 주 자막 사각형. 자막이 없으면 null
- Gemini 이미지 좌표 표준인 0~1000 [y_min, x_min, y_max, x_max] 순서를 사용
- 앞 프레임의 좌표를 복사하지 말고 각 이미지에서 실제 위치를 측정
- 사람보다 판매·홍보하는 메뉴, 제품, 시술 결과 또는 공간을 우선

JSON만 반환하세요:
{
  "composition_sequence": [
    {"segment_index": 0, "subject_description": "핵심 물품", "subject_box_2d": [300, 100, 750, 800], "subtitle_box_2d": [80, 80, 200, 920], "camera": "클로즈업"},
    {"segment_index": 1, "subject_description": "핵심 물품", "subject_box_2d": [250, 200, 750, 850], "subtitle_box_2d": null, "camera": "탑뷰"},
    {"segment_index": 2, "subject_description": "핵심 물품", "subject_box_2d": [450, 350, 750, 800], "subtitle_box_2d": null, "camera": "팔로잉샷"},
    {"segment_index": 3, "subject_description": "핵심 물품", "subject_box_2d": [200, 80, 800, 920], "subtitle_box_2d": [780, 100, 900, 900], "camera": "와이드샷"},
    {"segment_index": 4, "subject_description": "핵심 물품", "subject_box_2d": [380, 200, 730, 800], "subtitle_box_2d": [440, 120, 570, 880], "camera": "정면샷"}
  ]
}
"""


# ── 영상 파일로 분석 ─────────────────────────

def analyze_reel_from_file(
    video_path: str,
    caption: str = "",
) -> dict:
    """
    로컬 영상에서 프레임을 추출한 뒤 Gemini Flash로 분석합니다.

    Args:
        video_path: 로컬 영상 파일 경로 (.mp4 등)
        caption: 릴스 본문 캡션

    Returns:
        분석 결과 dict
    """
    if extract_unique_frames is None:
        raise RuntimeError("영상 분석 의존성이 설치되지 않았습니다. requirements.txt를 설치해주세요.")
    enforce_daily_limit("gemini", max_calls=int(get_env("GEMINI_DAILY_CALL_LIMIT", "100") or 100))
    with tempfile.TemporaryDirectory(prefix="reel_frames_") as frame_dir:
        signal_analysis = analyze_video_timeline(video_path)
        frame_paths = extract_unique_frames(video_path, output_dir=frame_dir)
        result = analyze_reel_from_frames(
            frame_paths,
            caption=caption,
            signal_context=signal_analysis,
        )
        return _merge_signal_analysis(result, signal_analysis)


def analyze_reel_from_frames(
    frame_paths: list[str],
    caption: str = "",
    signal_context: dict | None = None,
) -> dict:
    """
    추출된 프레임 이미지 목록을 Gemini Flash로 분석합니다.

    영상 전체 업로드 대신 JPEG 프레임만 보내므로 트래픽과 토큰 사용량을 줄일 수 있습니다.
    """
    if not frame_paths:
        raise ValueError("분석할 프레임이 없습니다.")
    if not GEMINI_API_KEY or genai is None:
        raise RuntimeError("Gemini 분석에 필요한 GEMINI_API_KEY 또는 GOOGLE_API_KEY 값이 없습니다.")

    model = genai.GenerativeModel(MODEL_NAME)

    print(f"[Gemini] 프레임 {len(frame_paths)}장 분석 중")
    images = [Image.open(path) for path in frame_paths]

    prompt = ANALYSIS_PROMPT
    if caption:
        prompt += f"\n\n[본문 캡션]\n{caption}"
    if signal_context:
        prompt += (
            "\n\n[로컬에서 실제 측정한 영상 신호]"
            "\n이 값은 전체 영상에서 계산한 근거입니다. 의미 해석에 활용하되 숫자를 바꾸지 마세요.\n"
            + json.dumps({
                "duration_seconds": signal_context.get("duration_seconds"),
                "signal_summary": signal_context.get("signal_summary"),
                "measured_diagnostics": signal_context.get("timeline_diagnostics"),
            }, ensure_ascii=False)
        )

    timestamped_images = []
    for path, image in zip(frame_paths, images):
        timestamp = _frame_timestamp(path)
        timestamped_images.extend([f"프레임 시각: {timestamp:.2f}초", image])

    with observed_operation("gemini.video_analysis", source="file", frame_count=len(frame_paths)):
        response = model.generate_content([prompt, *timestamped_images])
    record_api_usage("gemini", metadata={"operation": "video_analysis", "frame_count": len(frame_paths)})
    result = _normalize_analysis(_parse_response(response.text))
    result["frame_count"] = len(frame_paths)
    result["analysis_basis"] = "AI semantic analysis from timestamped sampled frames"

    usage = getattr(response, "usage_metadata", None)
    if usage:
        result["usage_metadata"] = {
            "prompt_token_count": getattr(usage, "prompt_token_count", None),
            "candidates_token_count": getattr(usage, "candidates_token_count", None),
            "total_token_count": getattr(usage, "total_token_count", None),
        }

    return result


def analyze_reel_from_url(media_url: str, caption: str = "") -> dict:
    """media_url에서 영상을 임시 다운로드한 뒤 프레임 기반으로 분석합니다."""
    response = httpx.get(media_url, timeout=60)
    response.raise_for_status()

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(response.content)
        video_path = f.name

    try:
        return analyze_reel_from_file(video_path, caption=caption)
    finally:
        Path(video_path).unlink(missing_ok=True)


# ── 썸네일 이미지로 분석 (영상 없을 때 대안) ──

def analyze_reel_from_thumbnail(
    thumbnail_url: str,
    caption: str = "",
) -> dict:
    """
    썸네일 이미지 URL로 부분 분석합니다.
    (영상 파일이 없을 때 대안 — 비전 항목만 가능)
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("Gemini 분석에 필요한 GEMINI_API_KEY 또는 GOOGLE_API_KEY 값이 없습니다.")

    image_response = httpx.get(thumbnail_url, timeout=30)
    image_response.raise_for_status()
    image = Image.open(io.BytesIO(image_response.content)).convert("RGB")
    jpeg = io.BytesIO()
    image.save(jpeg, format="JPEG", quality=90)

    prompt = THUMBNAIL_LAYOUT_PROMPT
    if caption:
        prompt += f"\n\n[물품 판별에만 참고할 본문 캡션]\n{caption[:1200]}"

    enforce_daily_limit("gemini", max_calls=int(get_env("GEMINI_DAILY_CALL_LIMIT", "100") or 100))
    with observed_operation("gemini.url_analysis", source="url"):
        response = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{get_env('GEMINI_VISION_MODEL', 'gemini-3.5-flash-lite')}:generateContent",
            headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY},
            json={
                "contents": [{"parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(jpeg.getvalue()).decode("ascii")}},
                ]}],
                "generationConfig": {"response_mime_type": "application/json"},
            },
            timeout=90,
        )
        response.raise_for_status()
        payload = response.json()
        parts = (((payload.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
        response_text = "".join(str(part.get("text") or "") for part in parts)
        if not response_text:
            raise RuntimeError("Gemini 썸네일 분석 응답에 JSON 텍스트가 없습니다.")
    record_api_usage("gemini", metadata={"operation": "url_analysis"})
    return _normalize_analysis(_parse_response(response_text))


def analyze_reel_sequence_from_url(video_url: str, caption: str = "") -> dict:
    """Measure five normalized temporal composition points from one reel."""
    if not GEMINI_API_KEY:
        raise RuntimeError("Gemini 분석에 필요한 GEMINI_API_KEY 또는 GOOGLE_API_KEY 값이 없습니다.")
    if cv2 is None:
        raise RuntimeError("시간 구간 프레임 추출에 필요한 OpenCV가 설치되지 않았습니다.")

    video_response = httpx.get(video_url, timeout=60)
    video_response.raise_for_status()
    ratios = (0.065, 0.23, 0.465, 0.735, 0.935)
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temporary:
        temporary.write(video_response.content)
        video_path = temporary.name
    capture = cv2.VideoCapture(video_path)
    try:
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0)
        if frame_count <= 0 or fps <= 0:
            raise RuntimeError("원본 릴스의 길이 정보를 읽지 못했습니다.")
        duration = frame_count / fps
        parts = [{"text": SEQUENCE_LAYOUT_PROMPT + (f"\n\n[물품 판별 참고 캡션]\n{caption[:1200]}" if caption else "")}]
        sample_times = []
        for index, ratio in enumerate(ratios):
            frame_number = min(frame_count - 1, max(0, round((frame_count - 1) * ratio)))
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            ok, frame = capture.read()
            if not ok:
                raise RuntimeError(f"정규화 구간 {index + 1}의 프레임을 읽지 못했습니다.")
            ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
            if not ok:
                raise RuntimeError(f"정규화 구간 {index + 1}의 프레임 변환에 실패했습니다.")
            timestamp = frame_number / fps
            sample_times.append(round(timestamp, 2))
            parts.extend([
                {"text": f"segment_index={index}, normalized_position={ratio:.3f}, timestamp_seconds={timestamp:.2f}"},
                {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(encoded.tobytes()).decode("ascii")}},
            ])
    finally:
        capture.release()
        Path(video_path).unlink(missing_ok=True)

    enforce_daily_limit("gemini", max_calls=int(get_env("GEMINI_DAILY_CALL_LIMIT", "100") or 100))
    with observed_operation("gemini.sequence_layout", source="video_url", frame_count=5):
        response = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{get_env('GEMINI_VISION_MODEL', 'gemini-3.5-flash-lite')}:generateContent",
            headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY},
            json={
                "contents": [{"parts": parts}],
                "generationConfig": {"response_mime_type": "application/json"},
            },
            timeout=120,
        )
        response.raise_for_status()
        payload = response.json()
        response_parts = (((payload.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
        response_text = "".join(str(part.get("text") or "") for part in response_parts)
        if not response_text:
            raise RuntimeError("Gemini 시간 구간 분석 응답에 JSON 텍스트가 없습니다.")
    record_api_usage("gemini", metadata={"operation": "sequence_layout", "frame_count": 5})
    parsed = _parse_response(response_text)
    raw_sequence = parsed.get("composition_sequence") if isinstance(parsed, dict) else []
    by_index = {
        int(row.get("segment_index", index)): row
        for index, row in enumerate(raw_sequence or []) if isinstance(row, dict)
    }
    sequence = []
    ranges = ((0, 13), (13, 33), (33, 60), (60, 87), (87, 100))
    for index, normalized_range in enumerate(ranges):
        row = by_index.get(index, {})
        sequence.append({
            "segment_index": index,
            "normalized_start": normalized_range[0],
            "normalized_end": normalized_range[1],
            "timestamp_seconds": sample_times[index],
            "subject_description": str(row.get("subject_description") or "핵심 물품"),
            "subject_bbox": _normalize_box_2d(row.get("subject_box_2d")) or _normalize_bbox(row.get("subject_bbox")),
            "subtitle_bbox": _normalize_box_2d(row.get("subtitle_box_2d")) or _normalize_bbox(row.get("subtitle_bbox")),
            "camera": str(row.get("camera") or ""),
        })
    return {"duration_seconds": round(duration, 2), "composition_sequence": sequence}


# ── 텍스트(캡션)만 분석 ──────────────────────

def analyze_caption_only(caption: str) -> dict:
    """
    영상 없이 캡션 텍스트만으로 후킹 패턴을 분석합니다.
    """
    if not GEMINI_API_KEY or genai is None:
        raise RuntimeError("Gemini 분석에 필요한 GEMINI_API_KEY 또는 GOOGLE_API_KEY 값이 없습니다.")

    model = genai.GenerativeModel(MODEL_NAME)

    prompt = f"""
인스타그램 릴스 캡션을 분석하여 마케팅 후킹 패턴을 추출해주세요.

[캡션]
{caption}

아래 JSON 형식으로만 응답하세요:
{{
  "caption_hooks": ["패턴1", "패턴2"],
  "analysis_summary": "이 캡션의 특징 요약"
}}
"""
    response = model.generate_content(prompt)
    return _parse_response(response.text)


def generate_revised_production_plan(analysis: dict, store_profile: dict) -> dict:
    """Turn diagnosed weaknesses into a shootable script and shot list."""
    if not GEMINI_API_KEY or genai is None:
        raise RuntimeError("대본 생성에 필요한 GEMINI_API_KEY 또는 GOOGLE_API_KEY 값이 없습니다.")
    model = genai.GenerativeModel(MODEL_NAME)
    prompt = f"""
당신은 소상공인 릴스 촬영 감독입니다. 이전 영상 진단과 가게 정보를 이용해 바로 촬영 가능한 개선 대본을 만드세요.

[가게 정보]
{json.dumps(store_profile, ensure_ascii=False)}

[이전 영상 진단]
{json.dumps({
    "summary": analysis.get("analysis_summary"),
    "hook": analysis.get("hook_text"),
    "priority_actions": analysis.get("priority_actions"),
    "timeline_diagnostics": analysis.get("timeline_diagnostics"),
    "creator_scores": analysis.get("category_scores"),
}, ensure_ascii=False)}

요구사항:
- 총 길이는 15~30초, 장면은 4~6개로 구성합니다.
- 각 장면은 start_seconds, end_seconds, shot, camera, direction, on_screen_text, voiceover, edit, fixes_issue를 포함합니다.
- 이전 영상의 문제를 어떤 장면에서 고치는지 fixes_issue에 명시합니다.
- 휴대폰 하나로 매장에서 촬영 가능한 지시만 사용합니다.
- 마지막 장면의 CTA는 가게 정보의 goal 하나만 사용합니다.
- JSON만 출력하세요.

{{
  "title": "릴스 제목",
  "target_duration_seconds": 20,
  "hook": "첫 문장",
  "caption_first_line": "캡션 첫 줄",
  "shots": [
    {{
      "start_seconds": 0,
      "end_seconds": 2,
      "shot": "대표 메뉴 결과 선공개",
      "camera": "클로즈업",
      "direction": "메뉴에서 20cm 거리",
      "on_screen_text": "화면 문구",
      "voiceover": "내레이션",
      "edit": "0.8초 컷 전환",
      "fixes_issue": "초반 메뉴 노출 지연 보완"
    }}
  ]
}}
"""
    response = model.generate_content(prompt)
    result = _parse_response(response.text)
    shots = []
    for index, shot in enumerate(result.get("shots") or [], start=1):
        if not isinstance(shot, dict):
            continue
        start = max(0.0, float(shot.get("start_seconds") or 0))
        end = max(start + 0.5, float(shot.get("end_seconds") or start + 2))
        shots.append({
            "index": index,
            "start_seconds": round(start, 1),
            "end_seconds": round(end, 1),
            "shot": str(shot.get("shot") or f"장면 {index}"),
            "camera": str(shot.get("camera") or "정면샷"),
            "direction": str(shot.get("direction") or "대상을 화면 중앙에 둡니다."),
            "on_screen_text": str(shot.get("on_screen_text") or ""),
            "voiceover": str(shot.get("voiceover") or ""),
            "edit": str(shot.get("edit") or ""),
            "fixes_issue": str(shot.get("fixes_issue") or ""),
        })
    if not shots:
        raise RuntimeError("촬영 가능한 장면 목록을 생성하지 못했습니다.")
    return {
        "title": str(result.get("title") or "개선 릴스"),
        "target_duration_seconds": float(result.get("target_duration_seconds") or shots[-1]["end_seconds"]),
        "hook": str(result.get("hook") or shots[0]["on_screen_text"]),
        "caption_first_line": str(result.get("caption_first_line") or ""),
        "shots": shots,
        "source": "latest_analysis_and_store_profile",
    }


# ── 내부 유틸 ────────────────────────────────

def _parse_response(text: str) -> dict:
    """Gemini 응답에서 JSON을 파싱합니다."""
    try:
        # 마크다운 코드블록 제거
        clean = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(clean)
    except json.JSONDecodeError as e:
        print(f"[경고] Gemini 응답 파싱 실패: {e}")
        return {"raw_response": text, "error": str(e)}


def _frame_timestamp(path: str) -> float:
    match = re.search(r"_(\d+(?:\.\d+)?)s\.(?:jpg|jpeg|png)$", str(path), re.IGNORECASE)
    return float(match.group(1)) if match else 0.0


def _clamp_score(value, default: float = 0.0) -> float:
    try:
        return round(max(0.0, min(float(value), 100.0)), 1)
    except (TypeError, ValueError):
        return default


def _normalize_bbox(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    try:
        x = max(0.0, min(float(value.get("x", 0)), 100.0))
        y = max(0.0, min(float(value.get("y", 0)), 100.0))
        width = max(1.0, min(float(value.get("width", 0)), 100.0 - x))
        height = max(1.0, min(float(value.get("height", 0)), 100.0 - y))
    except (TypeError, ValueError):
        return None
    return {"x": round(x, 1), "y": round(y, 1), "width": round(width, 1), "height": round(height, 1)}


def _normalize_box_2d(value) -> dict | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        y_min, x_min, y_max, x_max = [max(0.0, min(float(item), 1000.0)) for item in value]
    except (TypeError, ValueError):
        return None
    if x_max <= x_min or y_max <= y_min:
        return None
    return {
        "x": round(x_min / 10, 1),
        "y": round(y_min / 10, 1),
        "width": round((x_max - x_min) / 10, 1),
        "height": round((y_max - y_min) / 10, 1),
    }


def _normalize_analysis(result: dict) -> dict:
    """Keep older or partially valid model responses usable by the UI."""
    if not isinstance(result, dict):
        return {"error": "Gemini 응답이 객체 형식이 아닙니다."}

    scores = result.get("category_scores") if isinstance(result.get("category_scores"), dict) else {}
    normalized_scores = {
        key: _clamp_score(scores.get(key))
        for key in ["hook", "pacing", "audio", "visual", "engagement"]
    }
    non_zero = [score for score in normalized_scores.values() if score > 0]
    result["category_scores"] = normalized_scores
    result["overall_score"] = _clamp_score(
        result.get("overall_score"),
        round(sum(non_zero) / len(non_zero), 1) if non_zero else 0.0,
    )

    timeline = []
    for item in result.get("timeline_diagnostics") or []:
        if not isinstance(item, dict):
            continue
        timeline.append({
            "timestamp_seconds": max(0.0, float(item.get("timestamp_seconds") or 0)),
            "kind": item.get("kind") if item.get("kind") in {"strength", "risk"} else "risk",
            "title": str(item.get("title") or "확인할 구간"),
            "reason": str(item.get("reason") or "AI가 주의 구간으로 분류했습니다."),
            "predicted_retention": _clamp_score(item.get("predicted_retention")),
            "confidence": item.get("confidence") if item.get("confidence") in {"low", "medium", "high"} else "low",
            "action": str(item.get("action") or "원본 영상을 확인해 편집 여부를 결정하세요."),
        })
    result["timeline_diagnostics"] = sorted(timeline, key=lambda item: item["timestamp_seconds"])
    result["priority_actions"] = [str(item) for item in (result.get("priority_actions") or [])[:3]]
    result["subject_bbox"] = _normalize_box_2d(result.get("subject_box_2d")) or _normalize_bbox(result.get("subject_bbox"))
    result["subtitle_bbox"] = _normalize_box_2d(result.get("subtitle_box_2d")) or _normalize_bbox(result.get("subtitle_bbox"))
    result["subject_description"] = str(result.get("subject_description") or "핵심 물품")
    return result


def _merge_signal_analysis(result: dict, signals: dict) -> dict:
    """Use measured full-video signals as the timeline source of truth."""
    model_diagnostics = result.get("timeline_diagnostics") or []
    measured = []
    curve = signals.get("timeline_signals") or []
    for item in signals.get("timeline_diagnostics") or []:
        point = min(
            curve,
            key=lambda row: abs(float(row.get("timestamp_seconds", 0)) - float(item.get("timestamp_seconds", 0))),
            default={},
        )
        measured.append({
            **item,
            "predicted_retention": point.get("predicted_retention", 0),
        })

    result["semantic_timeline_diagnostics"] = model_diagnostics
    result["timeline_diagnostics"] = measured
    result["timeline_signals"] = curve
    result["signal_summary"] = signals.get("signal_summary", {})
    result["duration_seconds"] = signals.get("duration_seconds", 0)
    result["analysis_basis"] = (
        "Hybrid: full-video motion/audio measurements plus Gemini semantic frame analysis. "
        "Retention remains a heuristic, not Instagram measured retention."
    )
    result["prediction_confidence"] = (
        "medium" if signals.get("sample_count", 0) >= 20 else "low"
    )
    measured_actions = [item.get("action") for item in measured if item.get("kind") == "risk" and item.get("action")]
    result["priority_actions"] = list(dict.fromkeys(measured_actions + result.get("priority_actions", [])))[:3]
    return result


def format_report(analysis: dict) -> str:
    """데모용 간단 텍스트 보고서를 생성합니다."""
    return f"""
=== 릴스 분석 데모 리포트 ===

촬영 구도: {", ".join(analysis.get("camera_angles", [])) or "-"}
컷 속도: {analysis.get("cut_speed", "-")}
후킹 장면/문구: {analysis.get("hook_text", "-")}
자막 위치: {analysis.get("subtitle_position", "-")}
색감: {analysis.get("color_tone", "-")}
BGM 분위기: {analysis.get("bgm_mood", "-")}
캡션 후킹: {", ".join(analysis.get("caption_hooks", [])) or "-"}
AI 예상 종합 점수: {analysis.get("overall_score", "-")}
우선 수정: {" / ".join(analysis.get("priority_actions", [])) or "-"}

요약:
{analysis.get("analysis_summary", "-")}

프레임 수: {analysis.get("frame_count", "-")}
토큰 사용량: {analysis.get("usage_metadata", {})}
""".strip()


# ── 빠른 테스트 ───────────────────────────────
if __name__ == "__main__":
    # 캡션 분석 테스트 (API 키만 있으면 바로 가능)
    test_caption = "☕ 카페 사장님들 주목! 이렇게 찍으면 조회수 10배 됩니다 #카페스타그램 #소상공인"
    result = analyze_caption_only(test_caption)
    print(result)
