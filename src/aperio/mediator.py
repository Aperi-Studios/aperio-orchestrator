"""Evidence-based mediator disposition for one task.

The disposition follows the task's current state and its latest evidence, not
the newest filename. Filenames contain random ids, so sorting them is not a
safe proxy for chronology.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .model import utc_now
from .store import Project

EXCLUDED_DIRS = {".git", ".aperio", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache"}


def _artifact_digest(project: Project) -> str:
    entries: list[tuple[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(project.root):
        dirnames[:] = [name for name in dirnames if name not in EXCLUDED_DIRS]
        for name in filenames:
            path = Path(dirpath) / name
            if path.is_symlink():
                entries.append((path.relative_to(project.root).as_posix(), "symlink:" + os.readlink(path)))
                continue
            try:
                entries.append((path.relative_to(project.root).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()))
            except OSError:
                continue
    return hashlib.sha256(json.dumps(sorted(entries), separators=(",", ":")).encode("utf-8")).hexdigest()


class MediationError(RuntimeError):
    """The task does not have enough evidence to mediate."""


def _timestamp(row: dict[str, Any]) -> str:
    return str(row.get("at") or row.get("finished_at") or row.get("started_at") or row.get("created_at") or "")


def _latest(rows: list[dict[str, Any]], key: str, prefix: str = "") -> dict[str, Any] | None:
    found = [row for row in rows if str(row.get(key, "")).startswith(prefix)]
    return max(found, key=_timestamp) if found else None


def mediate(project: Project, task_id: str) -> dict[str, Any]:
    task = project.get_task(task_id)
    if not task.plan_id:
        raise MediationError("task has no plan")
    plan = project.get_plan(task.plan_id)
    evidence = project.evidence(task_id)
    run = None
    if task.run_id:
        run = next((row for row in evidence if row.get("run_id") == task.run_id), None)
    verify = _latest(evidence, "check_id", "verify-")
    review = _latest(evidence, "review_id", "review-")

    if task.status == "failed":
        disposition = "REFUTED"
        reason = "task status is failed"
    elif not task.run_id:
        disposition = "BLOCKED"
        reason = "no run evidence"
    elif run is None:
        disposition = "BLOCKED"
        reason = "current run evidence is missing"
    elif run.get("status") != "applied":
        disposition = "REFUTED"
        reason = f"run status is {run.get('status')}"
    elif task.status not in {"verified", "reviewed", "done"}:
        disposition = "BLOCKED"
        reason = f"task status is {task.status}"
    elif verify is None:
        disposition = "BLOCKED"
        reason = "no verification evidence"
    elif verify.get("check_id") != task.verify_id:
        disposition = "BLOCKED"
        reason = "verification evidence does not match the task"
    elif verify.get("artifact_digest") != _artifact_digest(project):
        disposition = "REFUTED"
        reason = "project changed after verification"
    elif verify.get("status") != "passed":
        disposition = "REFUTED"
        reason = f"verification status is {verify.get('status')}"
    elif task.review is None:
        disposition = "BLOCKED"
        reason = "no independent review"
    elif task.review.verdict == "refuted":
        disposition = "REFUTED"
        reason = "reviewer refuted the delivery"
    elif task.review.verdict != "confirmed":
        disposition = "BLOCKED"
        reason = "review verdict is not recognized"
    elif task.review.reviewer.strip().lower() == plan.builder.strip().lower():
        disposition = "REFUTED"
        reason = "reviewer is the builder"
    elif review is None:
        disposition = "BLOCKED"
        reason = "review evidence is missing"
    elif str(review.get("reviewer", "")).strip().lower() != task.review.reviewer.strip().lower():
        disposition = "BLOCKED"
        reason = "latest review evidence does not match the task review"
    elif str(review.get("verdict", "")).lower() != task.review.verdict:
        disposition = "BLOCKED"
        reason = "latest review verdict does not match the task review"
    else:
        disposition = "CONFIRMED"
        reason = "run applied, verification passed, and an independent reviewer confirmed"

    record = {
        "task_id": task_id,
        "plan_id": plan.id,
        "builder": plan.builder,
        "task_status": task.status,
        "disposition": disposition,
        "reason": reason,
        "run_id": run.get("run_id") if run else None,
        "verify_id": verify.get("check_id") if verify else None,
        "review_id": review.get("review_id") if review else None,
        "reviewer": task.review.reviewer if task.review else None,
        "at": utc_now(),
    }
    directory = project.state / "mediations"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{task_id}-{record['at'].replace(':', '-')}.json"
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    record["evidence_path"] = str(path)
    project.append_event("mediation.recorded", {"task_id": task_id, "disposition": disposition})
    return record
