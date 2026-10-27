"""Gate explanations: the why behind each refusal, with live project status.

``explain`` is teaching, not enforcement: it never gates, never writes, and
never performs the action it describes. Each topic states what the gate
checks, the incident that motivated it, and — when a project is open — the
gate's current status.
"""

from __future__ import annotations

from typing import Any

from .discovery import DiscoveryError
from .discovery import status as discovery_status
from .learning import status as learning_status
from .readiness import ReadinessError
from .readiness import status as readiness_status
from .store import Project
from .todo import status as todo_status

TOPICS = ("discovery", "learning", "todo", "readiness", "approval", "writes", "review")


def _project_line(status_text: str) -> str:
    return f"\n  This project now: {status_text}"


def _discovery(project: Project | None) -> str:
    text = (
        "WHAT IT CHECKS\n"
        "  `plan` refuses while discovery questions are unanswered. Answers are\n"
        "  recorded on the owner's behalf, evidence is referenced, and only an\n"
        "  explicit dated owner waiver can skip a question.\n"
        "WHY IT EXISTS\n"
        "  Plans built on guesses get reworked after approval. The interview is\n"
        "  cheap; rework is not. Waivers exist because some questions genuinely\n"
        "  do not apply — but a waiver is an owner decision with a review date,\n"
        "  not an agent shortcut.\n"
        "COMMANDS\n"
        "  aperio discover next --json     the next question and its choices\n"
        "  aperio discover answer <id> ... record the owner's answer\n"
        "  aperio discover waive <id> ...  explicit dated owner waiver\n"
        "  aperio discover status          coverage overview"
    )
    if project is not None:
        try:
            progress = discovery_status(project)
            text += _project_line(
                f"{progress['answered']}/{progress['total']} answered, "
                f"ready={progress['ready']}"
                + (f", next={progress['next']}" if not progress["ready"] and progress.get("next") else "")
            )
        except DiscoveryError as exc:
            text += _project_line(f"unreadable ({exc})")
    return text


def _learning(project: Project | None) -> str:
    text = (
        "WHAT IT CHECKS\n"
        "  `plan`, `approve`, and `run` refuse while the learning dossier is\n"
        "  missing or unproven. The dossier records the stack, official sources,\n"
        "  skill/MCP gaps, a teach-back, and a competency verdict.\n"
        "WHY IT EXISTS\n"
        "  Imported proof text is ignored by design: a dossier that claims a\n"
        "  proof is not evidence. Only `aperio learn proof` running a real local\n"
        "  command makes the dossier ready. A human must still judge source\n"
        "  quality — the gate validates structure, not truth.\n"
        "COMMANDS\n"
        "  aperio learn import <dossier.json>   import and validate the dossier\n"
        "  aperio learn proof --command ...     run and record a local proof\n"
        "  aperio learn status                  readiness and issues"
    )
    if project is not None:
        progress = learning_status(project)
        text += _project_line(
            f"ready={progress['ready']}"
            + (f", digest={progress['digest'][:12]}…" if progress.get("digest") else ", no dossier")
        )
    return text


def _todo(project: Project | None) -> str:
    text = (
        "WHAT IT CHECKS\n"
        "  `plan` refuses when the ledger is empty or when the in-progress count\n"
        "  is not exactly one. `run` revalidates that the plan's LINKED todo is\n"
        "  in progress or accepted. A task cannot start until every earlier\n"
        "  ledger task is accepted or deferred.\n"
        "WHY IT EXISTS\n"
        "  One slice at a time keeps review and rollback meaningful: a review\n"
        "  covers one deliverable, a rollback restores one slice, and the todo\n"
        "  approval records who accepted the work and on what evidence.\n"
        "COMMANDS\n"
        "  aperio todo add <title> --deliverable ... --acceptance ...\n"
        "  aperio todo start <id>\n"
        "  aperio todo accept <id> --by ... --evidence ... --confirm 'I accept this task'\n"
        "  aperio todo defer <id> --by ... --reason ...\n"
        "  aperio todo list"
    )
    if project is not None:
        progress = todo_status(project)
        text += _project_line(
            f"{progress['count']} tasks, {progress['pending']} pending, "
            f"{progress['in_progress']} in progress, {progress['accepted']} accepted"
        )
    return text


def _readiness(project: Project | None) -> str:
    text = (
        "WHAT IT CHECKS\n"
        "  `plan` requires the preflight section (audience, success measure,\n"
        "  features, constraints, review owner, approval path). `done` and\n"
        "  `handoff` require the FULL record: deploy, after-sales, design, and\n"
        "  security sections. High/critical unresolved security risk blocks full\n"
        "  readiness.\n"
        "WHY IT EXISTS\n"
        "  Deployment facts and the threat model are owner decisions, not agent\n"
        "  guesses. The split matters: preflight is enough to start work; the\n"
        "  full record is enough to claim the project is ready for the world.\n"
        "  The plan pins the record's digest — editing readiness after planning\n"
        "  invalidates the plan.\n"
        "COMMANDS\n"
        "  aperio readiness import <readiness.json>\n"
        "  aperio readiness status"
    )
    if project is not None:
        try:
            progress = readiness_status(project)
            text += _project_line(f"ready={progress['ready']}, issues={len(progress['issues'])}")
        except ReadinessError as exc:
            text += _project_line(f"unreadable ({exc})")
    return text


def _approval(project: Project | None) -> str:
    text = (
        "WHAT IT CHECKS\n"
        "  `approve` requires the exact phrase --confirm \"I approve this plan\"\n"
        "  and records a SHA-256 of the plan body. `run` refuses when the plan\n"
        "  body changed after approval, and the approver cannot also be the run\n"
        "  actor.\n"
        "WHY IT EXISTS\n"
        "  The phrase is a deliberate speed bump: approving is an owner decision\n"
        "  that should never happen by accident or by an agent's convenience.\n"
        "  The hash binding makes the approval mean the plan as written — any\n"
        "  later edit invalidates it. Self-approval was incident F1\n"
        "  (docs/AUDIT-CLAUDE-20261026.md).\n"
        "COMMANDS\n"
        "  aperio approve <plan-id> --by <owner> --confirm \"I approve this plan\"\n"
        "  aperio plan <plan.json>          create or replace the plan first"
    )
    if project is not None:
        approved = [p for p in project.plans() if p.approval is not None]
        text += _project_line(f"{len(approved)} approved plan(s) of {len(project.plans())}")
    return text


def _writes(project: Project | None) -> str:
    text = (
        "WHAT IT CHECKS\n"
        "  Every step declares the paths it may change. The runner snapshots\n"
        "  declared targets before the run, diffs the whole tree after, and\n"
        "  fails the run on any change outside the declaration. `.git` and\n"
        "  `.aperio` are protected and cannot be un-protected by project policy.\n"
        "  A `read` step must not change anything.\n"
        "WHY IT EXISTS\n"
        "  Undeclared writes are how agents break neighboring code. The fence\n"
        "  (allowed_paths) bounds the plan; the doors (step writes) bound each\n"
        "  step. Glob writes match one segment per `*` — `out/*.html` does not\n"
        "  reach `out/sub/x.html` (Z-D6). Shell steps without an OS sandbox are\n"
        "  DETECTED after the fact, not prevented: set `sandbox: true` when the\n"
        "  plan should run inside sandbox-exec/bwrap.\n"
        "COMMANDS\n"
        "  aperio plan <plan.json>          declare paths and steps in the plan\n"
        "  aperio rollback <task-id> --yes  restore the pre-run snapshot"
    )
    if project is not None:
        text += _project_line(
            "sandbox available: "
            + str(__import__("aperio.sandbox", fromlist=["kind"]).kind() or "none")
        )
    return text


def _review(project: Project | None) -> str:
    text = (
        "WHAT IT CHECKS\n"
        "  `review` refuses the builder as reviewer, accepts only confirmed or\n"
        "  refuted, and requires the current verification to have passed with the\n"
        "  project unchanged. `done` refuses without matching review evidence.\n"
        "  Host review goes further: a separate process, a brief-only workspace,\n"
        "  no builder conversation, and a project fingerprint check around the\n"
        "  review.\n"
        "WHY IT EXISTS\n"
        "  Self-approval was incident F1. The reviewer's job is to refute the\n"
        "  work; confirmation is earned when refutation attempts fail. Findings\n"
        "  need evidence and a location — the audit ledger enforces that shape.\n"
        "COMMANDS\n"
        "  aperio review <task-id> --host claude            fresh-context host review\n"
        "  aperio review <task-id> --reviewer <name> ...    manual independent review\n"
        "  aperio mediate <task-id>                         record the disposition"
    )
    if project is not None:
        tasks = project.tasks()
        reviewed = [t for t in tasks if t.review is not None]
        text += _project_line(f"{len(reviewed)} reviewed task(s) of {len(tasks)}")
    return text


_EXPLAINERS = {
    "discovery": _discovery,
    "learning": _learning,
    "todo": _todo,
    "readiness": _readiness,
    "approval": _approval,
    "writes": _writes,
    "review": _review,
}


def explain(topic: str, project: Project | None = None) -> dict[str, Any]:
    """The explanation payload for one topic, with live status when project given."""
    key = topic.strip().lower()
    if key not in _EXPLAINERS:
        raise KeyError(f"unknown topic: {topic} (topics: {', '.join(TOPICS)})")
    return {"topic": key, "text": _EXPLAINERS[key](project), "read_only": True}
