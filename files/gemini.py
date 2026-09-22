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
import argparse
import re
from datetime import datetime
from collections import Counter
import httpx
from PIL import Image
import google.generativeai as genai
from dotenv import load_dotenv

from frame_extractor import extract_frames, cleanup_frames

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if GEMINI_API_KEY:
    os.environ.setdefault("GOOGLE_API_KEY", GEMINI_API_KEY)
genai.configure(api_key=GEMINI_API_KEY)
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")


# ── 프롬프트 ─────────────────────────────────

ANALYSIS_PROMPT = """
당신은 인스타그램 릴스 마케팅 전문 분석가입니다.
아래는 릴스 영상에서 추출한 프레임 이미지들입니다.
첫 1~4초 후킹 구간을 더 촘촘히 추출했고, 이후 중반/후반 프레임도 함께 포함했습니다.
이를 바탕으로 소상공인이 참고할 수 있는 인사이트를 추출해주세요.

[분석 항목]
1. camera_angles: 발견된 촬영 구도 목록 (탑뷰, 클로즈업, 팔로잉샷, 정면샷 등)
2. hook_text: 초반 후킹 구간에서 보이는 문구, 제품, 행동, 핵심 장면 설명
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
  "timeline_segments": [
    {
      "time_range": "0~1초",
      "camera_angle": "클로즈업",
      "content": "첫 화면에 보여줄 장면",
      "purpose": "시선을 멈추게 하는 역할"
    }
  ],
  "analysis_summary": "이 영상은 ..."
}
"""


# ── 보고서 포맷 ───────────────────────────────

def _derive_reel_title(caption: str = "", fallback: str = "") -> str:
    """
    별도 제목이 없으면 캡션의 첫 의미 있는 줄을 보고서 제목처럼 사용합니다.
    """
    for line in (caption or "").splitlines():
        title = line.strip()
        if title and not set(title) <= {"-", ".", "_"}:
            return title[:80]
    return fallback or "릴스"


def _safe_filename(text: str, max_length: int = 60) -> str:
    """
    Windows 파일명에 안전한 짧은 이름을 만듭니다.
    """
    cleaned = re.sub(r'[\\/:*?"<>|]+', " ", text)
    cleaned = "".join(ch if (ch.isalnum() or ch in " ._-") else " " for ch in cleaned)
    cleaned = re.sub(r"\s+", "_", cleaned).strip("._ ")
    return (cleaned or "reel")[:max_length]


def _read_download_log(log_path: str = "videos/download_log.jsonl") -> list[dict]:
    if not os.path.exists(log_path):
        return []

    entries = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries


def _find_reel_metadata(video_path: str = "", reel_id: str = "") -> dict:
    video_name = os.path.basename(video_path)
    normalized_video_path = os.path.normcase(os.path.normpath(video_path)) if video_path else ""

    for entry in _read_download_log():
        code = entry.get("code", "")
        local_path = entry.get("local_video_path", "")
        normalized_local_path = os.path.normcase(os.path.normpath(local_path)) if local_path else ""

        if reel_id and reel_id == code:
            return entry
        if video_name and video_name == os.path.basename(local_path):
            return entry
        if normalized_video_path and normalized_video_path == normalized_local_path:
            return entry

    return {}


def _extract_frame_timestamp(frame_path: str) -> float | None:
    match = re.search(r"_(\d+(?:\.\d+)?)s\.jpg$", os.path.basename(frame_path))
    if not match:
        return None
    return float(match.group(1))


def _format_frame_timeline(frame_paths: list[str]) -> str:
    lines = []
    for idx, frame_path in enumerate(frame_paths, start=1):
        timestamp = _extract_frame_timestamp(frame_path)
        if timestamp is None:
            lines.append(f"- frame {idx}: 시간 정보 없음")
        else:
            lines.append(f"- frame {idx}: {timestamp:.2f}초")
    return "\n".join(lines)


def _select_top_reels(limit: int = 5, log_path: str = "videos/download_log.jsonl") -> list[dict]:
    entries = [
        entry for entry in _read_download_log(log_path)
        if entry.get("status") == "downloaded" and entry.get("local_video_path")
    ]
    entries.sort(key=lambda entry: entry.get("rank_score") or 0, reverse=True)
    return entries[:limit]


def _aggregate_analyses(analyses: list[dict]) -> dict:
    stats = {}

    all_angles = []
    all_hooks = []
    for item in analyses:
        analysis = item.get("analysis", {})
        all_angles.extend(analysis.get("camera_angles", []))
        all_hooks.extend(analysis.get("caption_hooks", []))

    stats["camera_angles"] = dict(Counter(all_angles).most_common())
    for field in ("subtitle_position", "color_tone"):
        values = [
            item.get("analysis", {}).get(field)
            for item in analyses
            if item.get("analysis", {}).get(field)
        ]
        stats[field] = dict(Counter(values).most_common())

    stats["caption_hooks"] = dict(Counter(all_hooks).most_common())
    return stats


def _format_reference_reels(reference_reels: list[dict]) -> str:
    lines = ["## 참고한 상위 릴스"]
    for idx, reel in enumerate(reference_reels, start=1):
        title = reel.get("title") or reel.get("reel_id") or f"릴스 {idx}"
        username = reel.get("username")
        reel_id = reel.get("reel_id") or reel.get("code")
        url = reel.get("url")
        score = reel.get("score")
        plays = reel.get("plays")

        meta = []
        if username:
            meta.append(f"@{username}")
        if reel_id:
            meta.append(reel_id)
        if score is not None:
            meta.append(f"점수 {score:.2f}")
        if plays:
            meta.append(f"조회수 {plays:,}")

        lines.append(f"{idx}. **{title}** ({' · '.join(meta)})")
        if url:
            lines.append(f"   - {url}")
    return "\n".join(lines)


def generate_top_reels_report(
    analyses: list[dict],
    reference_reels: list[dict],
    business_type: str = "카페",
    keyword: str = "",
) -> str:
    stats = _aggregate_analyses(analyses)
    summaries = [
        {
            "reel_id": item["reel_id"],
            "title": item.get("title"),
            "score": item.get("score"),
            "summary": item.get("analysis", {}).get("analysis_summary", ""),
            "camera_angles": item.get("analysis", {}).get("camera_angles", []),
            "hook_text": item.get("analysis", {}).get("hook_text", ""),
            "subtitle_position": item.get("analysis", {}).get("subtitle_position", ""),
            "color_tone": item.get("analysis", {}).get("color_tone", ""),
            "caption_hooks": item.get("analysis", {}).get("caption_hooks", []),
            "timeline_segments": item.get("analysis", {}).get("timeline_segments", []),
        }
        for item in analyses
    ]

    prompt = f"""
당신은 인스타그램 릴스 마케팅 컨설턴트입니다.
아래는 스코어링으로 선별한 상위 릴스 {len(analyses)}개의 분석 결과입니다.
업종은 '{business_type}'입니다.
사용자가 입력한 분석 키워드는 '{keyword or business_type}'입니다.

참고한 릴스:
{json.dumps(reference_reels, ensure_ascii=False, indent=2)}

공통 패턴 집계:
{json.dumps(stats, ensure_ascii=False, indent=2)}

개별 릴스 분석 요약:
{json.dumps(summaries, ensure_ascii=False, indent=2)}

다음 구조의 마크다운 보고서를 작성하세요.

## 이번 분석에 참고한 상위 릴스
- 각 릴스의 제목, 계정, 점수, URL을 사용자가 한눈에 알 수 있게 정리

## 초 단위 릴스 구성 기준표
- 상위 릴스들의 초반/중반/후반 흐름을 바탕으로 시간대별 기준점을 제시
- 반드시 아래 시간대를 기준으로 작성
  - 0~1초: 스크롤을 멈추게 할 첫 화면
  - 1~3초: 왜 봐야 하는지 설명하는 후킹 구간
  - 3~7초: 핵심 메뉴/공간/혜택을 보여주는 구간
  - 7~12초: 신뢰와 방문 이유를 쌓는 구간
  - 12초 이후: 저장, 공유, 방문 행동을 유도하는 마무리
- 각 시간대마다 '추천 구도', '넣어야 할 내용', '자막/문구 예시', '피해야 할 것'을 작성

## 상위 릴스 5개의 공통 공식
- 시간대별 흐름 외에 공통 구도, 자막 위치, 색감, 캡션 후킹을 구체적으로 정리

## 왜 이 릴스들이 성과가 좋았는지
- 영상/캡션/상품 노출 관점에서 설명

## 내일 바로 찍는 15초 촬영안
- 0초부터 15초까지 따라 찍을 수 있는 샷 리스트를 작성
- 각 줄은 '시간 / 화면 / 구도 / 자막' 형식으로 작성

## 이번 주 핵심 한 줄
- 한 문장으로 요약

조건:
- 전문용어를 줄이고 소상공인이 이해하기 쉽게 작성
- 추상적인 조언보다 촬영 장면과 행동을 구체적으로 제시
- 참고 릴스 URL은 빠뜨리지 말 것
- 시간대별 기준표를 보고서의 핵심으로 작성할 것
- 구도 설명에는 '클로즈업', '탑뷰', '아이레벨', '와이드샷', '팔로잉샷' 같은 전문 용어를 되도록 쓰지 말 것
- 대신 '음식이 화면을 꽉 채우게 가까이 찍기', '위에서 내려다보듯 찍기', '눈높이에서 찍기', '공간이 넓게 보이게 찍기', '걸어 들어가듯 따라가며 찍기'처럼 사용자가 바로 따라 할 수 있는 말로 작성할 것
"""

    model = genai.GenerativeModel(MODEL_NAME)
    response = model.generate_content(prompt)
    return response.text.strip()


def analyze_top_reels(
    limit: int = 5,
    business_type: str = "카페",
    keyword: str = "",
    output_path: str = "",
) -> str:
    top_reels = _select_top_reels(limit)
    if not top_reels:
        raise RuntimeError("분석할 다운로드 릴스를 찾지 못했습니다.")

    analyses = []
    reference_reels = []
    for idx, reel in enumerate(top_reels, start=1):
        reel_id = reel.get("code") or f"reel_{idx}"
        caption = reel.get("caption", "")
        title = _derive_reel_title(caption, fallback=reel_id)
        video_path = reel.get("local_video_path")

        print(f"[{idx}/{len(top_reels)}] 상위 릴스 분석 중: {title} ({reel_id})")
        result = analyze_reel_from_file(video_path, caption=caption, reel_id=reel_id)
        analysis = result.get("analysis", {})

        analyses.append({
            "reel_id": reel_id,
            "title": title,
            "score": reel.get("rank_score"),
            "analysis": analysis,
        })
        reference_reels.append({
            "title": title,
            "reel_id": reel_id,
            "username": reel.get("username", ""),
            "url": reel.get("url", ""),
            "score": reel.get("rank_score"),
            "plays": reel.get("ig_play_count", 0),
            "likes": reel.get("like_count", 0),
            "shares": reel.get("share_count", 0),
        })

    report = generate_top_reels_report(
        analyses,
        reference_reels,
        business_type=business_type,
        keyword=keyword,
    )

    if not output_path:
        date_prefix = datetime.now().strftime("%Y%m%d")
        report_label = keyword or business_type
        filename = f"{date_prefix}_상위{limit}개_{_safe_filename(report_label, 20)}_릴스_공통패턴_보고서.md"
        output_path = os.path.join("reports", filename)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"[Gemini] 상위 릴스 종합 보고서 저장 완료: {output_path}")
    return output_path


def format_report(
    analysis: dict,
    reel_id: str = "",
    insights: dict = None,
    reference_reels: list[dict] = None,
) -> str:
    """
    분석 결과를 읽기 좋은 텍스트 보고서로 변환합니다.
    """
    lines = []
    lines.append("=" * 50)
    lines.append("📋 릴스 분석 보고서")
    if reel_id:
        lines.append(f"   릴스 ID: {reel_id}")
    lines.append("=" * 50)

    if reference_reels:
        lines.append("\n🔎 참고한 릴스")
        for idx, reel in enumerate(reference_reels, start=1):
            title = reel.get("title") or reel.get("caption_title") or reel.get("reel_id") or f"릴스 {idx}"
            username = reel.get("username")
            url = reel.get("url")
            code = reel.get("reel_id") or reel.get("code")

            meta = []
            if username:
                meta.append(f"@{username}")
            if code:
                meta.append(code)

            suffix = f" ({' · '.join(meta)})" if meta else ""
            lines.append(f"  {idx}. {title}{suffix}")
            if url:
                lines.append(f"     {url}")

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

    timeline_segments = analysis.get("timeline_segments", [])
    if timeline_segments:
        lines.append("\n⏱️ 초 단위 구성")
        for segment in timeline_segments:
            lines.append(f"  · {segment.get('time_range', '-')}")
            lines.append(f"    - 구도: {segment.get('camera_angle', '-')}")
            lines.append(f"    - 내용: {segment.get('content', '-')}")
            lines.append(f"    - 역할: {segment.get('purpose', '-')}")

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
    reference_reels: list[dict] = None,
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
    frame_timeline = _format_frame_timeline(frames)
    if frame_timeline:
        prompt += f"\n\n[프레임 시간 정보]\n아래 순서는 전달된 이미지 순서와 같습니다.\n{frame_timeline}"
    if caption:
        prompt += f"\n\n[본문 캡션]\n{caption}"

    # 4. Gemini 요청 (이미지 리스트 + 프롬프트)
    print(f"[Gemini] {len(images)}장 프레임으로 분석 시작...")
    response = model.generate_content([*images, prompt])
    analysis = _parse_response(response.text)

    # 5. 보고서 생성
    report = format_report(
        analysis,
        reel_id=reel_id,
        insights=insights,
        reference_reels=reference_reels,
    )
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
    reference_reels: list[dict] = None,
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
        result = analyze_reel_from_file(tmp_path, caption, reel_id, insights, reference_reels)
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


# ── CLI 실행 ─────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="릴스 영상을 분석하고 보고서를 파일로 저장합니다.")
    parser.add_argument("--video", help="분석할 로컬 영상 파일 경로")
    parser.add_argument("--top", type=int, default=0, help="download_log 기준 상위 N개 릴스를 종합 분석")
    parser.add_argument("--business-type", default="카페", help="보고서 업종")
    parser.add_argument("--keyword", default="", help="분석 키워드. 예: 성수동카페, 강남네일, 홍대맛집")
    parser.add_argument("--caption", default="", help="릴스 본문 캡션")
    parser.add_argument("--title", default="", help="보고서에 표시할 릴스 제목")
    parser.add_argument("--url", default="", help="참고한 인스타그램 릴스 URL")
    parser.add_argument("--username", default="", help="참고한 릴스 계정명")
    parser.add_argument("--reel-id", default="", help="보고서에 표시할 릴스 ID")
    parser.add_argument("--output", default="", help="저장할 보고서 파일 경로 (.md 권장)")
    parser.add_argument("--plays", type=int, default=0, help="조회수")
    parser.add_argument("--likes", type=int, default=0, help="좋아요 수")
    parser.add_argument("--saved", type=int, default=0, help="저장 수")
    parser.add_argument("--shares", type=int, default=0, help="공유 수")
    args = parser.parse_args()

    if args.top:
        keyword = args.keyword.strip()
        if not keyword:
            try:
                keyword = input(f"분석 키워드를 입력하세요 (Enter: {args.business_type}): ").strip()
            except EOFError:
                keyword = ""

        analyze_top_reels(
            limit=args.top,
            business_type=args.business_type,
            keyword=keyword,
            output_path=args.output,
        )
    elif not args.video:
        test_caption = "☕ 카페 사장님들 주목! 이렇게 찍으면 조회수 10배 됩니다 #카페스타그램 #소상공인"
        result = analyze_caption_only(test_caption)
        print(result)
    else:
        metadata = _find_reel_metadata(video_path=args.video, reel_id=args.reel_id)
        caption = args.caption or metadata.get("caption", "")
        reel_id = args.reel_id or metadata.get("code", "") or os.path.splitext(os.path.basename(args.video))[0]
        title = args.title or _derive_reel_title(caption, fallback=reel_id)
        url = args.url or metadata.get("url", "")
        username = args.username or metadata.get("username", "")

        reference_reels = [{
            "title": title,
            "reel_id": reel_id,
            "username": username,
            "url": url,
        }]

        insights = {
            "plays": args.plays or metadata.get("ig_play_count", 0),
            "likes": args.likes or metadata.get("like_count", 0),
            "saved": args.saved,
            "shares": args.shares or metadata.get("share_count", 0),
        }
        result = analyze_reel_from_file(
            args.video,
            caption=caption,
            reel_id=reel_id,
            insights=insights,
            reference_reels=reference_reels,
        )

        if "error" in result:
            raise RuntimeError(result["error"])

        output_path = args.output
        if not output_path:
            date_prefix = datetime.now().strftime("%Y%m%d")
            filename = f"{date_prefix}_{_safe_filename(title)}_{_safe_filename(reel_id, 24)}_report.md"
            output_path = os.path.join("reports", filename)

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result["report"])

        print(f"[Gemini] 보고서 저장 완료: {output_path}")
