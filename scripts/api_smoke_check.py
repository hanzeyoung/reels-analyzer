from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import get_env, get_gemini_api_key


def status(label: str, ok: bool, detail: str = "") -> bool:
    marker = "OK" if ok else "FAIL"
    suffix = f" - {detail}" if detail else ""
    print(f"[{marker}] {label}{suffix}")
    return ok


def check_apify() -> bool:
    token = get_env("APIFY_TOKEN")
    if not token:
        return status("Apify", False, "APIFY_TOKEN missing")

    import requests

    response = requests.get(
        "https://api.apify.com/v2/users/me",
        headers={"Authorization": f"Bearer {token}"},
        timeout=20,
    )
    if response.ok:
        data = response.json().get("data", {})
        username = data.get("username") or data.get("id") or "authenticated"
        return status("Apify", True, str(username))
    return status("Apify", False, f"HTTP {response.status_code}")


def check_gemini() -> bool:
    api_key = get_gemini_api_key()
    if not api_key:
        return status("Gemini", False, "GEMINI_API_KEY or GOOGLE_API_KEY missing")

    import google.generativeai as genai

    genai.configure(api_key=api_key)
    models = list(genai.list_models())
    names = [model.name for model in models[:5]]
    return status("Gemini", bool(models), ", ".join(names))


def check_supabase() -> bool:
    url = get_env("SUPABASE_URL")
    key = get_env("SUPABASE_ANON_KEY")
    if not url or not key:
        return status("Supabase", False, "SUPABASE_URL or SUPABASE_ANON_KEY missing")

    from supabase import create_client

    client = create_client(url, key)
    try:
        response = client.table("reels").select("id").limit(1).execute()
    except Exception as exc:
        return status("Supabase", False, str(exc).splitlines()[0])
    return status("Supabase", True, f"reels rows returned: {len(response.data or [])}")


def main() -> int:
    checks = [check_apify(), check_gemini(), check_supabase()]
    print("\nResult:", "OK" if all(checks) else "NEEDS ATTENTION")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
