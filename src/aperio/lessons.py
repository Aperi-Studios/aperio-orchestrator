"""The lessons ledger: what this project learned, surfaced before it matters.

A lesson is a recorded "what went wrong and what to do differently", bound
optionally to the task that taught it and to the paths it concerns. The
compounding mechanism is surfacing: `relevant_lessons` matches a plan's
allowed paths against lesson paths, so a plan touching files named by an
earlier lesson sees that lesson at plan time — lesson #50 does not depend on
an agent reading the whole history.

Teach, never automate: lessons inform gates and the advisor; they never
block, and nothing here touches the approval phrase.
"""

from __future__ import annotations

import json
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

from .model import ModelError, utc_now
from .paths import replace_text_atomic
from .store import Project

SCHEMA_VERSION = 1
LESSONS_NAME = "lessons.json"
MAX_LESSONS = 500
MAX_TEXT = 2000


class LessonsError(ModelError):
    """The lessons ledger is missing, malformed, or the entry is invalid."""


def _path(project: Project) -> Path:
    return project.state / LESSONS_NAME


def read_lessons(project: Project) -> dict[str, Any]:
    path = _path(project)
    if not path.is_file():
        return {"schema": SCHEMA_VERSION, "lessons": [], "updated_at": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LessonsError(f"lessons ledger is unreadable: {exc}") from exc
    if not isinstance(data, dict):
        raise LessonsError("lessons ledger must be a JSON object")
    schema = data.get("schema")
    if schema is None:
        data["schema"] = SCHEMA_VERSION
    elif schema != SCHEMA_VERSION:
        raise LessonsError(
            f"unsupported lessons schema {schema}; this build supports {SCHEMA_VERSION}"
        )
    if not isinstance(data.get("lessons"), list):
        raise LessonsError("lessons ledger must carry a lessons list")
    return data


def add(
    project: Project,
    text: str,
    *,
    task_id: str = "",
    paths: list[str] | None = None,
    source: str = "manual",
) -> dict[str, Any]:
    """Record a lesson. Explicit, owner- or agent-initiated; never automatic."""
    text = text.strip()
    if not text:
        raise LessonsError("lesson text must not be empty")
    if len(text) > MAX_TEXT:
        raise LessonsError(f"lesson text is longer than {MAX_TEXT} characters")
    clean_paths: list[str] = []
    for item in paths or []:
        item = item.strip()
        if not item:
            continue
        if any(ch in item for ch in "*?[") or item.startswith("/") or ".." in item.split("/"):
            raise LessonsError(f"lesson path must be a plain project-relative path: {item}")
        clean_paths.append(item)
    data = read_lessons(project)
    lessons = data["lessons"]
    if len(lessons) >= MAX_LESSONS:
        raise LessonsError(f"lessons ledger is full ({MAX_LESSONS}); prune it first")
    entry = {
        "id": f"lesson-{len(lessons) + 1:04d}",
        "text": text,
        "task_id": task_id.strip(),
        "paths": clean_paths,
        "source": source,
        "created_at": utc_now(),
    }
    lessons.append(entry)
    data["updated_at"] = utc_now()
    replace_text_atomic(
        _path(project), json.dumps(data, indent=2, sort_keys=True) + "\n"
    )
    project.append_event(
        "lesson.added", {"lesson_id": entry["id"], "task_id": entry["task_id"]}
    )
    return entry


def remove(project: Project, lesson_id: str) -> dict[str, Any]:
    data = read_lessons(project)
    kept = [item for item in data["lessons"] if item.get("id") != lesson_id]
    if len(kept) == len(data["lessons"]):
        raise LessonsError(f"unknown lesson: {lesson_id}")
    data["lessons"] = kept
    data["updated_at"] = utc_now()
    replace_text_atomic(
        _path(project), json.dumps(data, indent=2, sort_keys=True) + "\n"
    )
    project.append_event("lesson.removed", {"lesson_id": lesson_id})
    return {"removed": lesson_id, "remaining": len(kept)}


def _path_matches(allowed: str, lesson_path: str) -> bool:
    """A lesson matches when its path equals, prefixes, or globs an allowed path."""
    if lesson_path == allowed:
        return True
    if allowed.startswith(lesson_path.rstrip("/") + "/"):
        return True
    if lesson_path.startswith(allowed.rstrip("/") + "/"):
        return True
    if any(ch in lesson_path for ch in "*?"):
        return fnmatchcase(allowed, lesson_path)
    return False


def relevant_lessons(project: Project, allowed_paths: list[str]) -> list[dict[str, Any]]:
    """Lessons whose paths intersect the plan's allowed paths, most recent last."""
    data = read_lessons(project)
    matches: list[dict[str, Any]] = []
    for lesson in data["lessons"]:
        lesson_paths = lesson.get("paths", [])
        if not lesson_paths:
            continue
        if any(
            _path_matches(allowed, lesson_path)
            for allowed in allowed_paths
            for lesson_path in lesson_paths
        ):
            matches.append(lesson)
    return matches


def format_list(data: dict[str, Any]) -> str:
    lessons = data["lessons"]
    if not lessons:
        return "Lessons: none recorded. Record one with `aperio lesson add \"<what went wrong>\" --paths <paths>`."
    lines = [f"Lessons: {len(lessons)} recorded"]
    for item in lessons:
        lines.append(f"{item['id']}  {item['text']}")
        if item.get("task_id"):
            lines.append(f"    task: {item['task_id']}")
        if item.get("paths"):
            lines.append(f"    paths: {', '.join(item['paths'])}")
    return "\n".join(lines)
