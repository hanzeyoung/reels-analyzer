"""Copy data saved before accounts existed (user_reels/ root) into a member's own space.

Dry run by default; originals are never moved or deleted, and existing files are not overwritten.
    python scripts/adopt_legacy_data.py member@example.com            # preview
    python scripts/adopt_legacy_data.py member@example.com --apply    # copy
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.privacy import user_namespace  # noqa: E402

# Shared infrastructure, not member content.
SKIP_NAMES = {"accounts.json", "oauth_states.json", "api_usage.jsonl", "guests", "exports"}
NAMESPACE_DIR = re.compile(r"^[0-9a-f]{20}$")


def legacy_items(base: Path) -> list[Path]:
    items = []
    for item in sorted(base.iterdir()):
        name = item.name
        if name in SKIP_NAMES or name.startswith("jobs.sqlite3") or name.endswith(".tmp") or name.startswith("."):
            continue
        if item.is_dir() and NAMESPACE_DIR.match(name):
            continue  # another member's space
        items.append(item)
    return items


def adopt(base: Path, email: str, apply: bool) -> list[str]:
    accounts = json.loads((base / "accounts.json").read_text(encoding="utf-8"))
    record = accounts.get(email.strip().lower())
    if not record:
        raise SystemExit(f"가입된 계정을 찾지 못했어요: {email}")
    target = base / user_namespace(record["user_id"])
    lines = []
    for item in legacy_items(base):
        destination = target / item.name
        if destination.exists():
            lines.append(f"건너뜀(이미 있음): {item.name}")
            continue
        lines.append(f"{'복사' if apply else '복사 예정'}: {item.name}")
        if apply:
            target.mkdir(parents=True, exist_ok=True)
            if item.is_dir():
                shutil.copytree(item, destination)
            else:
                shutil.copy2(item, destination)
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("email")
    parser.add_argument("--base", default="user_reels")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    lines = adopt(Path(args.base), args.email, args.apply)
    print("\n".join(lines) or "가져올 기존 데이터가 없어요.")
    if lines and not args.apply:
        print("\n미리보기예요. 실제로 복사하려면 --apply를 붙여 다시 실행하세요.")


if __name__ == "__main__":
    main()
