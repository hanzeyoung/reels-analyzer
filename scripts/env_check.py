from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from app.core.config import get_env
except Exception as exc:
    print(f"[FAIL] config import failed: {exc}")
    raise SystemExit(1)


REQUIRED_ENV = [
    "APIFY_TOKEN",
    "GEMINI_API_KEY",
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
]

OPTIONAL_ENV = [
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_MODEL",
    "GEMINI_MODEL",
    "META_ACCESS_TOKEN",
]

IMPORTS = [
    "requests",
    "dotenv",
    "pandas",
    "numpy",
    "plotly",
    "streamlit",
    "google.generativeai",
    "PIL",
    "imagehash",
    "httpx",
    "supabase",
    "anthropic",
    "openai",
    "cv2",
]


def status(label: str, ok: bool, detail: str = "") -> None:
    marker = "OK" if ok else "FAIL"
    suffix = f" - {detail}" if detail else ""
    print(f"[{marker}] {label}{suffix}")


def check_env() -> bool:
    print("== Environment variables ==")
    ok = True
    for name in REQUIRED_ENV:
        present = bool(get_env(name))
        status(name, present, "present" if present else "missing")
        ok = ok and present
    for name in OPTIONAL_ENV:
        present = bool(get_env(name))
        status(name, True, "present" if present else "not set")
    return ok


def check_imports() -> bool:
    print("\n== Python imports ==")
    ok = True
    for module_name in IMPORTS:
        try:
            module = importlib.import_module(module_name)
            version = getattr(module, "__version__", "")
            status(module_name, True, version)
        except Exception as exc:
            status(module_name, False, str(exc).splitlines()[0])
            ok = False
    return ok


def check_paths() -> bool:
    print("\n== Project paths ==")
    checks = {
        "root": ROOT.exists(),
        "main.py": (ROOT / "main.py").exists(),
        "reports": (ROOT / "reports").exists(),
        "videos_verify_keyword_final": (ROOT / "videos_verify_keyword_final").exists(),
        "nested duplicate project": (ROOT / "reels-analyzer").exists(),
    }
    for label, exists in checks.items():
        if label == "nested duplicate project":
            detail = "exists; archive after confirming obsolete" if exists else "not found"
            status(label, True, detail)
        else:
            status(label, exists)
    return all(value for key, value in checks.items() if key != "nested duplicate project")


def main() -> int:
    print(f"Python: {sys.version.split()[0]} ({sys.executable})")
    print(f"Project: {ROOT}")
    print(f"PYTHONPATH: {os.getenv('PYTHONPATH', '')}")

    results = [check_env(), check_imports(), check_paths()]
    print("\nResult:", "OK" if all(results) else "NEEDS ATTENTION")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
