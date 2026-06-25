"""프로젝트 저장·열기·자동저장."""
from __future__ import annotations
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from core.models import ProjectData

PROJECTS_DIR = Path(__file__).parent.parent / "projects"
PROJECTS_DIR.mkdir(exist_ok=True)


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def save_project(project: ProjectData, path: Optional[Path] = None) -> Path:
    if path is None:
        safe = "".join(c if c.isalnum() or c in "_- " else "_" for c in project.project_name)
        path = PROJECTS_DIR / f"{safe}.json"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(project.to_dict(), f, ensure_ascii=False, indent=2)
    return path


def load_project(path: Path | str) -> ProjectData:
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
    return ProjectData.from_dict(d)


def list_projects() -> List[Path]:
    return sorted(PROJECTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)


def autosave(project: ProjectData, autosave_dir: Optional[Path] = None) -> Path:
    ad = autosave_dir or (PROJECTS_DIR / "_autosave")
    ad.mkdir(exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "_- " else "_" for c in project.project_name)
    p = ad / f"{safe}_autosave.json"
    save_project(project, p)
    return p


def backup_project(path: Path) -> Path:
    bp = path.parent / "_backups" / f"{path.stem}_{_ts()}.json"
    bp.parent.mkdir(exist_ok=True)
    shutil.copy(str(path), str(bp))
    return bp
