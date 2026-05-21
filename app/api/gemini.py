"""
api/gemini.py
Gemini 1.5 Pro — 멀티모달 릴스 영상 분석 모듈
(비전 + 텍스트 분석)
"""

import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
MODEL_NAME = "gemini-1.5-pro"


# ── 프롬프트 ─────────────────────────────────

ANALYSIS_PROMPT = """
당신은 인스타그램 릴스 마케팅 전문 분석가입니다.
아래 릴스 영상 및 정보를 분석하여 소상공인이 참고할 수 있는 인사이트를 추출해주세요.

[분석 항목]
1. camera_angles: 영상에서 발견된 촬영 구도 목록 (탑뷰, 클로즈업, 팔로잉샷, 정면샷 등)
2. cut_speed: 컷 편집 속도 (느림 / 보통 / 빠름)
3. hook_text: 첫 3초 내 등장하는 후킹 문구 또는 핵심 장면 설명
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
    로컬 영상 파일을 Gemini에 업로드하여 분석합니다.

    Args:
        video_path: 로컬 영상 파일 경로 (.mp4 등)
        caption: 릴스 본문 캡션

    Returns:
        분석 결과 dict
    """
    model = genai.GenerativeModel(MODEL_NAME)

    print(f"[Gemini] 영상 업로드 중: {video_path}")
    video_file = genai.upload_file(path=video_path)

    prompt = ANALYSIS_PROMPT
    if caption:
        prompt += f"\n\n[본문 캡션]\n{caption}"

    response = model.generate_content([video_file, prompt])
    return _parse_response(response.text)


# ── 썸네일 이미지로 분석 (영상 없을 때 대안) ──

def analyze_reel_from_thumbnail(
    thumbnail_url: str,
    caption: str = "",
) -> dict:
    """
    썸네일 이미지 URL로 부분 분석합니다.
    (영상 파일이 없을 때 대안 — 비전 항목만 가능)
    """
    import httpx
    from PIL import Image
    import io

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


# ── 빠른 테스트 ───────────────────────────────
if __name__ == "__main__":
    # 캡션 분석 테스트 (API 키만 있으면 바로 가능)
    test_caption = "☕ 카페 사장님들 주목! 이렇게 찍으면 조회수 10배 됩니다 #카페스타그램 #소상공인"
    result = analyze_caption_only(test_caption)
    print(result)
