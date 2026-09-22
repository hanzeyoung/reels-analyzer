"""
core/video_analyzer.py
영상 분석 파이프라인 — Gemini로 개별 분석 후 Python으로 패턴 비교

흐름:
  릴스 영상들
    → analyze_single()    : Gemini Vision → 영상 1개 JSON
    → analyze_batch()     : 여러 영상 일괄 분석
    → compare_patterns()  : S급 vs C급 공통점/차이점 추출
    → build_report_input(): 보고서 작성용 인사이트 dict 반환
"""

from collections import Counter
from typing import Optional
from app.api.gemini import analyze_reel_from_file, analyze_reel_from_thumbnail


# ── 단일 영상 분석 ────────────────────────────

def analyze_single(
    reel_id: str,
    video_path: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
    caption: str = "",
    score: Optional[float] = None,
    tier: Optional[str] = None,
) -> dict:
    """
    릴스 1개를 Gemini로 분석하고 메타 정보를 합쳐 반환합니다.

    Args:
        reel_id: 릴스 식별자
        video_path: 로컬 영상 파일 경로 (있으면 우선 사용)
        thumbnail_url: 썸네일 URL (영상 없을 때 대안)
        caption: 본문 캡션
        score: 성과 점수 (비교 분석에 활용)
        tier: 등급 (S/A/B/C)

    Returns:
        {
          "reel_id": "...",
          "tier": "S",
          "score": 87.4,
          "camera_angles": ["탑뷰", "클로즈업"],
          "cut_speed": "빠름",
          "hook_text": "...",
          "subtitle_position": "하단",
          "color_tone": "따뜻함",
          "bgm_mood": "신나는",
          "caption_hooks": [...],
          "analysis_summary": "...",
        }
    """
    if video_path:
        raw = analyze_reel_from_file(video_path, caption)
    elif thumbnail_url:
        raw = analyze_reel_from_thumbnail(thumbnail_url, caption)
    else:
        raise ValueError("video_path 또는 thumbnail_url 중 하나는 필요합니다.")

    return {
        "reel_id": reel_id,
        "tier": tier,
        "score": score,
        **raw,
    }


# ── 다수 영상 일괄 분석 ───────────────────────

def analyze_batch(reels: list[dict]) -> list[dict]:
    """
    여러 릴스를 순서대로 분석합니다.

    Args:
        reels: [
            {
                "reel_id": "reel_001",
                "video_path": "/tmp/reel_001.mp4",   # 또는 thumbnail_url
                "thumbnail_url": "https://...",
                "caption": "...",
                "score": 87.4,
                "tier": "S"
            },
            ...
        ]

    Returns:
        analyze_single() 결과 리스트
    """
    results = []
    for i, reel in enumerate(reels):
        reel_id = reel.get("reel_id", f"reel_{i+1}")
        print(f"[{i+1}/{len(reels)}] 분석 중: {reel_id}")
        try:
            result = analyze_single(
                reel_id=reel_id,
                video_path=reel.get("video_path"),
                thumbnail_url=reel.get("thumbnail_url"),
                caption=reel.get("caption", ""),
                score=reel.get("score"),
                tier=reel.get("tier"),
            )
            results.append(result)
        except Exception as e:
            print(f"  [경고] {reel_id} 분석 실패: {e}")
    return results


# ── 패턴 비교 분석 ────────────────────────────

def compare_patterns(analyses: list[dict]) -> dict:
    """
    분석 결과 목록에서 S/A급(상위)과 B/C급(하위)의 패턴 차이를 추출합니다.

    Args:
        analyses: analyze_single() 결과 리스트

    Returns:
        {
          "top_tier": {
            "camera_angles": {"탑뷰": 8, "클로즈업": 5, ...},
            "cut_speed": {"빠름": 7, "보통": 2, ...},
            "color_tone": {...},
            "bgm_mood": {...},
            "subtitle_position": {...},
          },
          "low_tier": { ... },
          "key_differences": [
            "상위 릴스는 '탑뷰' 구도를 80% 이상 사용하지만, 하위 릴스는 36%에 불과합니다.",
            ...
          ],
          "top_common": {   # 상위 릴스의 최빈값 조합
            "camera_angle": "탑뷰",
            "cut_speed": "빠름",
            "color_tone": "따뜻함",
            "bgm_mood": "신나는",
          }
        }
    """
    top = [a for a in analyses if a.get("tier") in ("S", "A")]
    low = [a for a in analyses if a.get("tier") in ("B", "C")]

    top_stats = _aggregate(top)
    low_stats = _aggregate(low)
    diffs = _find_differences(top_stats, low_stats, len(top), len(low))
    top_common = _most_common_combo(top_stats)

    return {
        "top_tier": top_stats,
        "low_tier": low_stats,
        "top_count": len(top),
        "low_count": len(low),
        "key_differences": diffs,
        "top_common": top_common,
    }


def build_report_input(
    analyses: list[dict],
    business_type: str,
) -> dict:
    """
    보고서 작성에 필요한 모든 인사이트를 하나의 dict로 정리합니다.
    이 dict를 report_writer.generate_report()에 넘기면 됩니다.
    """
    patterns = compare_patterns(analyses)

    return {
        "business_type": business_type,
        "total_analyzed": len(analyses),
        "top_count": patterns["top_count"],
        "low_count": patterns["low_count"],
        "top_common": patterns["top_common"],
        "key_differences": patterns["key_differences"],
        "top_distributions": patterns["top_tier"],
        "individual_summaries": [
            {
                "reel_id": a["reel_id"],
                "tier": a.get("tier"),
                "score": a.get("score"),
                "summary": a.get("analysis_summary", ""),
            }
            for a in analyses
            if a.get("tier") in ("S", "A")
        ],
    }


# ── 내부 헬퍼 ────────────────────────────────

def _aggregate(analyses: list[dict]) -> dict:
    """분석 결과 목록에서 각 특성의 빈도를 집계합니다."""
    if not analyses:
        return {}

    stats = {}

    # camera_angles는 리스트라 flatten
    all_angles = []
    for a in analyses:
        all_angles.extend(a.get("camera_angles", []))
    stats["camera_angles"] = dict(Counter(all_angles))

    # 나머지는 단일 값
    for field in ("cut_speed", "color_tone", "bgm_mood", "subtitle_position"):
        values = [a[field] for a in analyses if field in a and a[field]]
        stats[field] = dict(Counter(values))

    return stats


def _find_differences(
    top: dict,
    low: dict,
    top_n: int,
    low_n: int,
) -> list[str]:
    """
    상위/하위 빈도 분포를 비교해서 의미 있는 차이를 문장으로 반환합니다.
    (비율 차이가 30%p 이상인 항목만 포함)
    """
    diffs = []
    if top_n == 0 or low_n == 0:
        return ["데이터 부족으로 비교가 어렵습니다."]

    comparisons = [
        ("camera_angles", "촬영 구도"),
        ("cut_speed", "컷 편집 속도"),
        ("bgm_mood", "BGM 분위기"),
        ("color_tone", "색감"),
    ]

    for field, label in comparisons:
        top_dist = top.get(field, {})
        low_dist = low.get(field, {})
        if not top_dist:
            continue

        # 상위에서 가장 많은 값
        top_key = max(top_dist, key=top_dist.get)
        top_ratio = top_dist[top_key] / max(sum(top_dist.values()), 1)
        low_ratio = low_dist.get(top_key, 0) / max(sum(low_dist.values()), 1)

        gap = top_ratio - low_ratio
        if gap >= 0.30:
            diffs.append(
                f"상위 릴스는 '{top_key}' {label}을(를) {top_ratio*100:.0f}% 사용하지만, "
                f"하위 릴스는 {low_ratio*100:.0f}%에 불과합니다."
            )

    return diffs if diffs else ["통계적으로 유의미한 차이가 발견되지 않았습니다."]


def _most_common_combo(top_stats: dict) -> dict:
    """상위 릴스에서 각 특성의 최빈값을 추출합니다."""
    result = {}
    for field in ("cut_speed", "color_tone", "bgm_mood", "subtitle_position"):
        dist = top_stats.get(field, {})
        if dist:
            result[field] = max(dist, key=dist.get)

    angles = top_stats.get("camera_angles", {})
    if angles:
        result["camera_angle"] = max(angles, key=angles.get)

    return result
