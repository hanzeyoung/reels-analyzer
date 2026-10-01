from __future__ import annotations

import hashlib
import shutil
import zipfile
from datetime import datetime, timedelta
from pathlib import Path


def user_namespace(auth_user_id: str) -> str:
    return hashlib.sha256(auth_user_id.encode("utf-8")).hexdigest()[:20]


def export_user_data(auth_user_id: str, base_dir: str | Path = "user_reels", output_dir: str | Path = "exports") -> Path:
    source = Path(base_dir) / user_namespace(auth_user_id)
    if not source.exists():
        raise FileNotFoundError("내보낼 사용자 데이터가 없습니다.")
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / f"reels_analyzer_export_{datetime.now():%Y%m%d_%H%M%S}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for item in source.rglob("*"):
            if item.is_file():
                bundle.write(item, item.relative_to(source))
    return archive


def delete_user_data(auth_user_id: str, base_dir: str | Path = "user_reels", dry_run: bool = True) -> list[str]:
    source = (Path(base_dir) / user_namespace(auth_user_id)).resolve()
    base = Path(base_dir).resolve()
    if base not in source.parents:
        raise ValueError("사용자 데이터 경로가 기본 저장소 밖을 가리킵니다.")
    files = [str(item) for item in source.rglob("*") if item.is_file()] if source.exists() else []
    if not dry_run and source.exists():
        shutil.rmtree(source)
    return files


def purge_expired_artifacts(
    roots: list[str | Path],
    retention_days: int = 90,
    dry_run: bool = True,
) -> list[str]:
    cutoff = datetime.now() - timedelta(days=max(1, retention_days))
    expired = []
    for raw_root in roots:
        root = Path(raw_root).resolve()
        if not root.exists():
            continue
        for item in root.rglob("*"):
            if item.is_file() and datetime.fromtimestamp(item.stat().st_mtime) < cutoff:
                expired.append(str(item))
                if not dry_run:
                    item.unlink(missing_ok=True)
    return expired
