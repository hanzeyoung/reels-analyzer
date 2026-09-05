"""
api/gemini.py
Gemini 1.5 Pro — 멀티모달 릴스 영상 분석 모듈
(비전 + 텍스트 분석)
"""

import io
import os
import json
import tempfile
from pathlib import Path

import google.generativeai as genai
import httpx
from dotenv import load_dotenv
from PIL import Image

from app.core.frame_extractor import extract_unique_frames

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if GEMINI_API_KEY:
    os.environ.setdefault("GOOGLE_API_KEY", GEMINI_API_KEY)
genai.configure(api_key=GEMINI_API_KEY)
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")


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

반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트 없이 JSON만 출력하세요.

{
  "camera_angles": ["탑뷰", "클로즈업"],
  "cut_speed": "빠름",
  "hook_text": "후킹 문구 또는 장면 설명",
  "subtitle_position": "하단",
  "color_tone": "따뜻함",
  "bgm_mood": "신나는",
  "caption_hooks": ["후킹패턴1", "후킹패턴2"],
  "analysis_summary": "이 영상은 ..."
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
    with tempfile.TemporaryDirectory(prefix="reel_frames_") as frame_dir:
        frame_paths = extract_unique_frames(video_path, output_dir=frame_dir)
        return analyze_reel_from_frames(frame_paths, caption=caption)


def analyze_reel_from_frames(
    frame_paths: list[str],
    caption: str = "",
) -> dict:
    """
    추출된 프레임 이미지 목록을 Gemini Flash로 분석합니다.

    영상 전체 업로드 대신 JPEG 프레임만 보내므로 트래픽과 토큰 사용량을 줄일 수 있습니다.
    """
    if not frame_paths:
        raise ValueError("분석할 프레임이 없습니다.")

    model = genai.GenerativeModel(MODEL_NAME)

    print(f"[Gemini] 프레임 {len(frame_paths)}장 분석 중")
    images = [Image.open(path) for path in frame_paths]

    prompt = ANALYSIS_PROMPT
    if caption:
        prompt += f"\n\n[본문 캡션]\n{caption}"

    response = model.generate_content([*images, prompt])
    result = _parse_response(response.text)
    result["frame_count"] = len(frame_paths)

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
    model = genai.GenerativeModel(MODEL_NAME)

    img_bytes = httpx.get(thumbnail_url).content
    image = Image.open(io.BytesIO(img_bytes))

    prompt = ANALYSIS_PROMPT
    if caption:
        prompt += f"\n\n[본문 캡션]\n{caption}"

    response = model.generate_content([image, prompt])
    return _parse_response(response.text)


# ── 텍스트(캡션)만 분석 ──────────────────────

def analyze_caption_only(caption: str) -> dict:
    """
    영상 없이 캡션 텍스트만으로 후킹 패턴을 분석합니다.
    """
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
