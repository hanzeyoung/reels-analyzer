"""Run every saved market watch, persist snapshots, and optionally send webhook alerts."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from app.api.reels_collector import get_top_reels
from app.core.config import get_env
from app.core.market_watch import (
    append_delivery_receipt,
    build_market_alerts,
    build_market_snapshot,
    compare_snapshots,
    append_market_run,
    filter_new_alerts,
    load_previous_snapshot,
    load_watchlist,
    save_snapshot,
    send_webhook_alerts,
    mark_alerts_sent,
)
from app.db.supabase_client import insert_market_snapshot
from app.core.observability import init_error_tracking


def main() -> int:
    init_error_tracking("market-watch")
    watchlist_paths = sorted(Path("user_reels").glob("**/market_watchlist.json"))
    watch_jobs = [
        (watch, path.parent)
        for path in watchlist_paths
        for watch in load_watchlist(path)
    ]
    if not watch_jobs:
        print("No saved market watches. Add one from the app first.")
        return 0

    summary = []
    failed = False
    for watch, user_dir in watch_jobs:
        query = watch["query"]
        snapshot_dir = user_dir / "market_snapshots"
        alert_state_path = user_dir / "market_alert_state.json"
        run_history_path = user_dir / "market_run_history.jsonl"
        delivery_history_path = user_dir / "market_delivery_history.jsonl"
        try:
            top_n = int(watch.get("top_n") or 15)
            last_error = None
            reels = []
            for attempt in range(1, 4):
                try:
                    reels = get_top_reels(query, max_items=max(top_n * 3, 30), top_n=top_n)
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt < 3:
                        time.sleep(2 ** attempt)
            if last_error and not reels:
                raise last_error
            previous = load_previous_snapshot(query, base_dir=snapshot_dir)
            current = build_market_snapshot(reels, query)
            changes = compare_snapshots(previous, current)
            alerts = build_market_alerts(
                previous,
                current,
                min_views=int(watch.get("min_views") or get_env("MARKET_ALERT_MIN_VIEWS", "10000")),
            )
            alerts = filter_new_alerts(query, alerts, state_path=alert_state_path)
            path = save_snapshot(current, base_dir=snapshot_dir)
            notified = False
            delivery_status = "disabled" if not watch.get("alerts_enabled", True) else "no_alerts"
            delivery_error = ""
            if watch.get("alerts_enabled", True) and alerts:
                try:
                    notified = send_webhook_alerts(get_env("MARKET_ALERT_WEBHOOK_URL"), query, alerts)
                    delivery_status = "sent" if notified else "webhook_missing"
                    if notified:
                        mark_alerts_sent(query, alerts, state_path=alert_state_path)
                except Exception as exc:
                    delivery_status = "failed"
                    delivery_error = str(exc)
            append_delivery_receipt({
                "query": query,
                "status": delivery_status,
                "alert_count": len(alerts),
                "error": delivery_error,
            }, path=delivery_history_path)
            cloud_saved = False
            if get_env("SUPABASE_URL") and get_env("SUPABASE_ANON_KEY"):
                try:
                    insert_market_snapshot({
                        "query": query,
                        "business_type": watch.get("business_type"),
                        "place": watch.get("place"),
                        "reel_count": current.get("reel_count", 0),
                        "accounts": current.get("accounts", []),
                        "top_hashtags": current.get("top_hashtags", []),
                        "top_tracks": current.get("top_tracks", []),
                        "media": current.get("media", []),
                        "alerts": alerts,
                        "comparison_confidence": changes[0].get("comparison_confidence") if changes else "none",
                    })
                    cloud_saved = True
                except Exception:
                    cloud_saved = False
            summary.append({
                "query": query,
                "snapshot": str(path),
                "accounts": len(current.get("accounts", [])),
                "alerts": len(alerts),
                "notified": notified,
                "cloud_saved": cloud_saved,
                "comparison_confidence": changes[0].get("comparison_confidence") if changes else "none",
            })
            append_market_run(summary[-1], path=run_history_path)
        except Exception as exc:
            failed = True
            summary.append({"query": query, "error": str(exc)})
            append_market_run(summary[-1], path=run_history_path)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
