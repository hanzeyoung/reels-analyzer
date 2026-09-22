"""Conservative commercial-use guidance for suggested audio."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

MAINSTREAM_TRACKS = {"espresso", "apt.", "golden", "ordinary"}
SAFE_SOURCES = {"meta_sound_collection", "owned", "commissioned", "licensed_by_business"}
REGISTRY_PATH = Path("user_reels/audio_rights_registry.json")

AUDIO_DIRECTIONS = (
    {"id": "warm_acoustic", "name": "포근한 어쿠스틱", "bpm": "82–94", "keywords": "warm acoustic cafe gentle guitar", "fits": ("분위기", "공간", "햇살", "브런치", "감성"), "use": "공간과 메뉴를 천천히 보여주는 장면"},
    {"id": "playful_bossa", "name": "경쾌한 보사노바", "bpm": "98–112", "keywords": "playful bossa nova cafe upbeat", "fits": ("카페", "메뉴", "데이트", "여행", "밝"), "use": "메뉴 공개와 손동작을 밝게 연결하는 장면"},
    {"id": "clean_lofi", "name": "깔끔한 로파이 비트", "bpm": "76–90", "keywords": "clean lofi beat minimal food", "fits": ("디테일", "질감", "차분", "과정", "클로즈업"), "use": "제품 디테일과 자막을 또렷하게 보여주는 장면"},
    {"id": "city_indie", "name": "산뜻한 인디 팝", "bpm": "104–120", "keywords": "bright indie pop city discovery", "fits": ("동네", "발견", "로컬", "골목", "신상"), "use": "외관에서 대표 장면으로 빠르게 넘어가는 흐름"},
    {"id": "soft_funk", "name": "리듬감 있는 소프트 펑크", "bpm": "108–124", "keywords": "soft funk groove product reel", "fits": ("손", "만들", "과정", "빠름", "활기"), "use": "손동작과 빠른 컷을 박자에 맞추는 장면"},
)


def recommend_audio_options(project: dict, limit: int = 5) -> list[dict]:
    """Rank several searchable music directions from this project's own evidence."""
    source = project.get("source") or {}
    synthesis = source.get("synthesis") or {}
    visual = source.get("visual_synthesis") or {}
    evidence = " ".join([
        str(project.get("title") or ""),
        str(project.get("concept") or ""),
        str(project.get("hook") or ""),
        str(source.get("query") or ""),
        str(visual.get("top_bgm_mood") or ""),
        str(visual.get("top_cut_speed") or ""),
        " ".join(str(value) for value in synthesis.get("repeated_terms") or []),
        " ".join(str(item.get("label") or "") for item in synthesis.get("common_patterns") or []),
    ]).lower()
    ranked = []
    for order, option in enumerate(AUDIO_DIRECTIONS):
        matches = [word for word in option["fits"] if word.lower() in evidence]
        score = len(matches) * 10 - order
        reason = f"프로젝트 근거 ‘{', '.join(matches[:3])}’와 잘 맞음" if matches else option["use"]
        ranked.append({**option, "score": score, "reason": reason, "rights_source": "meta_sound_collection"})
    return sorted(ranked, key=lambda option: option["score"], reverse=True)[:max(1, limit)]


def classify_audio_rights(
    track: dict,
    intended_use: str = "organic_business",
    account_type: str = "business",
) -> dict:
    """Classify evidence, never claiming a legal right that was not supplied."""
    name = str(track.get("곡명") or track.get("name") or "").strip()
    source = str(track.get("rights_source") or track.get("source") or "").lower()
    license_name = str(track.get("license") or "").strip()
    normalized = name.lower()
    expires_at = str(track.get("expires_at") or "").strip()
    if expires_at:
        try:
            if datetime.fromisoformat(expires_at).date() < datetime.now().date():
                return {
                    "status": "라이선스 만료",
                    "level": "restricted",
                    "detail": f"등록된 사용 권한이 {expires_at}에 만료됐습니다. 갱신 증빙 전에는 사용하지 마세요.",
                    "expires_at": expires_at,
                }
        except ValueError:
            return {
                "status": "만료일 형식 확인 필요",
                "level": "review",
                "detail": "라이선스 만료일이 올바른 YYYY-MM-DD 형식이 아닙니다.",
            }

    if license_name and source in SAFE_SOURCES:
        return {
            "status": "라이선스 확인됨",
            "level": "safe",
            "detail": f"증빙된 라이선스: {license_name}. 사용 목적 {intended_use} 범위가 포함되는지 확인하세요.",
            "verified_at": track.get("verified_at"),
            "evidence_url": track.get("evidence_url", ""),
            "evidence_path": track.get("evidence_path", ""),
            "expires_at": expires_at,
        }
    if source in {"original", "owned"} or "original audio" in normalized or "원본 음원" in normalized:
        return {
            "status": "권리 보유 여부 확인",
            "level": "review",
            "detail": "원본 음원 표시는 자동 사용 허가를 뜻하지 않습니다. 직접 제작했거나 권리를 확보했는지 확인하세요.",
        }
    if normalized in MAINSTREAM_TRACKS:
        return {
            "status": "비즈니스 계정 제한 가능",
            "level": "restricted",
            "detail": "상업 음악은 계정 유형과 지역에 따라 사용할 수 없을 수 있습니다. Instagram 앱의 상업용 음악 라이브러리에서 확인하세요.",
            "safe_alternative": "Meta Sound Collection에서 같은 분위기의 royalty-free 음원을 선택하세요.",
        }
    if account_type == "business" or intended_use in {"ad", "paid_campaign", "branded_content"}:
        return {
            "status": "비즈니스 사용 증빙 필요",
            "level": "unknown",
            "detail": "공개 릴스에서 사용됐다는 사실은 상업 이용 허가가 아닙니다. 계정에서 직접 사용 가능 여부와 광고 사용 범위를 확인하세요.",
            "safe_alternative": "Meta Sound Collection 또는 별도 상업 라이선스 음원을 사용하세요.",
        }
    return {
        "status": "사용 전 확인 필요",
        "level": "unknown",
        "detail": "곡명만으로 상업 이용 권한을 판단할 수 없습니다. Instagram 또는 편집 도구에서 라이선스 범위를 확인하세요.",
        "safe_alternative": "권리 증빙이 가능한 음원으로 교체하세요.",
    }


def load_rights_registry(path: str | Path = REGISTRY_PATH) -> dict:
    target = Path(path)
    if not target.exists():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_rights_verification(
    track_name: str,
    source: str,
    license_name: str,
    evidence_url: str = "",
    notes: str = "",
    evidence_path: str = "",
    expires_at: str = "",
    path: str | Path = REGISTRY_PATH,
) -> dict:
    registry = load_rights_registry(path)
    registry[track_name.strip().lower()] = {
        "rights_source": source,
        "license": license_name,
        "evidence_url": evidence_url,
        "notes": notes,
        "evidence_path": evidence_path,
        "expires_at": expires_at,
        "verified_at": datetime.now().isoformat(timespec="seconds"),
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    return registry[track_name.strip().lower()]


def annotate_tracks(
    tracks: list[dict],
    intended_use: str = "organic_business",
    account_type: str = "business",
    registry_path: str | Path = REGISTRY_PATH,
) -> list[dict]:
    registry = load_rights_registry(registry_path)
    annotated = []
    for track in tracks:
        evidence = registry.get(str(track.get("곡명") or "").strip().lower(), {})
        enriched = {**track, **evidence}
        annotated.append({
            **enriched,
            "rights": classify_audio_rights(enriched, intended_use=intended_use, account_type=account_type),
        })
    return annotated
