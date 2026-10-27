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

import json
from typing import Any

from .discovery import DiscoveryError
from .discovery import status as discovery_status
from .learning import status as learning_status
from .readiness import ReadinessError, validate_preflight
from .readiness import status as readiness_status
from .store import Project
from .todo import status as todo_status


def _step(action: str, command: str, why: str, **extra: Any) -> dict[str, Any]:
    # Bare <placeholders> are shell redirections; quoting keeps every
    # suggested command runnable as printed (a host review caught this).
    import re as _re

    command = _re.sub(r"(?<!['\"])(<[^>]+>)(?!['\"])", r"'\1'", command)
    data = {"action": action, "command": command, "why": why}
    data.update(extra)
    return data


def _with_project(step: dict[str, Any], root: str) -> dict[str, Any]:
    """Point the printed command at the advised project explicitly.

    `apero next --project X` must not suggest commands that would act on
    whatever directory the caller happens to be in (a host review caught
    this). The path is shell-quoted so suggested commands stay safe and
    runnable for valid paths containing shell metacharacters (a later
    review caught the naive double quotes).
    """
    import shlex

    command = step["command"]
    if command.startswith("aperio ") and "--project" not in command:
        head, _, rest = command.partition(" ")
        quoted = shlex.quote(root)
        step["command"] = f"{head} --project {quoted} {rest}" if rest else f"{head} --project {quoted}"
    return step


def _discovery_step(progress: dict[str, Any] | None) -> dict[str, Any] | None:
    if progress is None:
        # No usable progress: route to the read-only lookup so the agent
        # gets a valid question id instead of a placeholder (a host review
        # flagged the unnamed variant).
        return _step(
            "discover.next",
            "aperio discover next --json",
            "discovery state is unreadable or absent; read the next question "
            "(or the error) before answering — the plan gate refuses until "
            "every question is answered or explicitly waived by the owner",
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
    if progress["in_progress"] > 1:
        # _active_todo refuses any count other than exactly one; there is no
        # unstart command, so route to the ledger to defer the extras (a
        # host review caught the missing branch). The why stays prose: any
        # runnable command belongs in the project-scoped command field.
        active = [item["id"] for item in progress["tasks"] if item["status"] == "in_progress"]
        return _step(
            "recover",
            "aperio todo list",
            f"{progress['in_progress']} todo tasks are in progress; plan refuses "
            "unless exactly one is — inspect the ledger and defer the extras "
            f"({', '.join(active[:3])}) until one remains",
        )
    return None


def _run_todo_step(project: Project, progress: dict[str, Any], task: dict[str, Any]) -> dict[str, Any] | None:
    """cmd_run's linked-todo rule for the SAME task the advice names.

    A host review caught this helper picking its own approved task while the
    suggestion named a different one; both must use the selected task.
    """
    plan_id = task.get("plan_id")
    if not plan_id:
        return None
    plan = project.get_plan(plan_id)
    if not plan.todo_id:
        return None
    linked = next(
        (item for item in progress["tasks"] if item["id"] == plan.todo_id), None
    )
    if linked is None:
        return _step(
            "plan",
            "aperio plan <plan.json>",
            "the approved plan is linked to a todo task that no longer exists; "
            "run would refuse — make a new plan",
        )
    if linked["status"] not in {"in_progress", "accepted"}:
        if linked["status"] == "pending":
            return _step(
                "todo.start",
                f"aperio todo start {linked['id']}",
                "the plan's linked todo task is pending; run refuses until it is "
                "started or accepted",
                todo_id=linked["id"],
            )
        return _step(
            "recover",
            f"aperio status {task['task_id']}",
            f"the plan's linked todo task is {linked['status']}; run refuses — "
            "inspect the task and decide: resume, roll back, or re-plan",
            task_id=task["task_id"],
        )
    return None


def _readiness_step(project: Project) -> dict[str, Any] | None:
    """Preflight readiness only: cmd_plan requires preflight, done/handoff full."""
    issues = validate_preflight(project)
    if issues:
        # An existing record needs --replace or the suggested import refuses
        # (a host review caught the missing flag).
        command = (
            "aperio readiness import <readiness.json> --replace"
            if (project.state / "readiness.json").exists()
            else "aperio readiness import <readiness.json>"
        )
        return _step(
            "readiness.import",
            command,
            "pre-flight readiness is required before planning, approval, or run",
            issues=issues[:6],
        )
    return None


def _stale_task_ids(project: Project) -> set[str]:
    """Tasks whose plan bindings no longer match the current gate records."""
    stale: set[str] = set()
    for task in project.tasks():
        if task.status not in {"planned", "approved"} or not task.plan_id:
            continue
        if _binding_problem(project, str(task.plan_id)) is not None:
            stale.add(task.id)
    return stale


def _binding_problem(project: Project, plan_id: str) -> str | None:
    """The stale/missing binding reason for a plan, or None when current."""
    from .discovery import digest as discovery_digest
    from .readiness import digest as readiness_digest

    try:
        plan = project.get_plan(plan_id)
    except Exception:  # noqa: BLE001 - any plan-load failure means re-plan
        return f"the plan {plan_id} cannot be loaded"
    if not plan.learning_digest:
        return "the plan has no learning binding"
    current = learning_status(project)
    if not current.get("ready") or current.get("digest") != plan.learning_digest:
        return "the learning dossier changed after this plan was created"
    if not plan.discovery_digest:
        if project.discovery() is not None:
            return "the plan has no discovery binding"
    else:
        try:
            current = discovery_digest(project)
        except DiscoveryError:
            current = None
        if current != plan.discovery_digest:
            return "discovery changed after this plan was created"
    if not plan.readiness_digest:
        return "the plan has no readiness binding"
    try:
        current = readiness_digest(project)
    except ReadinessError:
        current = None
    if current != plan.readiness_digest:
        return "the readiness record changed after this plan was created"
    return None


def _stale_binding(project: Project, plan_id: str) -> dict[str, Any] | None:
    """A re-plan step when the plan's discovery/learning/readiness pin is stale.

    approve, run, and resume re-check the bindings and refuse on drift; naming
    it here saves the agent the refusal.
    """
    problem = _binding_problem(project, plan_id)
    if problem is None:
        return None
    return _step(
        "plan",
        "aperio plan <plan.json>",
        f"{problem}; approve and run would refuse — make a new plan. The stale "
        "task stays blocked; finish the new plan's slice instead",
    )


def _handoff_written(project: Project, task_id: Any) -> bool:
    """Whether a handoff artifact exists for this done task.

    write_handoff records a handoff.written event with the task id; the
    advisory treats that as loop completion because cmd_handoff leaves the
    task status at done.
    """
    if not task_id:
        return False
    events = project.state / "events.jsonl"
    if not events.is_file():
        return False
    for line in events.read_text(encoding="utf-8").splitlines():
        if '"handoff.written"' not in line or task_id not in line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("event") == "handoff.written" and row.get("data", {}).get("task_id") == task_id:
            return True
    return False


def _task_step(project: Project) -> dict[str, Any] | None:
    """The most advanced in-flight task determines the loop stage.

    Tasks with stale plan bindings are skipped: a re-plan creates a new task,
    and the advisor must follow the new slice rather than re-recommending a
    re-plan for the task that can no longer proceed (a host review caught the
    loop).
    """
    stale_ids = _stale_task_ids(project)
    handed_off = {
        task.id
        for task in project.tasks()
        if task.status == "done" and _handoff_written(project, task.id)
    }
    stage_order = ["planned", "approved", "applied", "verified", "reviewed", "done"]
    best: tuple[int, dict[str, Any]] | None = None
    for task in project.tasks():
        # A handed-off task is finished: it must not mask newer in-flight
        # work (a host review caught the done task winning forever), and a
        # stale task can no longer proceed.
        if task.id in stale_ids or task.id in handed_off:
            continue
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
        # No active task. If a completed slice exists, the loop for it is
        # done — but a pending todo slice means there is next work to start
        # (a host review flagged complete masking a ready ledger).
        if handed_off:
            ledger = todo_status(project)["tasks"]
            # todo.start refuses while an earlier ledger entry is neither
            # accepted nor deferred (a host review caught the advisor
            # recommending an illegal start), so settle the predecessor
            # first. The handed-off task's own todo is the usual blocker.
            unsettled = next(
                (
                    item
                    for item in ledger
                    if item["status"] == "in_progress"
                ),
                None,
            )
            if unsettled is not None:
                return _step(
                    "todo.accept",
                    f"aperio todo accept {unsettled['id']} --by '<owner>' "
                    "--evidence '<what proves the deliverable>' "
                    "--confirm 'I accept this task'",
                    "the handed-off slice's todo is still in progress; todo start "
                    "refuses until every earlier task is accepted or deferred — "
                    "accept it with the review evidence (or defer it with a reason)",
                    todo_id=unsettled["id"],
                    task_id=max(handed_off),
                )
            pending = next(
                (item for item in ledger if item["status"] == "pending"),
                None,
            )
            if pending is not None:
                return _step(
                    "todo.start",
                    f"aperio todo start {pending['id']}",
                    "the previous slice is settled and the ledger holds the next "
                    "pending slice; start it before planning",
                    todo_id=pending["id"],
                    task_id=max(handed_off),
                )
            return _step(
                "complete",
                "aperio status --json",
                "the last task is done and its handoff is written; the loop for "
                "this slice is complete — start the next todo slice, then plan it",
                task_id=max(handed_off),
            )
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
            plan_id=task["plan_id"],
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
    # command actually refuses on them (host reviews flagged both over- and
    # under-gating): plan enforces the full preplan set; approve enforces
    # learning/discovery/readiness bindings but has no todo check; run adds
    # the plan's linked todo; verify, review, done, handoff, and the status
    # inspection for a failed task enforce none of these.
    step = _task_step(project)
    assert step is not None
    action = step["action"]

    if action == "plan":
        for gate_step in (
            ready(_learning_step(learning_ready)),
            ready(_todo_nonempty_step(todo)),
            ready(_readiness_step(project)),
            ready(_todo_active_step(todo)),
            ready(_discovery_step(discovery_ready)),
        ):
            if gate_step is not None:
                return gate_step
    elif action == "approve":
        for gate_step in (
            ready(_learning_step(learning_ready)),
            ready(_readiness_step(project)),
            ready(_discovery_step(discovery_ready)),
        ):
            if gate_step is not None:
                return gate_step
    elif action == "run":
        for gate_step in (
            ready(_learning_step(learning_ready)),
            ready(_readiness_step(project)),
            ready(_discovery_step(discovery_ready)),
            ready(_run_todo_step(project, todo, step)),
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

    # A handoff already written for this done task means the loop is complete;
    # cmd_handoff does not change task status, so without this the advisor
    # would recommend handoff forever (a host review flagged this).
    if step["action"] == "handoff" and _handoff_written(project, step.get("task_id")):
        return _with_project(
            _step(
                "complete",
                "aperio status --json",
                "the task is done and its handoff is written; the loop for this "
                "slice is complete — start the next todo slice with aperio plan",
                task_id=step.get("task_id"),
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
