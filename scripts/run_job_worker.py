from __future__ import annotations

import argparse
import re
import time
from datetime import datetime
from pathlib import Path

from app.api.gemini import analyze_reel_from_file, analyze_reel_from_url, format_report
from app.core.job_queue import claim_next_job, complete_job, fail_job, is_job_cancelled, update_progress
from app.core.observability import init_error_tracking


def _safe_name(value: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", value)[:64] or "reel"


def process_job(job: dict) -> dict:
    payload = job["payload"]
    update_progress(job["id"], 10)
    if job["kind"] == "video_analysis_file":
        video_path = Path(payload["video_path"])
        if not video_path.exists():
            raise FileNotFoundError(f"Queued video does not exist: {video_path}")
        analysis = analyze_reel_from_file(str(video_path), caption=payload.get("caption", ""))
    elif job["kind"] == "video_analysis_url":
        analysis = analyze_reel_from_url(payload["video_url"], caption=payload.get("caption", ""))
    else:
        raise ValueError(f"Unsupported job kind: {job['kind']}")

    if is_job_cancelled(job["id"]):
        return {}
    update_progress(job["id"], 90)
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    report_path = reports_dir / f"{datetime.now():%Y%m%d_%H%M%S}_{_safe_name(payload.get('title', 'reel'))}_report.md"
    report_path.write_text(format_report(analysis), encoding="utf-8")
    return {"analysis": analysis, "report_path": str(report_path)}


def main() -> int:
    init_error_tracking("analysis-worker")
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Process one available job and exit")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()

    while True:
        job = claim_next_job(kinds=("video_analysis_file", "video_analysis_url"))
        if not job:
            if args.once:
                return 0
            time.sleep(max(0.5, args.poll_seconds))
            continue
        try:
            result = process_job(job)
            if complete_job(job["id"], result):
                print(f"Completed {job['id']}")
            else:
                print(f"Discarded cancelled job {job['id']}")
        except Exception as exc:
            fail_job(job["id"], str(exc))
            print(f"Failed {job['id']}: {exc}")
        if args.once:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
