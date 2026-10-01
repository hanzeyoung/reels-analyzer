from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path


PROJECT_STAGES = ("idea", "script", "shoot", "review", "posted")
STAGE_LABELS = {
    "idea": "Idea",
    "script": "Script",
    "shoot": "Shoot",
    "review": "Review",
    "posted": "Posted",
}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _read(path: str | Path) -> list[dict]:
    target = Path(path)
    if not target.exists():
        return []
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def _write(projects: list[dict], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(projects, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)


def list_projects(path: str | Path, include_archived: bool = False) -> list[dict]:
    projects = _read(path)
    if not include_archived:
        projects = [item for item in projects if not item.get("archived")]
    return sorted(projects, key=lambda item: item.get("updated_at", ""), reverse=True)


def create_project(
    title: str,
    path: str | Path,
    business_type: str = "",
    concept: str = "",
    source: dict | None = None,
) -> dict:
    now = _now()
    project = {
        "id": str(uuid.uuid4()),
        "title": re.sub(r"\s+", " ", title).strip()[:80] or "Untitled reel",
        "business_type": business_type,
        "stage": "idea",
        "concept": concept.strip(),
        "source": source or {},
        "hook": "",
        "script": "",
        "script_variants": {},
        "shot_list": [],
        "edit_notes": [],
        "audio": {},
        "guide_assets": {},
        "analysis": {},
        "instagram_media_id": "",
        "published_at": "",
        "archived": False,
        "created_at": now,
        "updated_at": now,
    }
    projects = _read(path)
    projects.append(project)
    _write(projects, path)
    return project


def update_project(project_id: str, updates: dict, path: str | Path) -> dict | None:
    projects = _read(path)
    updated = None
    allowed = {
        "title", "business_type", "stage", "concept", "source", "hook", "script",
        "script_variants", "shot_list", "edit_notes", "analysis", "audio", "guide_assets",
        "instagram_media_id", "published_at", "archived",
    }
    for index, project in enumerate(projects):
        if project.get("id") != project_id:
            continue
        clean_updates = {key: value for key, value in updates.items() if key in allowed}
        if clean_updates.get("stage") not in PROJECT_STAGES:
            clean_updates.pop("stage", None)
        updated = {**project, **clean_updates, "updated_at": _now()}
        projects[index] = updated
        break
    if updated:
        _write(projects, path)
    return updated


def delete_project(project_id: str, path: str | Path) -> bool:
    projects = _read(path)
    remaining = [item for item in projects if item.get("id") != project_id]
    if len(remaining) == len(projects):
        return False
    _write(remaining, path)
    return True


def pipeline_counts(projects: list[dict]) -> dict[str, int]:
    return {stage: sum(1 for item in projects if item.get("stage") == stage) for stage in PROJECT_STAGES}


def next_action(project: dict) -> str:
    stage = project.get("stage", "idea")
    if stage == "idea":
        return "훅과 대본을 확정하세요."
    if stage == "script":
        return "촬영 컷과 순서를 준비하세요."
    if stage == "shoot":
        return "촬영본을 올리고 게시 전 분석을 실행하세요."
    if stage == "review":
        return "수정안을 반영하고 게시 준비를 마치세요."
    return "게시 후 실측 성과를 연결하세요."
