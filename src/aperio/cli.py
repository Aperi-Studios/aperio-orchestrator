"""Aperio v2 command line. Standard library only."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .handoff import write_handoff
from .hosts import detect_hosts
from .model import Acceptance, Approval, ModelError, Plan, Step, Task, new_id
from .policy import PolicyError
from .runner import RunError, apply_plan, finish, review, rollback, verify
from .store import Project, StoreError


def _project(args: argparse.Namespace) -> Project:
    return Project.open(args.project)


def _print_task(task: Task) -> None:
    print(f"{task.id}  {task.status:11}  {task.title}")
    if task.plan_id:
        print(f"  plan: {task.plan_id}")
    if task.run_id:
        print(f"  run:  {task.run_id}")


def cmd_init(args: argparse.Namespace) -> int:
    project = Project.init(args.path, name=args.name)
    print(f"Initialized Aperio project at {project.root}")
    print(f"State: {project.state}")
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    project = _project(args)
    text = sys.stdin.read() if args.text == "-" else args.text
    ask = project.add_ask(text, source=args.source)
    print(f"{ask.id}  recorded")
    return 0


def _load_plan_data(path: str) -> dict[str, Any]:
    raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ModelError(f"plan is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ModelError("plan must be a JSON object")
    return data


def cmd_plan(args: argparse.Namespace) -> int:
    project = _project(args)
    data = _load_plan_data(args.file)
    task = Task(
        id=new_id("task"),
        title=str(data.get("title", "")).strip(),
        request=str(data.get("request", "")).strip(),
        status="planned",
    )
    if not task.title or not task.request:
        raise ModelError("plan needs title and request")
    plan = Plan(
        id=new_id("plan"),
        task_id=task.id,
        title=task.title,
        request=task.request,
        allowed_paths=[str(p) for p in data.get("allowed_paths", [])],
        steps=[Step.from_dict(item) for item in data.get("steps", [])],
        acceptance=[Acceptance.from_dict(item) for item in data.get("acceptance", [])],
        builder=str(data.get("builder", "agent")),
    )
    plan.validate()
    if not plan.acceptance:
        raise ModelError("plan needs at least one acceptance check")
    task.plan_id = plan.id
    with project.lock():
        project.save_plan(plan)
        project.put_task(task)
        project.append_event("plan.created", {"task_id": task.id, "plan_id": plan.id})
    print(f"{task.id}  {plan.id}  planned")
    print("Approve it before running: aperio approve " + plan.id)
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    project = _project(args)
    if args.confirm != "I approve this plan":
        raise ModelError('approval requires --confirm "I approve this plan"')
    plan = project.get_plan(args.plan_id)
    task = project.get_task(plan.task_id)
    plan.approval = Approval(approved_by=args.by, note=args.note)
    task.status = "approved"
    with project.lock():
        project.save_plan(plan)
        project.put_task(task)
        project.append_event("plan.approved", {"plan_id": plan.id, "by": args.by})
    print(f"{plan.id}  approved by {args.by}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    project = _project(args)
    task = project.get_task(args.task_id)
    if not task.plan_id:
        raise RunError("task has no plan")
    plan = project.get_plan(task.plan_id)
    evidence = apply_plan(project, plan, actor=args.actor)
    print(f"{evidence['run_id']}  {evidence['status']}")
    if evidence.get("changed_files"):
        print("changed: " + ", ".join(evidence["changed_files"][:20]))
    if evidence.get("violations"):
        for violation in evidence["violations"][:10]:
            print("violation: " + violation)
        return 1
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    project = _project(args)
    evidence = verify(project, args.task_id)
    print(f"{evidence['check_id']}  {evidence['status']}")
    for check in evidence["checks"]:
        print(f"  {check['check_id']}: {'ok' if check['ok'] else 'FAILED'} (exit {check['exit_code']})")
    return 0 if evidence["status"] == "passed" else 1


def cmd_review(args: argparse.Namespace) -> int:
    project = _project(args)
    result = review(project, args.task_id, args.reviewer, args.verdict, notes=args.notes)
    print(f"{args.task_id}  review {result['verdict']} by {result['reviewer']}")
    return 0 if result["verdict"] == "confirmed" else 1


def cmd_done(args: argparse.Namespace) -> int:
    project = _project(args)
    task = finish(project, args.task_id)
    print(f"{task['id']}  done")
    return 0


def cmd_rollback(args: argparse.Namespace) -> int:
    project = _project(args)
    if not args.yes:
        raise ModelError("rollback requires --yes")
    restored = rollback(project, args.task_id)
    print(f"{args.task_id}  rolled back {len(restored)} file(s)")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    project = _project(args)
    if args.task_id:
        task = project.get_task(args.task_id)
        data = task.to_dict()
        if task.plan_id:
            plan = project.get_plan(task.plan_id)
            data["plan"] = plan.to_dict()
        data["evidence"] = project.evidence(task.id)
        if args.json:
            print(json.dumps(data, indent=2, sort_keys=True))
        else:
            _print_task(task)
            if task.review:
                print(f"  review: {task.review.verdict} by {task.review.reviewer}")
            for note in task.notes:
                print(f"  note: {note}")
        return 0
    tasks = project.tasks()
    if args.json:
        print(json.dumps([t.to_dict() for t in tasks], indent=2, sort_keys=True))
    else:
        print(f"Project: {project.root}")
        print(f"State:   {project.state}")
        if not tasks:
            print("No tasks. Add an ask or a plan.")
        for task in tasks:
            _print_task(task)
    return 0


def cmd_handoff(args: argparse.Namespace) -> int:
    project = _project(args)
    path = write_handoff(project, args.task_id)
    print(path)
    if args.print:
        print(path.read_text(encoding="utf-8"))
    return 0


def cmd_hosts(args: argparse.Namespace) -> int:
    hosts = detect_hosts()
    if args.json:
        print(json.dumps([h.__dict__ for h in hosts], indent=2, sort_keys=True))
        return 0
    print(f"{'name':12} {'status':10} {'version':48} path")
    for host in hosts:
        print(f"{host.name:12} {host.status:10} {host.version[:48]:48} {host.path or ''}")
    print("\nPresence is not permission. Authentication, model access, and cost are unverified.")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    project = _project(args)
    checks: list[tuple[str, bool, str]] = [
        ("python", sys.version_info >= (3, 10), sys.version.split()[0]),
        ("project state", project.state.is_dir(), str(project.state)),
        ("project metadata", (project.state / "project.json").is_file(), "project.json"),
        ("queue", (project.state / "queue.json").is_file(), "queue.json"),
        ("write access", os.access(project.state, os.W_OK), str(project.state)),
    ]
    failed = False
    for name, ok, detail in checks:
        print(f"{'OK  ' if ok else 'FAIL'} {name}: {detail}")
        failed = failed or not ok
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aperio",
        description="Aperio v2: a bounded, evidence-first project orchestrator.",
    )
    parser.add_argument("--version", action="version", version=f"aperio {__version__}")
    parser.add_argument("--project", default=os.getcwd(), help="project root (default: current directory)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="initialize a project")
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("--name", default="")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("ask", help="record an owner ask")
    p.add_argument("text", help="ask text, or - to read stdin")
    p.add_argument("--source", default="manual")
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("plan", help="create a plan from JSON")
    p.add_argument("file", help="plan JSON path, or - to read stdin")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("approve", help="approve a plan as the owner")
    p.add_argument("plan_id")
    p.add_argument("--by", default=os.environ.get("USER", "owner"))
    p.add_argument("--note", default="")
    p.add_argument("--confirm", required=True)
    p.set_defaults(func=cmd_approve)

    p = sub.add_parser("run", help="apply an approved plan")
    p.add_argument("task_id")
    p.add_argument("--actor", default="agent")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("verify", help="run the plan's acceptance checks")
    p.add_argument("task_id")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("review", help="record an independent review")
    p.add_argument("task_id")
    p.add_argument("--reviewer", required=True)
    p.add_argument("--verdict", choices=["confirmed", "refuted"], required=True)
    p.add_argument("--notes", default="")
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("done", help="mark a task done after review")
    p.add_argument("task_id")
    p.set_defaults(func=cmd_done)

    p = sub.add_parser("rollback", help="restore a run's files from its backup")
    p.add_argument("task_id")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_rollback)

    p = sub.add_parser("status", help="show project or task state")
    p.add_argument("task_id", nargs="?")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("handoff", help="write the owner handoff")
    p.add_argument("task_id")
    p.add_argument("--print", action="store_true")
    p.set_defaults(func=cmd_handoff)

    p = sub.add_parser("hosts", help="detect installed hosts (read-only)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_hosts)

    p = sub.add_parser("doctor", help="check the project state")
    p.set_defaults(func=cmd_doctor)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (StoreError, RunError, PolicyError, ModelError, OSError, json.JSONDecodeError) as exc:
        print(f"aperio: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
