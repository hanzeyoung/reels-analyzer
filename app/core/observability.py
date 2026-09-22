from __future__ import annotations

import json
import logging
import re
import time
from contextlib import contextmanager
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Iterator

from app.core.config import get_env


LOG_PATH = Path("logs") / "reel_lab.jsonl"
USAGE_PATH = Path("user_reels") / "api_usage.jsonl"
SENSITIVE_KEY = re.compile(r"token|secret|password|authorization|api[_-]?key", re.IGNORECASE)


def init_error_tracking(service: str = "reel-lab") -> bool:
    dsn = get_env("SENTRY_DSN")
    if not dsn:
        return False
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=dsn,
            environment=get_env("APP_ENV", "development"),
            release=get_env("APP_RELEASE") or None,
            send_default_pii=False,
            traces_sample_rate=float(get_env("SENTRY_TRACES_SAMPLE_RATE", "0.05")),
        )
        sentry_sdk.set_tag("service", service)
        return True
    except (ImportError, ValueError):
        return False


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "[REDACTED]" if SENSITIVE_KEY.search(str(key)) else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        value = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._-]+", r"\1[REDACTED]", value)
        value = re.sub(r"(?i)(access_token=)[^&\s]+", r"\1[REDACTED]", value)
    return value


def get_logger(name: str = "reel_lab", path: Path = LOG_PATH) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(path, maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def log_event(event: str, **fields: Any) -> None:
    payload = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "event": event,
        **redact(fields),
    }
    get_logger().info(json.dumps(payload, ensure_ascii=False, default=str))


@contextmanager
def observed_operation(name: str, **fields: Any) -> Iterator[None]:
    started = time.perf_counter()
    log_event(f"{name}.started", **fields)
    try:
        yield
    except Exception as exc:
        log_event(f"{name}.failed", duration_ms=round((time.perf_counter() - started) * 1000), error=str(exc), **fields)
        raise
    else:
        log_event(f"{name}.completed", duration_ms=round((time.perf_counter() - started) * 1000), **fields)


def record_api_usage(
    service: str,
    units: float = 1,
    estimated_cost_usd: float = 0,
    metadata: dict | None = None,
    path: Path = USAGE_PATH,
) -> dict:
    record = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "service": service,
        "units": float(units),
        "estimated_cost_usd": float(estimated_cost_usd),
        "metadata": redact(metadata or {}),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def get_daily_usage(service: str, path: Path = USAGE_PATH) -> dict:
    today = datetime.now().astimezone().date()
    units = 0.0
    cost = 0.0
    calls = 0
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
                timestamp = datetime.fromisoformat(item["timestamp"])
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
            if item.get("service") == service and timestamp.date() == today:
                calls += 1
                units += float(item.get("units") or 0)
                cost += float(item.get("estimated_cost_usd") or 0)
    return {"service": service, "calls": calls, "units": round(units, 4), "estimated_cost_usd": round(cost, 6)}


def enforce_daily_limit(
    service: str,
    max_calls: int = 0,
    max_cost_usd: float = 0,
    path: Path = USAGE_PATH,
) -> dict:
    usage = get_daily_usage(service, path)
    if max_calls and usage["calls"] >= max_calls:
        raise RuntimeError(f"{service} 일일 호출 한도 {max_calls}회에 도달했습니다.")
    if max_cost_usd and usage["estimated_cost_usd"] >= max_cost_usd:
        raise RuntimeError(f"{service} 일일 비용 한도 ${max_cost_usd:.2f}에 도달했습니다.")
    return usage


def load_recent_events(limit: int = 50, path: Path = LOG_PATH, failures_only: bool = False) -> list[dict]:
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict):
            continue
        if failures_only and not str(item.get("event", "")).endswith(".failed"):
            continue
        events.append(item)
    return events[-max(1, limit):][::-1]
