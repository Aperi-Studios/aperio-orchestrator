"""Owner-visible todo list with one-task-at-a-time approval.

A task is not a time box. It is the smallest independently reviewable unit of
work derived from the owner's request. The next task cannot start until the
current one is accepted and explicitly approved.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .model import ModelError, new_id, utc_now
from .paths import replace_text_atomic
from .store import Project

SCHEMA_VERSION = 1
TODO_NAME = "todo.json"
STATUSES = {"pending", "in_progress", "accepted", "deferred"}


class TodoError(ModelError):
    """The todo list is missing, malformed, or the transition is not allowed."""


def _path(project: Project) -> Path:
    return project.state / TODO_NAME


def _read(project: Project) -> dict[str, Any]:
    path = _path(project)
    if not path.is_file():
        return {"schema": SCHEMA_VERSION, "tasks": [], "updated_at": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TodoError(f"todo list is unreadable: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
        raise TodoError("todo list is malformed")
    if data.get("schema") != SCHEMA_VERSION:
        raise TodoError("todo list has an unsupported schema")
    for task in data["tasks"]:
        if not isinstance(task, dict) or not isinstance(task.get("status"), str):
            raise TodoError("todo list contains a malformed task")
        if task["status"] not in STATUSES:
            raise TodoError(f"todo list contains an unknown status: {task['status']}")
    return data


def _write(project: Project, data: dict[str, Any]) -> None:
    data["schema"] = SCHEMA_VERSION
    data["updated_at"] = utc_now()
    _path(project).parent.mkdir(parents=True, exist_ok=True)
    replace_text_atomic(_path(project), json.dumps(data, indent=2, sort_keys=True) + "\n")


def _task(data: dict[str, Any], task_id: str) -> dict[str, Any]:
    for task in data["tasks"]:
        if task.get("id") == task_id:
            return task
    raise TodoError(f"unknown todo task: {task_id}")


def _order(data: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(data["tasks"], key=lambda item: (item.get("position", 0), item.get("created_at", "")))


def add(
    project: Project,
    title: str,
    *,
    deliverable: str = "",
    acceptance: str = "",
) -> dict[str, Any]:
    title = title.strip()
    deliverable = deliverable.strip()
    acceptance = acceptance.strip()
    if not title:
        raise TodoError("todo task title is required")
    if not deliverable:
        raise TodoError("todo task deliverable is required")
    if not acceptance:
        raise TodoError("todo task acceptance is required")
    with project.lock():
        data = _read(project)
        task = {
            "id": new_id("todo"),
            "title": title,
            "deliverable": deliverable,
            "acceptance": acceptance,
            "status": "pending",
            "position": len(data["tasks"]),
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "approval": None,
        }
        data["tasks"].append(task)
        _write(project, data)
        project.append_event("todo.added", {"task_id": task["id"]})
    return task


def tasks(project: Project) -> dict[str, Any]:
    return _read(project)


def start(project: Project, task_id: str) -> dict[str, Any]:
    with project.lock():
        data = _read(project)
        task = _task(data, task_id)
        if task["status"] != "pending":
            raise TodoError(f"todo task is {task['status']}; only a pending task can start")
        ordered = _order(data)
        for previous in ordered:
            if previous["id"] == task_id:
                break
            if previous["status"] not in {"accepted", "deferred"}:
                raise TodoError(
                    f"previous todo task {previous['id']} is {previous['status']}; accept or defer it first"
                )
        active = [item for item in data["tasks"] if item["status"] == "in_progress"]
        if active:
            raise TodoError(f"todo task {active[0]['id']} is already in progress")
        task["status"] = "in_progress"
        task["updated_at"] = utc_now()
        _write(project, data)
        project.append_event("todo.started", {"task_id": task_id})
    return task


def accept(
    project: Project,
    task_id: str,
    *,
    by: str,
    evidence: str,
    confirm: str,
) -> dict[str, Any]:
    if confirm != "I accept this task":
        raise TodoError('accepting a task requires --confirm "I accept this task"')
    if not by.strip():
        raise TodoError("accepting a task requires an approver")
    if not evidence.strip():
        raise TodoError("accepting a task requires evidence")
    with project.lock():
        data = _read(project)
        task = _task(data, task_id)
        if task["status"] != "in_progress":
            raise TodoError(f"todo task is {task['status']}; only an in-progress task can be accepted")
        task["status"] = "accepted"
        task["updated_at"] = utc_now()
        task["approval"] = {
            "approved_by": by.strip(),
            "approved_at": utc_now(),
            "note": confirm,
        }
        task["evidence"] = evidence.strip()
        _write(project, data)
        project.append_event(
            "todo.accepted",
            {"task_id": task_id, "by": by.strip(), "evidence": evidence.strip()},
        )
    return task


def defer(project: Project, task_id: str, *, by: str, reason: str) -> dict[str, Any]:
    if not by.strip() or not reason.strip():
        raise TodoError("deferring a task requires an approver and a reason")
    with project.lock():
        data = _read(project)
        task = _task(data, task_id)
        if task["status"] not in {"pending", "in_progress"}:
            raise TodoError(f"todo task is {task['status']}; only pending or in-progress work can be deferred")
        task["status"] = "deferred"
        task["updated_at"] = utc_now()
        task["approval"] = {"approved_by": by.strip(), "approved_at": utc_now(), "note": reason.strip()}
        _write(project, data)
        project.append_event("todo.deferred", {"task_id": task_id, "by": by.strip()})
    return task


def status(project: Project) -> dict[str, Any]:
    data = _read(project)
    ordered = _order(data)
    return {
        "schema": SCHEMA_VERSION,
        "count": len(ordered),
        "pending": sum(1 for item in ordered if item["status"] == "pending"),
        "in_progress": sum(1 for item in ordered if item["status"] == "in_progress"),
        "accepted": sum(1 for item in ordered if item["status"] == "accepted"),
        "deferred": sum(1 for item in ordered if item["status"] == "deferred"),
        "tasks": ordered,
    }


def format_status(data: dict[str, Any]) -> str:
    if not data["tasks"]:
        return "Todo: empty. Add the first independently reviewable task."
    lines = [
        (
            f"Todo: {data['count']} tasks · {data['pending']} pending · "
            f"{data['in_progress']} in progress · {data['accepted']} accepted · {data['deferred']} deferred"
        )
    ]
    for item in data["tasks"]:
        lines.append(
            f"{item['id']}  {item['status']:11}  {item['title']}  "
            f"deliverable={item['deliverable']}"
        )
    return "\n".join(lines)
