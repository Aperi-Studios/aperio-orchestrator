"""Evidence-based mediator disposition for one task."""

from __future__ import annotations

import json
from typing import Any

from .model import utc_now
from .store import Project


class MediationError(RuntimeError):
    """The task does not have enough evidence to mediate."""


def _last(rows: list[dict[str, Any]], key: str, prefix: str = "") -> dict[str, Any] | None:
    found = [row for row in rows if str(row.get(key, "")).startswith(prefix)]
    return found[-1] if found else None


def mediate(project: Project, task_id: str) -> dict[str, Any]:
    task = project.get_task(task_id)
    if not task.plan_id:
        raise MediationError("task has no plan")
    plan = project.get_plan(task.plan_id)
    evidence = project.evidence(task_id)
    run = _last(evidence, "run_id", "run-")
    verify = _last(evidence, "check_id", "verify-")
    review = _last(evidence, "review_id", "review-")

    if run is None:
        disposition = "BLOCKED"
        reason = "no run evidence"
    elif run.get("status") != "applied":
        disposition = "REFUTED"
        reason = f"run status is {run.get('status')}"
    elif verify is None:
        disposition = "BLOCKED"
        reason = "no verification evidence"
    elif verify.get("status") != "passed":
        disposition = "REFUTED"
        reason = f"verification status is {verify.get('status')}"
    elif review is None:
        disposition = "BLOCKED"
        reason = "no independent review evidence"
    elif review.get("verdict") == "refuted":
        disposition = "REFUTED"
        reason = "reviewer refuted the delivery"
    elif review.get("verdict") != "confirmed":
        disposition = "BLOCKED"
        reason = "review verdict is not recognized"
    elif str(review.get("reviewer", "")).strip().lower() == plan.builder.strip().lower():
        disposition = "REFUTED"
        reason = "reviewer is the builder"
    else:
        disposition = "CONFIRMED"
        reason = "run applied, verification passed, and an independent reviewer confirmed"

    record = {
        "task_id": task_id,
        "plan_id": plan.id,
        "builder": plan.builder,
        "disposition": disposition,
        "reason": reason,
        "run_id": run.get("run_id") if run else None,
        "verify_id": verify.get("check_id") if verify else None,
        "review_id": review.get("review_id") if review else None,
        "reviewer": review.get("reviewer") if review else None,
        "at": utc_now(),
    }
    directory = project.state / "mediations"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{task_id}-{record['at'].replace(':', '-')}.json"
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    record["evidence_path"] = str(path)
    project.append_event("mediation.recorded", {"task_id": task_id, "disposition": disposition})
    return record
