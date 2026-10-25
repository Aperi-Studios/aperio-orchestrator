"""Generate the owner-facing handoff from actual task, plan, and evidence state."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .store import Project


def _bullets(items: list[str], empty: str = "None recorded.") -> str:
    if not items:
        return f"- {empty}"
    return "\n".join(f"- {item}" for item in items)


def _evidence_summary(evidence: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    if "steps" in evidence:
        for step in evidence["steps"]:
            if step.get("kind") == "run":
                rows.append(
                    f"`{step.get('step_id')}` exit {step.get('exit_code')} in {step.get('duration_s')}s"
                )
            else:
                rows.append(f"`{step.get('step_id')}` wrote `{step.get('path')}`")
    if "checks" in evidence:
        for check in evidence["checks"]:
            rows.append(f"`{check.get('check_id')}` {'passed' if check.get('ok') else 'FAILED'}")
    return rows


def build_handoff(project: Project, task_id: str) -> str:
    task = project.get_task(task_id)
    plan = project.get_plan(task.plan_id) if task.plan_id else None
    evidence = project.evidence(task_id)
    asks = [ask for ask in project.asks() if ask.status == "recorded"]

    lines: list[str] = [
        f"# Handoff: {task.title}",
        "",
        f"**Task:** `{task.id}`  ",
        f"**Status:** `{task.status}`  ",
        f"**Updated:** {task.updated_at}  ",
        f"**Project:** `{project.root}`",
        "",
        "## Requested outcome",
        "",
        task.request.strip() or "No request recorded.",
        "",
    ]
    if asks:
        lines.extend(["## Owner asks on record", "", _bullets([f"`{a.id}` {a.text}" for a in asks[-10:]]), ""])

    if plan:
        lines.extend(
            [
                "## Approved plan",
                "",
                f"**Plan:** `{plan.id}`  ",
                f"**Title:** {plan.title}  ",
                f"**Builder:** {plan.builder}  ",
                f"**Allowed paths:** {', '.join(plan.allowed_paths)}  ",
                f"**Approval:** {plan.approval.approved_by if plan.approval else 'NOT APPROVED'}",
                "",
                "### Steps",
                "",
            ]
        )
        for step in plan.steps:
            if step.kind == "write":
                lines.append(f"- `{step.id}` write `{step.path}`")
            else:
                lines.append(f"- `{step.id}` run `{step.command}` in `{step.cwd}`")
        lines.extend(["", "### Acceptance checks", ""])
        for check in plan.acceptance:
            lines.append(f"- `{check.id}` `{check.command}` expected exit {check.expected_exit}")
        lines.append("")

    lines.extend(["## What changed", ""])
    changes: list[str] = []
    for record in evidence:
        changes.extend(record.get("changed_files", []))
    if changes:
        lines.append(_bullets(sorted(set(changes))))
        if task.status == "rolled_back":
            lines.append("")
            lines.append("These files were changed by the run and then restored by rollback.")
    else:
        lines.append("- No successful changed-file evidence recorded.")
    lines.append("")

    lines.extend(["## Verification", ""])
    verification_rows: list[str] = []
    for record in evidence:
        verification_rows.extend(_evidence_summary(record))
    lines.append(_bullets(verification_rows, "No verification evidence recorded."))
    lines.append("")

    lines.extend(["## Independent review", ""])
    if task.review:
        lines.append(f"- Reviewer: {task.review.reviewer}")
        lines.append(f"- Verdict: **{task.review.verdict}**")
        lines.append(f"- Notes: {task.review.notes or 'None'}")
    else:
        lines.append("- No independent review recorded.")
    lines.append("")

    lines.extend(
        [
            "## Known limits",
            "",
            "- Shell steps are not OS-sandboxed. The runner detects changes outside declared writes, but detection happens after the command.",
            "- Verification runs the commands in the approved plan. It does not prove behavior the plan did not check.",
            "- This handoff is generated from local evidence. A remote deployment is not implied.",
            "",
            "## Owner action required",
            "",
            "- Review the evidence and decide whether the delivered behavior matches the request.",
            "",
            "## Next action",
            "",
        ]
    )
    if task.status == "done":
        lines.append("- No further task action. Keep the evidence with the delivered project.")
    elif task.status == "reviewed":
        lines.append("- Run `aperio done` after confirming the review, or record a refutation.")
    elif task.status == "verified":
        lines.append("- Obtain an independent review before calling this done.")
    elif task.status == "applied":
        lines.append("- Run the acceptance checks and obtain an independent review.")
    else:
        lines.append("- Resolve the failed or blocked step, then rerun the plan.")
    lines.append("")
    return "\n".join(lines)


def write_handoff(project: Project, task_id: str) -> Path:
    text = build_handoff(project, task_id)
    path = project.state / "handoff.md"
    path.write_text(text, encoding="utf-8")
    project.append_event("handoff.written", {"task_id": task_id, "path": str(path)})
    return path
