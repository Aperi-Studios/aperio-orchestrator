"""Aperio v2 command line. Standard library only."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .adapter import HostError, run_host_review
from .discovery import (
    QUESTION_BY_ID,
    DiscoveryError,
    answer_question,
    as_json,
    format_next,
    format_status,
    next_question,
    parse_choices,
    waive_question,
)
from .discovery import (
    digest as discovery_digest,
)
from .discovery import (
    status as discovery_status,
)
from .discovery import (
    summary as discovery_summary,
)
from .drift import check as drift_check
from .drift import format_findings as format_drift
from .evidence import add as evidence_add
from .evidence import entries as evidence_entries
from .evidence import format_entries as format_evidence
from .handoff import write_handoff
from .hosts import detect_hosts
from .inspect import InspectionError
from .inspect import collect as collect_inspection
from .inspect import format_report as format_inspection
from .inspect import hints as inspection_hints
from .mediator import MediationError, mediate
from .mesh import MeshError, MeshStore
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

    progress = discovery_status(project)
    if not progress["ready"]:
        if progress["missing"]:
            missing = ", ".join(progress["missing"])
            raise DiscoveryError(
                "discovery is required before planning; finish or waive: " + missing
            )
        if progress["research"]:
            research = ", ".join(progress["research"])
            raise DiscoveryError(
                "discovery has unresolved research answers; record a decision first: " + research
            )
        raise DiscoveryError("discovery is not ready")
    if progress["waived"]:
        print(
            "WARNING: discovery waivers accepted: " + ", ".join(progress["waived"]),
            file=sys.stderr,
        )

    plan.discovery_digest = discovery_digest(project)
    task.plan_id = plan.id
    with project.lock():
        project.save_plan(plan)
        project.put_task(task)
        project.append_event("plan.created", {"task_id": task.id, "plan_id": plan.id})
    print(f"{task.id}  {plan.id}  planned")
    print("Approve it before running: aperio approve " + plan.id)
    return 0


def _require_current_discovery(project: Project, plan: Plan) -> None:
    if not plan.discovery_digest:
        return
    current = discovery_digest(project)
    if current != plan.discovery_digest:
        raise DiscoveryError(
            "discovery changed after this plan was created; make a new plan"
        )


def cmd_approve(args: argparse.Namespace) -> int:
    project = _project(args)
    if args.confirm != "I approve this plan":
        raise ModelError('approval requires --confirm "I approve this plan"')
    plan = project.get_plan(args.plan_id)
    _require_current_discovery(project, plan)
    task = project.get_task(plan.task_id)
    if task.status not in {"planned", "approved", "failed"}:
        raise ModelError(f"task is {task.status}; an approved, verified, or done task cannot be re-approved")
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
    _require_current_discovery(project, plan)
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
    if args.host:
        result = run_host_review(
            project,
            args.task_id,
            host=args.host,
            timeout_s=args.timeout,
            budget_usd=args.budget,
        )
        print(f"{args.task_id}  review {result['verdict']} by {result['host']}")
        for finding in result.get("findings", [])[:10]:
            print(f"  {finding.get('severity', '?')}: {finding.get('claim', '')}")
        return 0 if result["verdict"] == "confirmed" else 1
    if not args.reviewer or not args.verdict:
        raise ModelError("manual review needs --reviewer and --verdict, or use --host")
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
        discovery = project.discovery()
        if discovery is not None:
            progress = discovery_status(project)
            print(
                f"Discovery: {progress['answered']}/{progress['total']} answered"
                f" · {progress['research']} need research"
                f" · ready={'yes' if progress['ready'] else 'no'}"
            )
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
    discovery = project.discovery()
    if discovery is not None:
        progress = discovery_status(project)
        print(
            "INFO discovery: "
            f"{progress['answered']}/{progress['total']} answered, "
            f"{progress['research']} need research, "
            f"ready={'yes' if progress['ready'] else 'no'}"
        )
    return 1 if failed else 0


def cmd_drift(args: argparse.Namespace) -> int:
    findings = drift_check(args.project)
    if args.json:
        print(json.dumps([finding.to_dict() for finding in findings], indent=2, sort_keys=True))
    else:
        print(format_drift(findings))
    return 1 if findings else 0


def _question_payload(project: Project, question: Any) -> dict[str, Any]:
    progress = discovery_status(project)
    return {
        "id": question.id,
        "domain": question.domain,
        "prompt": question.prompt,
        "why": question.why,
        "multi": question.multi,
        "allow_text": question.allow_text,
        "options": [
            {"number": number, "value": choice.value, "label": choice.label}
            for number, choice in enumerate(question.choices, 1)
        ],
        "progress": {
            "answered": progress["answered"],
            "total": progress["total"],
            "research": progress["research"],
            "missing": progress["missing"],
            "waived": progress["waived"],
            "waived_research": progress["waived_research"],
            "ready": progress["ready"],
        },
        "hints": inspection_hints(project, question.id),
    }


def cmd_discover(args: argparse.Namespace) -> int:
    project = _project(args)
    if args.discover_command == "next":
        question = next_question(project)
        if question is None:
            progress = discovery_status(project)
            if args.json:
                print(as_json({"ready": True, "status": progress, "question": None}))
            else:
                print(format_status(project))
            return 0
        if args.json:
            print(
                as_json(
                    {
                        "ready": False,
                        "status": discovery_status(project),
                        "question": _question_payload(project, question),
                    }
                )
            )
        else:
            print(format_next(project))
            hints = inspection_hints(project, question.id)
            if hints:
                print("\nInspection hints:")
                for hint in hints:
                    print(f"- {hint}")
        return 0
    if args.discover_command == "answer":
        question = QUESTION_BY_ID.get(args.question_id)
        if question is None:
            raise DiscoveryError(f"unknown question: {args.question_id}")
        values = parse_choices(question, args.choice or "")
        answer = answer_question(
            project,
            args.question_id,
            choices=values,
            text=args.text or "",
            evidence=args.evidence or "",
        )
        progress = discovery_status(project)
        if args.json:
            print(
                as_json(
                    {
                        "answer": answer,
                        "next": progress["next"],
                        "ready": progress["ready"],
                        "status": progress,
                    }
                )
            )
        else:
            print(f"{args.question_id} recorded")
            if progress["next"]:
                print(format_next(project))
            else:
                print(format_status(project))
        return 0
    if args.discover_command == "waive":
        waiver = waive_question(
            project,
            args.question_id,
            by=args.by,
            risk=args.risk,
            confirm=args.confirm,
            review_at=args.review_at,
        )
        if args.json:
            print(as_json({"waiver": waiver, "status": discovery_status(project)}))
        else:
            print(f"{args.question_id} waived by {waiver['by']}")
            print(format_status(project))
        return 0
    if args.discover_command == "status":
        progress = discovery_status(project)
        print(as_json(progress) if args.json else format_status(project))
        return 0
    if args.discover_command == "summary":
        print(discovery_summary(project))
        return 0
    raise DiscoveryError("unknown discover command")


def cmd_inspect(args: argparse.Namespace) -> int:
    project = _project(args)
    data = collect_inspection(project, url=args.url, allow_private=args.allow_private)
    print(as_json(data) if args.json else format_inspection(data))
    return 0


def cmd_evidence(args: argparse.Namespace) -> int:
    project = _project(args)
    if args.evidence_command == "add":
        entry = evidence_add(project, args.path, label=args.label)
        if args.json:
            print(as_json(entry))
        else:
            print(f"{entry['id']}  {entry['path']}  {entry['sha256']}")
        return 0
    data = evidence_entries(project)
    print(as_json(data) if args.json else format_evidence(data))
    return 0


def cmd_message(args: argparse.Namespace) -> int:
    project = _project(args)
    store = MeshStore(project)
    try:
        if args.message_command == "send":
            message = store.send(
                args.sender,
                args.to,
                args.body,
                task_id=args.task,
                kind=args.kind,
                thread_id=args.thread,
                reply_to=args.reply_to,
            )
            print(json.dumps(message, indent=2, sort_keys=True))
            return 0
        if args.message_command == "read":
            messages = store.read(
                recipient=args.to,
                task_id=args.task,
                thread_id=args.thread,
                since_id=args.since,
                limit=args.limit,
                mark_read=args.mark_read,
            )
            if args.json:
                print(json.dumps(messages, indent=2, sort_keys=True))
            else:
                for message in messages:
                    print(f"{message['id']}  {message['thread_id']}  {message['sender']} -> {message['recipient']}: {message['body']}")
            return 0
        if args.message_command == "ack":
            print(json.dumps(store.ack(args.message_id, args.by), indent=2, sort_keys=True))
            return 0
        if args.message_command == "stats":
            print(json.dumps(store.stats(), indent=2, sort_keys=True))
            return 0
    finally:
        store.close()
    raise ModelError(f"unknown message command: {args.message_command}")


def cmd_mediate(args: argparse.Namespace) -> int:
    project = _project(args)
    record = mediate(project, args.task_id)
    print(f"{record['disposition']}: {record['reason']}")
    print(record["evidence_path"])
    return 0 if record["disposition"] == "CONFIRMED" else 1


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
    p.add_argument("--reviewer", default=None)
    p.add_argument("--verdict", choices=["confirmed", "refuted"], default=None)
    p.add_argument("--notes", default="")
    p.add_argument("--host", default=None, help="run a fresh-context host review (claude, codex, dsh, goose)")
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("--budget", type=float, default=1.50)
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

    p = sub.add_parser("drift", help="check docs for links and paths that do not exist")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_drift)

    p = sub.add_parser("discover", help="structured, persistent discovery interview")
    discover = p.add_subparsers(dest="discover_command", required=True)
    discover_next = discover.add_parser("next", help="show the next question")
    discover_next.add_argument("--json", action="store_true")
    discover_next.set_defaults(func=cmd_discover)
    discover_answer = discover.add_parser("answer", help="record an answer")
    discover_answer.add_argument("question_id")
    discover_answer.add_argument("--choice", default="", help="comma-separated option numbers or values")
    discover_answer.add_argument("--text", default="", help="free-text answer or clarification")
    discover_answer.add_argument("--evidence", default="", help="path, URL, or reference")
    discover_answer.add_argument("--json", action="store_true")
    discover_answer.set_defaults(func=cmd_discover)
    discover_waive = discover.add_parser("waive", help="record an explicit owner waiver")
    discover_waive.add_argument("question_id")
    discover_waive.add_argument("--by", required=True)
    discover_waive.add_argument("--risk", required=True)
    discover_waive.add_argument("--review-at", required=True)
    discover_waive.add_argument("--confirm", required=True)
    discover_waive.add_argument("--json", action="store_true")
    discover_waive.set_defaults(func=cmd_discover)
    discover_status = discover.add_parser("status", help="show discovery coverage")
    discover_status.add_argument("--json", action="store_true")
    discover_status.set_defaults(func=cmd_discover)
    discover_summary = discover.add_parser("summary", help="show recorded answers")
    discover_summary.set_defaults(func=cmd_discover)

    p = sub.add_parser("inspect", help="read-only folder and URL inspection")
    p.add_argument("--url", default=None, help="public URL to inspect read-only")
    p.add_argument("--allow-private", action="store_true", help="allow a private or loopback URL")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("evidence", help="record file evidence as a path and hash")
    evidence = p.add_subparsers(dest="evidence_command", required=True)
    evidence_add = evidence.add_parser("add", help="record a file reference and hash")
    evidence_add.add_argument("path")
    evidence_add.add_argument("--label", default="")
    evidence_add.add_argument("--json", action="store_true")
    evidence_add.set_defaults(func=cmd_evidence)
    evidence_list = evidence.add_parser("list", help="show recorded evidence files")
    evidence_list.add_argument("--json", action="store_true")
    evidence_list.set_defaults(func=cmd_evidence)

    p = sub.add_parser("message", help="local durable message store")
    msg = p.add_subparsers(dest="message_command", required=True)
    send = msg.add_parser("send", help="send a message")
    send.add_argument("--from", dest="sender", required=True)
    send.add_argument("--to", required=True)
    send.add_argument("--body", required=True)
    send.add_argument("--task", default=None)
    send.add_argument("--kind", default="note", choices=["note", "task", "reply", "review", "status"])
    send.add_argument("--thread", default=None)
    send.add_argument("--reply-to", type=int, default=None)
    send.set_defaults(func=cmd_message)
    read = msg.add_parser("read", help="read messages")
    read.add_argument("--to", default=None)
    read.add_argument("--task", default=None)
    read.add_argument("--thread", default=None)
    read.add_argument("--since", type=int, default=0)
    read.add_argument("--limit", type=int, default=100)
    read.add_argument("--mark-read", action="store_true")
    read.add_argument("--json", action="store_true")
    read.set_defaults(func=cmd_message)
    ack = msg.add_parser("ack", help="acknowledge a message")
    ack.add_argument("message_id", type=int)
    ack.add_argument("--by", required=True)
    ack.set_defaults(func=cmd_message)
    stats = msg.add_parser("stats", help="message counts")
    stats.set_defaults(func=cmd_message)

    p = sub.add_parser("mediate", help="record a disposition from task evidence")
    p.add_argument("task_id")
    p.set_defaults(func=cmd_mediate)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (
        StoreError,
        RunError,
        PolicyError,
        ModelError,
        HostError,
        MeshError,
        MediationError,
        DiscoveryError,
        InspectionError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(f"aperio: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
