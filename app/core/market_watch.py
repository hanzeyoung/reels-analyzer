"""Build and persist local market snapshots from collected public reel metadata."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import hashlib
from pathlib import Path

import requests


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z가-힣_-]+", "-", value).strip("-")
    return slug[:80] or "market"


def build_market_snapshot(reels: list[dict], query: str) -> dict:
    accounts = defaultdict(lambda: {"reel_count": 0, "views": 0, "likes": 0, "shares": 0, "top_reel": ""})
    hashtags = Counter()
    tracks = Counter()
    media = []

    for reel in reels:
        username = str(reel.get("username") or reel.get("사용자") or "unknown").lstrip("@")
        views = int(reel.get("ig_play_count") or reel.get("조회수") or 0)
        likes = int(reel.get("like_count") or reel.get("좋아요") or 0)
        shares = int(reel.get("share_count") or reel.get("공유") or 0)
        account = accounts[username]
        account["reel_count"] += 1
        account["views"] += views
        account["likes"] += likes
        account["shares"] += shares
        if not account["top_reel"] or views > account.get("top_views", -1):
            account["top_views"] = views
            account["top_reel"] = reel.get("url") or reel.get("링크") or ""
        for tag in re.findall(r"#[0-9A-Za-z가-힣_]+", str(reel.get("caption") or reel.get("캡션") or "")):
            hashtags[tag] += 1
        track = str(reel.get("audio_title") or reel.get("음원") or reel.get("BGM곡") or "").strip()
        if track:
            tracks[track] += 1
        media.append({
            "media_id": str(reel.get("id") or reel.get("code") or reel.get("url") or reel.get("링크") or ""),
            "username": username,
            "views": views,
            "likes": likes,
            "shares": shares,
            "url": reel.get("url") or reel.get("링크") or "",
            "caption": str(reel.get("caption") or reel.get("캡션") or "")[:500],
            "track": track,
            "thumbnail_url": reel.get("thumbnail_url") or reel.get("thumbnail") or "",
            "video_url": reel.get("video_url") or reel.get("media_url") or "",
            "published_at": reel.get("taken_at_date") or reel.get("taken_at") or "",
        })

    ranked = sorted(
        ({"username": username, **values} for username, values in accounts.items()),
        key=lambda item: (item["views"], item["likes"]),
        reverse=True,
    )
    return {
        "query": query,
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "reel_count": len(reels),
        "accounts": ranked,
        "media": media,
        "top_hashtags": [name for name, _ in hashtags.most_common(10)],
        "top_tracks": [name for name, _ in tracks.most_common(10)],
    }


def compare_snapshots(previous: dict | None, current: dict) -> list[dict]:
    previous_accounts = {item["username"]: item for item in (previous or {}).get("accounts", [])}
    changes = []
    previous_media = {item.get("media_id"): item for item in (previous or {}).get("media", []) if item.get("media_id")}
    current_media = {item.get("media_id"): item for item in current.get("media", []) if item.get("media_id")}
    overlap_ids = set(previous_media).intersection(current_media)
    account_overlap = defaultdict(lambda: {"views": 0, "count": 0})
    for media_id in overlap_ids:
        before_media = previous_media[media_id]
        after_media = current_media[media_id]
        username = after_media.get("username", "unknown")
        account_overlap[username]["views"] += after_media.get("views", 0) - before_media.get("views", 0)
        account_overlap[username]["count"] += 1
    for item in current.get("accounts", []):
        before = previous_accounts.get(item["username"], {})
        changes.append({
            **item,
            "view_delta": item.get("views", 0) - before.get("views", 0),
            "reel_delta": item.get("reel_count", 0) - before.get("reel_count", 0),
            "is_new": not bool(before),
            "same_media_view_delta": account_overlap[item["username"]]["views"],
            "same_media_count": account_overlap[item["username"]]["count"],
        })
    coverage = len(overlap_ids) / max(len(current_media), 1)
    for item in changes:
        item["comparison_coverage"] = round(coverage * 100, 1)
        item["comparison_confidence"] = "high" if coverage >= 0.7 else ("medium" if coverage >= 0.4 else "low")
    return sorted(changes, key=lambda item: (item["same_media_view_delta"], item["view_delta"]), reverse=True)


def save_snapshot(snapshot: dict, base_dir: str | Path = "user_reels/market_snapshots") -> Path:
    directory = Path(base_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = directory / f"{_safe_slug(snapshot.get('query', 'market'))}_{stamp}.json"
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_previous_snapshot(query: str, base_dir: str | Path = "user_reels/market_snapshots") -> dict | None:
    directory = Path(base_dir)
    files = sorted(directory.glob(f"{_safe_slug(query)}_*.json"), reverse=True)
    if not files:
        return None
    try:
        return json.loads(files[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def build_market_alerts(previous: dict | None, current: dict, min_views: int = 10000) -> list[dict]:
    """Create actionable alerts from new reels and stable same-media growth."""
    previous_media = {item.get("media_id"): item for item in (previous or {}).get("media", []) if item.get("media_id")}
    alerts = []
    for item in current.get("media", []):
        media_id = item.get("media_id")
        before = previous_media.get(media_id)
        if before:
            delta = item.get("views", 0) - before.get("views", 0)
            if delta >= min_views:
                alerts.append({
                    "type": "fast_growth",
                    "severity": "high",
                    "username": item.get("username"),
                    "message": f"기존 릴스 조회수가 {delta:,}회 증가했습니다.",
                    "url": item.get("url", ""),
                    "media_id": media_id,
                })
        elif item.get("views", 0) >= min_views:
            alerts.append({
                "type": "new_breakout",
                "severity": "high",
                "username": item.get("username"),
                "message": f"새로 발견된 릴스가 조회수 {item.get('views', 0):,}회를 기록했습니다.",
                "url": item.get("url", ""),
                "media_id": media_id,
            })
    return sorted(alerts, key=lambda item: item["severity"] == "high", reverse=True)


def load_watchlist(path: str | Path = "user_reels/market_watchlist.json") -> list[dict]:
    target = Path(path)
    if not target.exists():
        return []
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_watch(
    query: str,
    business_type: str,
    place: str,
    top_n: int = 15,
    path: str | Path = "user_reels/market_watchlist.json",
    alerts_enabled: bool = True,
    min_views: int = 10000,
) -> list[dict]:
    watches = load_watchlist(path)
    entry = {
        "query": query,
        "business_type": business_type,
        "place": place,
        "top_n": top_n,
        "alerts_enabled": bool(alerts_enabled),
        "min_views": max(1, int(min_views)),
    }
    watches = [item for item in watches if item.get("query") != query]
    watches.append(entry)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(watches, ensure_ascii=False, indent=2), encoding="utf-8")
    return watches


def _alert_fingerprint(query: str, alert: dict) -> str:
    identity = "|".join([
        query,
        str(alert.get("type") or ""),
        str(alert.get("media_id") or alert.get("url") or ""),
        str(alert.get("message") or ""),
    ])
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def filter_new_alerts(
    query: str,
    alerts: list[dict],
    state_path: str | Path = "user_reels/market_alert_state.json",
    ttl_days: int = 14,
) -> list[dict]:
    target = Path(state_path)
    try:
        state = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
    except (OSError, json.JSONDecodeError):
        state = {}
    cutoff = datetime.now() - timedelta(days=max(1, ttl_days))
    active = {}
    for key, value in state.items():
        try:
            if datetime.fromisoformat(value) >= cutoff:
                active[key] = value
        except (TypeError, ValueError):
            continue
    return [alert for alert in alerts if _alert_fingerprint(query, alert) not in active]


def mark_alerts_sent(
    query: str,
    alerts: list[dict],
    state_path: str | Path = "user_reels/market_alert_state.json",
) -> None:
    target = Path(state_path)
    try:
        state = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
    except (OSError, json.JSONDecodeError):
        state = {}
    now = datetime.now().isoformat(timespec="seconds")
    for alert in alerts:
        state[_alert_fingerprint(query, alert)] = now
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def send_webhook_alerts(webhook_url: str, query: str, alerts: list[dict]) -> bool:
    if not webhook_url or not alerts:
        return False
    heading = f"[{query}] 릴스 시장 변화 {len(alerts)}건"
    lines = [f"• @{item.get('username', 'unknown')}: {item.get('message', '')} {item.get('url', '')}" for item in alerts[:10]]
    if "discord.com/api/webhooks" in webhook_url:
        payload = {"content": heading, "embeds": [{"description": "\n".join(lines), "color": 773610}]}
    elif "hooks.slack.com" in webhook_url:
        payload = {"text": heading + "\n" + "\n".join(lines)}
    else:
        payload = {"text": heading, "query": query, "alerts": alerts[:10]}
    response = requests.post(webhook_url, json=payload, timeout=20)
    response.raise_for_status()
    return True


def append_market_run(record: dict, path: str | Path = "user_reels/market_run_history.jsonl") -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as file:
        file.write(json.dumps({"recorded_at": datetime.now().isoformat(timespec="seconds"), **record}, ensure_ascii=False) + "\n")


def append_delivery_receipt(record: dict, path: str | Path = "user_reels/market_delivery_history.jsonl") -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as file:
        file.write(json.dumps({"recorded_at": datetime.now().isoformat(timespec="seconds"), **record}, ensure_ascii=False) + "\n")


def load_jsonl_history(path: str | Path, limit: int = 20) -> list[dict]:
    target = Path(path)
    if not target.exists():
        return []
    records = []
    for line in target.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            records.append(item)
    return records[-max(1, limit):][::-1]
