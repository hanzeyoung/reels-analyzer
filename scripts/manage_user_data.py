from __future__ import annotations

import argparse
import json

from app.core.privacy import delete_user_data, export_user_data, purge_expired_artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description="Export, delete, or purge Reel Lab user data")
    subparsers = parser.add_subparsers(dest="command", required=True)
    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("auth_user_id")
    delete_parser = subparsers.add_parser("delete")
    delete_parser.add_argument("auth_user_id")
    delete_parser.add_argument("--apply", action="store_true")
    purge_parser = subparsers.add_parser("purge")
    purge_parser.add_argument("--days", type=int, default=90)
    purge_parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if args.command == "export":
        print(export_user_data(args.auth_user_id))
    elif args.command == "delete":
        print(json.dumps(delete_user_data(args.auth_user_id, dry_run=not args.apply), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(
            purge_expired_artifacts(["user_reels/uploads", "reports"], args.days, dry_run=not args.apply),
            ensure_ascii=False,
            indent=2,
        ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
