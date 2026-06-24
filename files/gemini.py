"""
app/api/gemini.py
Gemini 1.5 Flash — 프레임 이미지 기반 릴스 분석 모듈

변경사항:
- gemini-1.5-pro → gemini-1.5-flash (비용 절감)
- 영상 통째로 업로드 → ffmpeg 프레임 이미지 분석 (트래픽 절감)
"""

import os
import io
import json
import httpx
from PIL import Image
import google.generativeai as genai
from dotenv import load_dotenv

from frame_extractor import extract_frames, cleanup_frames

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
MODEL_NAME = "gemini-1.5-flash"


# ── 프롬프트 ─────────────────────────────────

ANALYSIS_PROMPT = """
당신은 인스타그램 릴스 마케팅 전문 분석가입니다.
아래는 릴스 영상에서 균등한 간격으로 추출한 프레임 이미지들입니다.
이를 바탕으로 소상공인이 참고할 수 있는 인사이트를 추출해주세요.

[분석 항목]
1. camera_angles: 발견된 촬영 구도 목록 (탑뷰, 클로즈업, 팔로잉샷, 정면샷 등)
2. hook_text: 첫 번째 프레임에서 보이는 후킹 요소 또는 핵심 장면 설명
3. subtitle_position: 자막 위치 (상단 / 중앙 / 하단 / 없음)
4. color_tone: 전반적인 색감 분위기 (따뜻함 / 차가움 / 생동감 / 차분함 등)
5. caption_hooks: 본문 캡션에서 발견된 후킹 패턴 목록
6. analysis_summary: 이 영상이 잘 될 수 있었던 이유 2~3줄 요약 (소상공인 눈높이)

※ 프레임 이미지 분석이므로 cut_speed, bgm_mood는 분석하지 않습니다.

반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트 없이 JSON만 출력하세요.

{
  "camera_angles": ["탑뷰", "클로즈업"],
  "hook_text": "후킹 요소 또는 장면 설명",
  "subtitle_position": "하단",
  "color_tone": "따뜻함",
  "caption_hooks": ["후킹패턴1", "후킹패턴2"],
  "analysis_summary": "이 영상은 ..."
}
"""


# ── 보고서 포맷 ───────────────────────────────

def format_report(analysis: dict, reel_id: str = "", insights: dict = None) -> str:
    """
    분석 결과를 읽기 좋은 텍스트 보고서로 변환합니다.
    """
    lines = []
    lines.append("=" * 50)
    lines.append("📋 릴스 분석 보고서")
    if reel_id:
        lines.append(f"   릴스 ID: {reel_id}")
    lines.append("=" * 50)

    if insights:
        lines.append("\n📊 성과 지표")
        lines.append(f"  · 조회수:  {insights.get('plays', 0):,}")
        lines.append(f"  · 좋아요:  {insights.get('likes', 0):,}")
        lines.append(f"  · 저장:    {insights.get('saved', 0):,}")
        lines.append(f"  · 공유:    {insights.get('shares', 0):,}")

    lines.append("\n🎬 영상 분석")
    angles = ", ".join(analysis.get("camera_angles", []))
    lines.append(f"  · 촬영 구도:  {angles or '분석 불가'}")
    lines.append(f"  · 첫 장면:    {analysis.get('hook_text', '-')}")
    lines.append(f"  · 자막 위치:  {analysis.get('subtitle_position', '-')}")
    lines.append(f"  · 색감:       {analysis.get('color_tone', '-')}")

    hooks = analysis.get("caption_hooks", [])
    if hooks:
        lines.append("\n💬 캡션 후킹 패턴")
        for h in hooks:
            lines.append(f"  · {h}")

    lines.append("\n💡 핵심 인사이트")
    lines.append(f"  {analysis.get('analysis_summary', '-')}")
    lines.append("=" * 50)

    return "\n".join(lines)


# ── 로컬 영상 파일로 분석 ─────────────────────

def analyze_reel_from_file(
    video_path: str,
    caption: str = "",
    reel_id: str = "",
    insights: dict = None,
) -> dict:
    """
    로컬 영상 파일을 프레임 추출 후 Gemini Flash로 분석합니다.

    Args:
        video_path: 로컬 영상 파일 경로 (.mp4 등)
        caption: 릴스 본문 캡션
        reel_id: 릴스 ID (보고서용)
        insights: 성과 지표 dict (보고서용)

    Returns:
        {
            "analysis": 분석 결과 dict,
            "report": 텍스트 보고서,
            "frame_count": 사용된 프레임 수
        }
    """
    model = genai.GenerativeModel(MODEL_NAME)

    # 1. 프레임 추출
    frames = extract_frames(video_path)
    if not frames:
        return {"error": "프레임 추출 실패"}

    # 2. PIL 이미지 로드
    images = [Image.open(f) for f in frames]

    # 3. 프롬프트 구성
    prompt = ANALYSIS_PROMPT
    if caption:
        prompt += f"\n\n[본문 캡션]\n{caption}"

    # 4. Gemini 요청 (이미지 리스트 + 프롬프트)
    print(f"[Gemini] {len(images)}장 프레임으로 분석 시작...")
    response = model.generate_content([*images, prompt])
    analysis = _parse_response(response.text)

    # 5. 보고서 생성
    report = format_report(analysis, reel_id=reel_id, insights=insights)
    print(report)

    # 6. 임시 프레임 파일 정리
    cleanup_frames(frames)

    return {
        "analysis": analysis,
        "report": report,
        "frame_count": len(images),
    }


# ── URL에서 영상 다운로드 후 분석 ─────────────

def analyze_reel_from_url(
    media_url: str,
    caption: str = "",
    reel_id: str = "",
    insights: dict = None,
) -> dict:
    """
    media_url에서 영상을 다운로드 후 프레임 분석합니다.
    Meta Graph API의 media_url 필드와 연동합니다.

    Args:
        media_url: 영상 CDN URL (Meta Graph API media_url)
        caption: 릴스 본문 캡션
        reel_id: 릴스 ID
        insights: 성과 지표

    Returns:
        analyze_reel_from_file과 동일한 구조
    """
    import tempfile

    print(f"[Gemini] 영상 다운로드 중: {media_url[:60]}...")
    video_bytes = httpx.get(media_url, follow_redirects=True, timeout=60).content

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(video_bytes)
        tmp_path = f.name

    try:
        result = analyze_reel_from_file(tmp_path, caption, reel_id, insights)
    finally:
        os.unlink(tmp_path)

    return result


# ── 캡션만 분석 ───────────────────────────────

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
        clean = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(clean)
    except json.JSONDecodeError as e:
        print(f"[경고] Gemini 응답 파싱 실패: {e}")
        return {"raw_response": text, "error": str(e)}


# ── 빠른 테스트 ───────────────────────────────
if __name__ == "__main__":
    test_caption = "☕ 카페 사장님들 주목! 이렇게 찍으면 조회수 10배 됩니다 #카페스타그램 #소상공인"
    result = analyze_caption_only(test_caption)
    print(result)
