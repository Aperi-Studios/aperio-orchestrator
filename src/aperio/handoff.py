"""Generate the owner-facing handoff from actual task, plan, and evidence state."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .audit import AuditError
from .audit import latest as latest_audit
from .evidence import EvidenceError
from .evidence import entries as evidence_entries
from .repo import facts as repo_facts
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
            elif step.get("kind") == "host":
                rows.append(
                    f"`{step.get('step_id')}` host {step.get('host')} exit {step.get('exit_code')} "
                    f"changed {len(step.get('changes', []))} file(s)"
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
    repository = repo_facts(project)
    if repository:
        changed = f" ({repository['changed']} changed)" if repository["dirty"] else ""
        lines[7:7] = [
            "## Repository",
            "",
            f"**Branch:** `{repository['branch']}`  ",
            f"**Commit:** `{repository['head']}`  ",
            f"**Working tree:** {'dirty' if repository['dirty'] else 'clean'}{changed}  ",
            "",
        ]
    if asks:
        lines.extend(["## Owner asks on record", "", _bullets([f"`{a.id}` {a.text}" for a in asks[-10:]]), ""])

    discovery = project.discovery() or {}
    waivers = discovery.get("waivers") if isinstance(discovery, dict) else {}
    if isinstance(waivers, dict) and waivers:
        waiver_rows = [
            f"`{question_id}` — {item.get('risk', 'no risk stated')} "
            f"(accepted by {item.get('by', 'unknown')}, review by {item.get('review_at', 'not set')})"
            for question_id, item in sorted(waivers.items())
            if isinstance(item, dict)
        ]
        lines.extend(["## Discovery waivers", "", _bullets(waiver_rows), ""])

    try:
        manifest = evidence_entries(project)
    except EvidenceError:
        manifest = {"entries": []}
    manifest_rows = [
        f"`{item.get('id', '?')}` {item.get('label', '')} — `{item.get('path', '')}` "
        f"sha256 `{str(item.get('sha256', ''))[:16]}`"
        for item in manifest.get("entries", [])
        if isinstance(item, dict)
    ]
    if manifest_rows:
        lines.extend(["## Evidence files", "", _bullets(manifest_rows), ""])

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
        if plan.discovery_digest:
            lines.extend([f"**Discovery digest:** `{plan.discovery_digest[:16]}`", ""])
        for step in plan.steps:
            if step.kind == "write":
                lines.append(f"- `{step.id}` write `{step.path}`")
            elif step.kind == "host":
                lines.append(f"- `{step.id}` host `{step.host}` writes: {', '.join(step.writes)}")
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

    try:
        audit = latest_audit(project)
    except AuditError as exc:
        audit = {"invalid": str(exc)}
    lines.extend(["## Security audit", ""])
    if audit is None:
        lines.append("- No source audit recorded.")
    elif "invalid" in audit:
        lines.append(f"- **INVALID:** {audit['invalid']}")
    else:
        lines.append(f"- Audit: `{audit.get('audit_id', '')}`")
        lines.append(f"- Status: **{audit.get('run_status', 'unknown')}**")
        lines.append(f"- Coverage: {audit.get('checked', 0)}/{audit.get('units', 0)} checked")
        lines.append(
            f"- Findings: {audit.get('confirmed', 0)} confirmed, "
            f"{audit.get('needs_validation', 0)} needs validation, "
            f"{audit.get('rejected', 0)} rejected"
        )
        if audit.get("source_changed"):
            lines.append("- Source changed since the audit started.")
        if audit.get("truncated"):
            lines.append("- Coverage was truncated.")
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
