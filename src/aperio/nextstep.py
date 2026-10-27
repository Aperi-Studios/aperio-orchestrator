"""The next-action advisor: read-only GPS for the Aperio loop.

``next_action`` inspects project state and answers three questions an agent
would otherwise have to reverse-engineer from refusals: what is the next legal
action, the exact command that performs it, and why the loop requires it now.

The module is deliberately read-only: it opens state, never writes, and never
performs the action it names. Gates stay gates; this only narrates them.
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


def _step(action: str, command: str, why: str, **extra: Any) -> dict[str, Any]:
    data = {"action": action, "command": command, "why": why}
    data.update(extra)
    return data


def _discovery_step(progress: dict[str, Any] | None) -> dict[str, Any] | None:
    if progress is None:
        return _step(
            "discover.answer",
            "apero discover answer <question-id> --text \"<owner's answer>\"",
            "discovery has not started; the plan gate refuses until every question "
            "is answered or explicitly waived by the owner",
        )
    if not progress["ready"]:
        question = progress["next"]
        return _step(
            "discover.answer",
            f"apero discover answer {question} --text \"<owner's answer>\"",
            f"discovery is {progress['answered']}/{progress['total']} answered; "
            "the plan gate refuses until it is ready",
            question=question,
        )
    return None


def _learning_step(progress: dict[str, Any] | None) -> dict[str, Any] | None:
    if progress is None or progress.get("digest") is None:
        return _step(
            "learn.import",
            "apero learn import <dossier.json>",
            "no learning dossier exists; plan, approve, and run refuse without one",
            issues=progress.get("issues", []) if progress else [],
        )
    if not progress["ready"]:
        return _step(
            "learn.proof",
            "apero learn proof --command \"<command that proves the stack works>\"",
            "the dossier is imported but not proven; imported proof text is ignored, "
            "a local command must run and pass",
            issues=progress.get("issues", []),
        )
    return None


def _todo_step(progress: dict[str, Any] | None) -> dict[str, Any] | None:
    if progress is None:
        return _step(
            "todo.add",
            "apero todo add \"<title>\" --deliverable \"<what exists when done>\" "
            "--acceptance \"<how it is checked>\"",
            "the todo ledger is empty; plan refuses without exactly one task in progress",
        )
    if progress["in_progress"] == 0:
        pending = next((item for item in progress["tasks"] if item["status"] == "pending"), None)
        if pending is None:
            return _step(
                "todo.add",
                "apero todo add \"<title>\" --deliverable \"<what exists when done>\" "
                "--acceptance \"<how it is checked>\"",
                "every todo task is accepted or deferred; add the next slice",
            )
        return _step(
            "todo.start",
            f"apero todo start {pending['id']}",
            "plan requires exactly one todo task in progress",
            todo_id=pending["id"],
        )
    return None


def _readiness_step(progress: dict[str, Any] | None) -> dict[str, Any] | None:
    if progress is None:
        return _step(
            "readiness.import",
            "apero readiness import <readiness.json>",
            "no readiness record exists; the preflight gate refuses to plan without one",
        )
    if not progress["ready"]:
        return _step(
            "readiness.import",
            "apero readiness import <readiness.json> --replace",
            "the readiness record has open issues",
            issues=progress.get("issues", []),
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
            "apero plan <plan.json>",
            f"the plan {plan_id} cannot be loaded; write a fresh bounded plan",
        )
    if plan.learning_digest:
        current = learning_status(project)
        if not current.get("ready") or current.get("digest") != plan.learning_digest:
            return _step(
                "plan",
                "apero plan <plan.json>",
                "the learning dossier changed after this plan was created; "
                "approve and run would refuse — make a new plan",
                task_id=None,
            )
    if plan.discovery_digest:
        try:
            current = discovery_digest(project)
        except DiscoveryError:
            current = None
        if current != plan.discovery_digest:
            return _step(
                "plan",
                "apero plan <plan.json>",
                "discovery changed after this plan was created; "
                "approve and run would refuse — make a new plan",
            )
    if plan.readiness_digest:
        try:
            current = readiness_digest(project)
        except ReadinessError:
            current = None
        if current != plan.readiness_digest:
            return _step(
                "plan",
                "apero plan <plan.json>",
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
            "apero plan <plan.json>",
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
            f"apero approve {task['plan_id']} --by <owner> --confirm \"I approve this plan\"",
            "a plan exists and waits for the owner's explicit approval phrase",
            task_id=task["id"],
            plan_id=task["plan_id"],
        )
    if status == "approved":
        return _step(
            "run",
            f"apero run {task['id']} --actor <builder>",
            "the plan is approved; the run actor must differ from the approver",
            task_id=task["id"],
        )
    if status == "applied":
        return _step(
            "verify",
            f"apero verify {task['id']}",
            "the run applied cleanly; acceptance checks must pass before review",
            task_id=task["id"],
        )
    if status == "verified":
        return _step(
            "review",
            f"apero review {task['id']} --reviewer <independent reviewer> --verdict confirmed",
            "verification passed; an independent reviewer (never the builder) must confirm",
            task_id=task["id"],
        )
    if status == "reviewed":
        return _step(
            "done",
            f"apero done {task['id']}",
            "the review is confirmed; full readiness is required to close the task",
            task_id=task["id"],
        )
    if status == "done":
        return _step(
            "handoff",
            f"apero handoff {task['id']}",
            "the task is done; write the owner handoff describing the actual state",
            task_id=task["id"],
        )
    return _step(
        "recover",
        f"apero status {task['id']}",
        f"the most advanced task is {status}; inspect it and decide: resume, roll back, or re-plan",
        task_id=task["id"],
    )


def next_action(project: Project) -> dict[str, Any]:
    """The single next legal action for this project, or done when complete."""
    # Gates first, in the order cmd_plan enforces them: learning, todo,
    # preflight readiness, then discovery.
    discovery_ready = None
    try:
        discovery_ready = discovery_status(project)
    except DiscoveryError:
        discovery_ready = {"ready": False, "answered": 0, "total": 0, "next": None}
    learning_ready = learning_status(project)
    todo = todo_status(project)
    readiness = None
    try:
        readiness = readiness_status(project)
    except ReadinessError:
        readiness = None

    for step in (
        _learning_step(learning_ready),
        _todo_step(todo),
        _readiness_step(readiness),
        _discovery_step(discovery_ready),
    ):
        if step is not None:
            return step

    # All gates satisfied: the loop itself is the next action.
    step = _task_step(project)
    assert step is not None
    step["gates"] = {
        "discovery": discovery_ready["ready"] if discovery_ready else False,
        "learning": bool(learning_ready.get("ready")),
        "todo_in_progress": todo["in_progress"],
        "readiness": bool(readiness.get("ready")) if readiness else False,
    }
    return step
