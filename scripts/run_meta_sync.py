from __future__ import annotations

import json
from pathlib import Path

from app.core.config import get_env
from app.core.meta_sync import run_meta_sync
from app.core.observability import init_error_tracking
from app.core.token_vault import load_encrypted_token


def main() -> int:
    init_error_tracking("meta-sync")
    limit = int(get_env("META_SYNC_LIMIT", "30") or 30)
    jobs = []
    environment_token = get_env("META_ACCESS_TOKEN")
    if environment_token:
        jobs.append({
            "token": environment_token,
            "business_type": get_env("META_SYNC_BUSINESS_TYPE", "카페"),
            "auth_user_id": "",
            "user_dir": Path("user_reels"),
        })

    encryption_key = get_env("META_TOKEN_ENCRYPTION_KEY")
    if encryption_key:
        for token_path in sorted(Path("user_reels").glob("*/meta_token.enc")):
            stored = load_encrypted_token(encryption_key, token_path)
            if not stored:
                continue
            metadata = stored.get("metadata") or {}
            jobs.append({
                "token": stored["token"],
                "business_type": metadata.get("business_type") or "카페",
                "auth_user_id": metadata.get("auth_user_id") or "",
                "user_dir": token_path.parent,
            })

    if not jobs:
        print("No Meta token configured for scheduled synchronization.")
        return 0

    results = []
    failed = False
    for job in jobs:
        user_dir = job["user_dir"]
        try:
            results.append(run_meta_sync(
                access_token=job["token"],
                business_type=job["business_type"],
                limit=limit,
                auth_user_id=job["auth_user_id"],
                library_path=user_dir / "library.jsonl",
                store_profile_path=user_dir / "store_profile.json",
                performance_history_path=user_dir / "performance_history.jsonl",
                use_service_role=bool(job["auth_user_id"] and get_env("SUPABASE_SERVICE_ROLE_KEY")),
            ))
        except Exception as exc:
            failed = True
            results.append({"user_dir": str(user_dir), "error": str(exc)})
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
