"""The next-action advisor: read-only GPS for the Aperio loop.

``next_action`` inspects project state and answers three questions an agent
would otherwise have to reverse-engineer from refusals: what is the next legal
action, the exact command that performs it, and why the loop requires it now.

Gate steps prefix the lifecycle advice only when the next lifecycle command
actually refuses on them (plan, approve, run, recover): verify and review do
not re-check the gates, so an applied task routes to verify even if a gate
later drifted. Within the gate check the order is the one ``cmd_plan``
refuses in (learning, todo-nonempty, preflight readiness, single in-progress
todo, discovery). Full readiness is demanded only before done and handoff,
matching the CLI.

The module is deliberately read-only: it opens state, never writes, and never
performs the action it names. Gates stay gates; this only narrates them.
"""

from __future__ import annotations

from typing import Any

from .discovery import DiscoveryError
from .discovery import status as discovery_status
from .learning import status as learning_status
from .readiness import ReadinessError, validate_preflight
from .readiness import status as readiness_status
from .store import Project
from .todo import status as todo_status


def _step(action: str, command: str, why: str, **extra: Any) -> dict[str, Any]:
    data = {"action": action, "command": command, "why": why}
    data.update(extra)
    return data


def _with_project(step: dict[str, Any], root: str) -> dict[str, Any]:
    """Point the printed command at the advised project explicitly.

    `apero next --project X` must not suggest commands that would act on
    whatever directory the caller happens to be in (a host review caught
    this). The placeholder form <project-root> keeps literal commands
    copyable while stating the required target.
    """
    command = step["command"]
    if command.startswith("aperio ") and "--project" not in command:
        head, _, rest = command.partition(" ")
        step["command"] = f'{head} --project "{root}" {rest}' if rest else f'{head} --project "{root}"'
    return step


def _discovery_step(progress: dict[str, Any] | None) -> dict[str, Any] | None:
    if progress is None:
        return _step(
            "discover.answer",
            "aperio discover answer <question-id> --text \"<owner's answer>\"",
            "discovery has not started; the plan gate refuses until every question "
            "is answered or explicitly waived by the owner",
        )
    if not progress["ready"]:
        question = progress.get("next")
        if not question:
            # The record could not name a question (corrupt or unreadable):
            # route to the read-only lookup instead of printing an invalid id.
            return _step(
                "discover.next",
                "aperio discover next --json",
                "discovery is not ready but the record did not name the next "
                "question; read the next question (or the error) before answering",
            )
        return _step(
            "discover.answer",
            f"aperio discover answer {question} --text \"<owner's answer>\"",
            f"discovery is {progress['answered']}/{progress['total']} answered; "
            "the plan gate refuses until it is ready",
            question=question,
        )
    return None


def _learning_step(progress: dict[str, Any] | None) -> dict[str, Any] | None:
    if progress is None or progress.get("digest") is None:
        return _step(
            "learn.import",
            "aperio learn import <dossier.json>",
            "no learning dossier exists; plan, approve, and run refuse without one",
            issues=progress.get("issues", []) if progress else [],
        )
    if not progress["ready"]:
        return _step(
            "learn.proof",
            "aperio learn proof --command \"<command that proves the stack works>\"",
            "the dossier is imported but not proven; imported proof text is ignored, "
            "a local command must run and pass",
            issues=progress.get("issues", []),
        )
    return None


def _todo_nonempty_step(progress: dict[str, Any] | None) -> dict[str, Any] | None:
    """cmd_plan's _require_todo: the ledger must not be empty."""
    if progress is None or progress["count"] == 0:
        return _step(
            "todo.add",
            "aperio todo add \"<title>\" --deliverable \"<what exists when done>\" "
            "--acceptance \"<how it is checked>\"",
            "the todo ledger is empty; plan refuses without exactly one task in progress",
        )
    return None


def _todo_active_step(progress: dict[str, Any]) -> dict[str, Any] | None:
    """cmd_plan's _active_todo: exactly one task must be in progress.

    Checked after preflight readiness because cmd_plan reaches it later.
    """
    if progress["in_progress"] == 0:
        pending = next((item for item in progress["tasks"] if item["status"] == "pending"), None)
        if pending is None:
            return _step(
                "todo.add",
                "aperio todo add \"<title>\" --deliverable \"<what exists when done>\" "
                "--acceptance \"<how it is checked>\"",
                "every todo task is accepted or deferred; add the next slice",
            )
        return _step(
            "todo.start",
            f"aperio todo start {pending['id']}",
            "plan requires exactly one todo task in progress",
            todo_id=pending["id"],
        )
    return None


def _readiness_step(project: Project) -> dict[str, Any] | None:
    """Preflight readiness only: cmd_plan requires preflight, done/handoff full."""
    issues = validate_preflight(project)
    if issues:
        return _step(
            "readiness.import",
            "aperio readiness import <readiness.json>",
            "pre-flight readiness is required before planning, approval, or run",
            issues=issues[:6],
        )
    return None


def _stale_binding(project: Project, plan_id: str) -> dict[str, Any] | None:
    """A re-plan step when the plan's discovery/learning/readiness pin is stale.

    approve, run, and resume re-check the bindings and refuse on drift; naming
    it here saves the agent the refusal.
    """
    from .discovery import digest as discovery_digest
    from .readiness import digest as readiness_digest

    try:
        plan = project.get_plan(plan_id)
    except Exception:  # noqa: BLE001 - any plan-load failure means re-plan
        return _step(
            "plan",
            "aperio plan <plan.json>",
            f"the plan {plan_id} cannot be loaded; write a fresh bounded plan",
        )
    if not plan.learning_digest:
        # A missing binding is refused by approve/run exactly like a stale one.
        return _step(
            "plan",
            "aperio plan <plan.json>",
            "the plan has no learning binding; approve and run would refuse — "
            "make a new plan against the current dossier",
        )
    current = learning_status(project)
    if not current.get("ready") or current.get("digest") != plan.learning_digest:
        return _step(
            "plan",
            "aperio plan <plan.json>",
            "the learning dossier changed after this plan was created; "
            "approve and run would refuse — make a new plan",
        )
    if not plan.discovery_digest:
        if project.discovery() is not None:
            return _step(
                "plan",
                "aperio plan <plan.json>",
                "the plan has no discovery binding; approve would refuse — "
                "make a new plan against the current discovery record",
            )
    else:
        try:
            current = discovery_digest(project)
        except DiscoveryError:
            current = None
        if current != plan.discovery_digest:
            return _step(
                "plan",
                "aperio plan <plan.json>",
                "discovery changed after this plan was created; "
                "approve and run would refuse — make a new plan",
            )
    if not plan.readiness_digest:
        return _step(
            "plan",
            "aperio plan <plan.json>",
            "the plan has no readiness binding; approve and run would refuse — "
            "make a new plan against the current readiness record",
        )
    try:
        current = readiness_digest(project)
    except ReadinessError:
        current = None
    if current != plan.readiness_digest:
        return _step(
            "plan",
            "aperio plan <plan.json>",
            "the readiness record changed after this plan was created; "
            "approve and run would refuse — make a new plan",
        )
    return None


def _task_step(project: Project) -> dict[str, Any] | None:
    """The most advanced in-flight task determines the loop stage."""
    stage_order = ["planned", "approved", "applied", "verified", "reviewed", "done"]
    best: tuple[int, dict[str, Any]] | None = None
    for task in project.tasks():
        if task.status in {"failed", "blocked", "rolled_back"}:
            index = 0
        else:
            try:
                index = stage_order.index(task.status)
            except ValueError:
                index = 0
        if best is None or index > best[0]:
            best = (index, task.to_dict())
    if best is None:
        return _step(
            "plan",
            "aperio plan <plan.json>",
            "no task is in flight; write a bounded plan for the in-progress todo slice",
        )

    task = best[1]
    status = task["status"]
    # approve and run re-validate the plan's gate bindings; advise a re-plan
    # when any binding is stale instead of pointing at a refusal.
    if status in {"planned", "approved"} and task.get("plan_id"):
        stale = _stale_binding(project, str(task["plan_id"]))
        if stale is not None:
            return stale
    if status == "planned":
        return _step(
            "approve",
            f"aperio approve {task['plan_id']} --by <owner> --confirm \"I approve this plan\"",
            "a plan exists and waits for the owner's explicit approval phrase",
            task_id=task["id"],
            plan_id=task["plan_id"],
        )
    if status == "approved":
        return _step(
            "run",
            f"aperio run {task['id']} --actor <builder>",
            "the plan is approved; the run actor must differ from the approver",
            task_id=task["id"],
        )
    if status == "applied":
        return _step(
            "verify",
            f"aperio verify {task['id']}",
            "the run applied cleanly; acceptance checks must pass before review",
            task_id=task["id"],
        )
    if status == "verified":
        return _step(
            "review",
            f"aperio review {task['id']} --reviewer <independent reviewer> --verdict confirmed",
            "verification passed; an independent reviewer (never the builder) must confirm",
            task_id=task["id"],
        )
    if status == "reviewed":
        return _step(
            "done",
            f"aperio done {task['id']}",
            "the review is confirmed; full readiness is required to close the task",
            task_id=task["id"],
        )
    if status == "done":
        return _step(
            "handoff",
            f"aperio handoff {task['id']}",
            "the task is done; write the owner handoff describing the actual state",
            task_id=task["id"],
        )
    return _step(
        "recover",
        f"aperio status {task['id']}",
        f"the most advanced task is {status}; inspect it and decide: resume, roll back, or re-plan",
        task_id=task["id"],
    )


def next_action(project: Project) -> dict[str, Any]:
    """The single next legal action for this project, or done when complete."""
    root = str(project.root)
    discovery_ready = None
    try:
        discovery_ready = discovery_status(project)
    except DiscoveryError:
        discovery_ready = {"ready": False, "answered": 0, "total": 0, "next": None}
    learning_ready = learning_status(project)
    todo = todo_status(project)

    def ready(step: dict[str, Any] | None) -> dict[str, Any] | None:
        return _with_project(step, root) if step is not None else None

    # Which lifecycle command is next? Gates are only prefixed when that
    # command actually refuses on them: plan/approve/run re-check learning,
    # todo, preflight, and discovery; verify and review do not (a host
    # review flagged gate-first routing misadvising an applied task).
    step = _task_step(project)
    assert step is not None
    gate_enforcing = step["action"] in {"plan", "approve", "run", "recover"}

    if gate_enforcing:
        # In the order cmd_plan reaches its refusals: learning, todo-nonempty,
        # preflight readiness, the single in-progress todo, then discovery.
        for gate_step in (
            ready(_learning_step(learning_ready)),
            ready(_todo_nonempty_step(todo)),
            ready(_readiness_step(project)),
            ready(_todo_active_step(todo)),
            ready(_discovery_step(discovery_ready)),
        ):
            if gate_step is not None:
                return gate_step

    # done and handoff require FULL readiness, not just preflight; route the
    # gap before recommending them (a host review flagged this).
    if step["action"] in {"done", "handoff"}:
        full = readiness_status(project)
        if not full["ready"]:
            return _with_project(
                _step(
                    "readiness.import",
                    "aperio readiness import <readiness.json> --replace",
                    "full project readiness is required before done or handoff",
                    issues=full.get("issues", [])[:6],
                ),
                root,
            )
    step = _with_project(step, root)
    step["gates"] = {
        "discovery": discovery_ready["ready"] if discovery_ready else False,
        "learning": bool(learning_ready.get("ready")),
        "todo_in_progress": todo["in_progress"],
    }
    return step
