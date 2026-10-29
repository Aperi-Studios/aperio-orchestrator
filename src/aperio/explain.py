"""Gate explanations: the why behind each refusal, with live project status.

``explain`` is teaching, not enforcement: it never gates, never writes, and
never performs the action it describes. Each topic states what the gate
checks, the incident that motivated it, and — when a project is open — the
gate's current status.
"""

from __future__ import annotations

from typing import Any

from .discovery import DiscoveryError
from .discovery import readonly_load as discovery_readonly_load
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
        "  recorded on the owner's behalf, evidence references are optional, and only an\n"
        "  explicit dated owner waiver can skip a question.\n"
        "WHY IT EXISTS\n"
        "  Plans built on guesses get reworked after approval. The interview is\n"
        "  cheap; rework is not — the interview exists so plans bind to owner\n"
        "  facts rather than guesses (docs/PROJECT-HISTORY.md records why the\n"
        "  v1 repository was rebuilt). Answers are recorded by the agent on the\n"
        "  owner's behalf; owner identity is not cryptographically verified,\n"
        "  and evidence references are optional. Waivers\n"
        "  exist because some questions genuinely do not apply — but a waiver is\n"
        "  an owner decision with a review date and an exact confirmation\n"
        "  phrase (skill/aperio/SKILL.md, discovery waiver), not an agent\n"
        "  shortcut.\n"
        "COMMANDS\n"
        "  aperio discover next --json\n"
        "                                 prints the next question, its id, and choices\n"
        "  aperio discover answer '<question-id>' --choice '<option-number-or-value>' \\\n"
        "      --text '<the owner answer>' --evidence '<optional source>'\n"
        "  aperio discover waive '<question-id>' --by '<owner>' --risk '<risk>' \\\n"
        "      --review-at 'YYYY-MM-DD' --confirm 'I accept this risk'\n"
        "  aperio discover status"
    )
    if project is not None:
        try:
            with discovery_readonly_load():
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
        "  command makes the dossier ready (docs/STATUS.md, Learning plan gate\n"
        "  row; tests/test_cli.py::test_plan_without_learning_is_refused). A\n"
        "  human must still judge source quality — the gate validates\n"
        "  structure, not truth.\n"
        "COMMANDS\n"
        "  aperio learn import '<dossier.json>'\n"
        "  aperio learn proof --command '<a command that proves the stack works>'\n"
        "  aperio learn status"
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
        "  approval records who accepted the work and on what evidence. A task\n"
        "  cannot start until its predecessor is accepted or deferred\n"
        "  (skill/aperio/SKILL.md todo gate; tests/test_todo.py).\n"
        "COMMANDS\n"
        "  aperio todo add '<title>' --deliverable '<what exists when done>' \\\n"
        "      --acceptance '<how it is checked>'\n"
        "  aperio todo start '<todo-id>'\n"
        "  aperio todo accept '<todo-id>' --by '<owner>' \\\n"
        "      --evidence '<what proves the deliverable>' --confirm 'I accept this task'\n"
        "  aperio todo defer '<todo-id>' --by '<owner>' --reason '<why>'\n"
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
        "  features, out_of_scope, integrations, constraints, review owner,\n"
        "  approval path). `done` and\n"
        "  `handoff` require the FULL record: deploy, after-sales, design, and\n"
        "  security sections. High/critical unresolved security risk blocks full\n"
        "  readiness.\n"
        "WHY IT EXISTS\n"
        "  Deployment facts and the threat model are owner decisions, not agent\n"
        "  guesses. The split matters: preflight is enough to start work; the\n"
        "  full record is enough to claim the project is ready for the world\n"
        "  (docs/STATUS.md, Project readiness record row). The plan pins the\n"
        "  record's digest — editing readiness after planning invalidates the\n"
        "  plan (tests/test_cli.py::test_readiness_change_invalidates_the_plan).\n"
        "COMMANDS\n"
        "  aperio readiness import '<readiness.json>'\n"
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
        "  aperio approve '<plan-id>' --by '<owner>' --confirm 'I approve this plan'\n"
        "  aperio plan '<plan.json>'\n"
        "                                 write a fresh plan; re-planning creates a new task"
    )
    if project is not None:
        approved = [p for p in project.plans_readonly() if p.approval is not None]
        text += _project_line(f"{len(approved)} approved plan(s) of {len(project.plans_readonly())}")
    return text


def _writes(project: Project | None) -> str:
    text = (
        "WHAT IT CHECKS\n"
        "  Every step declares the paths it may change; the union of those\n"
        "  declarations is the run boundary. The runner snapshots the declared\n"
        "  targets before the run, diffs the scanned tree after, and fails the\n"
        "  run on any change outside that union (host steps are additionally\n"
        "  held to their own step's writes). The scan skips\n"
        "  .git, .aperio, node_modules, virtualenvs, and cache dirs, and cannot\n"
        "  see writes outside the project (README, known limits). `.git` and\n"
        "  `.aperio` are protected and cannot be un-protected by project policy.\n"
        "  A `read` step must not change anything.\n"
        "WHY IT EXISTS\n"
        "  Undeclared writes are how agents break neighboring code. The fence\n"
        "  (allowed_paths) bounds the plan; the doors (step writes) bound each\n"
        "  step. Protected paths are non-overridable by design (PRD Z-02;\n"
        "  tests/test_core.py::test_protected_paths_cannot_be_removed_by_policy).\n"
        "  Glob writes match one segment per `*` — `out/*.html` does not reach\n"
        "  `out/sub/x.html` (PRD Z-D6). Shell steps without an OS sandbox are\n"
        "  DETECTED after the fact, not prevented: set `sandbox: true` when the\n"
        "  plan should run inside sandbox-exec/bwrap (PRD Z-01).\n"
        "COMMANDS\n"
        "  aperio plan '<plan.json>'\n"
        "  aperio rollback '<task-id>' --yes"
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
        "  Reviewer independence exists because reviewer identity was once a\n"
        "  free-text label one process could self-assert (incident F2,\n"
        "  docs/AUDIT-CLAUDE-20261026.md); self-approval (F1) is the approval\n"
        "  gate's incident. The\n"
        "  reviewer's job is to refute the work; confirmation is earned when\n"
        "  refutation attempts fail. The audit ledger (a separate feature)\n"
        "  enforces evidence-and-location shape for its findings; host review\n"
        "  verdicts are validated for verdict/reviewer identity, not finding\n"
        "  structure — read the returned findings rather than trusting them\n"
        "  (docs/AUDIT-CLAUDE-20261026.md;\n"
        "  tests/test_adapter.py::test_reviewer_cannot_change_the_project).\n"
        "COMMANDS\n"
        "  aperio review '<task-id>' --host claude\n"
        "  aperio review '<task-id>' --reviewer '<independent name>' \\\n"
        "      --verdict confirmed\n"
        "  aperio mediate '<task-id>'"
    )
    if project is not None:
        tasks = project.tasks_readonly()
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
