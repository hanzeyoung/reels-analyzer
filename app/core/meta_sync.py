from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.api.meta_graph import collect_my_reels
from app.core.config import get_env, has_env
from app.core.performance_insights import (
    append_performance_snapshot,
    compare_snapshot_windows,
    load_performance_history,
    normalize_insights,
    performance_score,
)
from app.db.supabase_client import configure_service_role, sync_meta_account
from app.core.observability import observed_operation, record_api_usage


LIBRARY_PATH = Path("user_reels") / "library.jsonl"
STORE_PROFILE_PATH = Path("user_reels") / "store_profile.json"


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _upsert_library(entries: list[dict], path: Path = LIBRARY_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                existing.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    by_id = {str(item.get("instagram_media_id") or item.get("릴스") or ""): item for item in existing}
    for entry in entries:
        key = str(entry.get("instagram_media_id") or entry.get("릴스") or "")
        by_id[key] = {**by_id.get(key, {}), **entry}
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in by_id.values()),
        encoding="utf-8",
    )
    temporary.replace(path)


def _library_entry(reel: dict, business_type: str, username: str, store_id: str) -> dict:
    insights = normalize_insights(reel.get("insights"))
    score = performance_score(insights)
    caption = str(reel.get("caption") or "").strip()
    title = next((line.strip() for line in caption.splitlines() if line.strip()), f"@{username} 릴스")
    return {
        "릴스": str(reel.get("id") or ""),
        "instagram_media_id": str(reel.get("id") or ""),
        "릴스명": title[:36],
        "어떤 영상인지": caption[:120] or f"@{username} Instagram 릴스",
        "원문": title[:64],
        "캡션": caption,
        "링크": reel.get("permalink") or "",
        "원격영상": reel.get("media_url") or "",
        "로컬영상": "",
        "사용자": username,
        "출처": "Meta 실측",
        "업종": business_type,
        "store_id": store_id,
        "조회수": int(insights["views"]),
        "좋아요": int(insights["likes"]),
        "저장": int(insights["saved"]),
        "공유": int(insights["shares"]),
        "총점": score,
        "등급": "S" if score >= 80 else ("A" if score >= 60 else ("B" if score >= 40 else "C")),
        "길이(초)": 0,
        "촬영구도": "-",
        "BGM": "-",
        "BGM곡": "",
        "analysis": {},
        "insights": insights,
        "업로드": reel.get("timestamp") or datetime.now().isoformat(timespec="seconds"),
    }


def run_meta_sync(
    access_token: str = "",
    business_type: str = "카페",
    limit: int = 30,
    auth_user_id: str = "",
    library_path: str | Path = LIBRARY_PATH,
    store_profile_path: str | Path = STORE_PROFILE_PATH,
    performance_history_path: str | Path = "user_reels/performance_history.jsonl",
    use_service_role: bool = False,
) -> dict:
    token = access_token or get_env("META_ACCESS_TOKEN")
    if not token:
        raise ValueError("예약 동기화에는 META_ACCESS_TOKEN이 필요합니다.")
    with observed_operation("meta.account_sync", limit=limit):
        payload = collect_my_reels(access_token=token, limit=limit)
    record_api_usage("meta", metadata={"operation": "account_sync", "reels": len(payload.get("reels", []))})
    profile = payload["profile"]
    store_profile = _load_json(Path(store_profile_path))
    entries = []
    changes = {}
    for reel in payload["reels"]:
        reel_id = str(reel.get("id") or "")
        entries.append(_library_entry(reel, business_type, profile.get("username", ""), store_profile.get("store_id", "")))
        append_performance_snapshot(
            reel_id,
            reel.get("insights", {}),
            permalink=reel.get("permalink", ""),
            path=performance_history_path,
        )
        changes[reel_id] = compare_snapshot_windows(load_performance_history(reel_id, path=performance_history_path))
    _upsert_library(entries, Path(library_path))

    cloud_sync = None
    if has_env("SUPABASE_URL") and has_env("SUPABASE_ANON_KEY"):
        try:
            configure_service_role(use_service_role)
            cloud_sync = sync_meta_account(
                profile,
                payload["reels"],
                business_type,
                store_profile,
                auth_user_id=auth_user_id,
            )
        except Exception as exc:
            cloud_sync = {"error": str(exc)}
        finally:
            configure_service_role(False)
    return {
        "username": profile.get("username", ""),
        "synced_reels": len(entries),
        "graph_version": payload.get("graph_version", ""),
        "changes": changes,
        "cloud_sync": cloud_sync,
        "completed_at": datetime.now().isoformat(timespec="seconds"),
    }
