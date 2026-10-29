"""The tutorial: a flight simulator for the Aperio loop.

``build`` creates a practice project in the learner's chosen directory with
every plan gate pre-satisfied (discovery answered, learning dossier proven,
todo started, readiness imported) plus a starter plan file and a written
checklist. The learner then flies plan -> approve -> run -> verify -> review
-> done -> handoff themselves, following `aperio next` when stuck.

``check`` grades the flight from real project state — read-only, like the
other advisors. It never performs a practice step for the learner and never
touches the practice project's state; it reads and reports only.

This is the teaching layer's simulator: gates stay gates, and the tutorial's
fixture is a disposable copy, not the learner's real project.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .discovery import answer_question
from .learning import import_dossier, record_proof
from .readiness import import_readiness
from .store import Project
from .todo import add as todo_add
from .todo import start as todo_start

CHECKLIST = """# Aperio tutorial: fly the loop yourself

This project is a practice fixture: every plan gate is already satisfied
(discovery answered, learning proven, todo started, readiness imported).
Your job is to fly the loop's execution half with the starter plan.

## Your flight plan (in order)

1. Read the starter plan at `starter-plan.json`. Notice its three parts:
   allowed_paths (the fence), steps (the doors), acceptance (the proof).
2. Create the plan:  aperio plan starter-plan.json
   The output prints `task-id  plan-id`.
3. Approve it as the owner:
   aperio approve <plan-id> --by owner --confirm "I approve this plan"
4. Run it as a different actor:  aperio run <task-id> --actor learner
5. Verify:  aperio verify <task-id>
6. Review as someone who is not the builder:
   aperio review <task-id> --reviewer mentor --verdict confirmed
7. Close it:  aperio done <task-id>
8. Write the handoff:  aperio handoff <task-id>
9. Check your flight:  aperio tutorial . --check

When a command refuses you, run `aperio next` — it names the gate that
stopped you and the exact command past it. Refusals are the lesson.

## The rules you just practiced

- The approval phrase is exact on purpose: approving is an owner decision.
- The run actor must differ from the approver (no self-approval).
- The reviewer must differ from the builder (no self-review).
- `done` requires full readiness; the fixture's record already satisfies it.
"""

DOSSIER = {
    "schema": 1,
    "stack": {
        "surface": "website",
        "runtime": "Python 3.10",
        "framework": "standard library",
        "package_manager": "none",
        "database": "none",
        "hosting": "local",
        "versions": {"python": "3.10"},
        "constraints": [],
    },
    "sources": [
        {
            "title": "Python documentation",
            "url": "https://docs.python.org/3/",
            "kind": "official_docs",
            "version": "3.10",
            "accessed": "2026-10-29",
            "official": True,
        }
    ],
    "skills": [],
    "skill_gap": {"needed": False, "reason": "The standard library is sufficient for this tutorial."},
    "mcps": [],
    "teachback": {
        "agent": "learner",
        "summary": (
            "I can explain the Aperio loop: discovery binds the plan to owner facts, "
            "the learning dossier must be proven by a local command, the todo ledger keeps "
            "one slice in flight, the readiness record separates planning from done, and "
            "approval binds the plan body by hash so later edits invalidate it."
        ),
        "uncertainties": [],
    },
    "competency": {
        "agent": "learner",
        "verdict": "demonstrated",
        "evidence": "The tutorial fixture's local proof command and the checklist walkthrough.",
        "recorded_at": "2026-10-29T00:00:00Z",
    },
}

READINESS = {
    "schema": 1,
    "preflight": {
        "audience": "Tutorial learner",
        "success_measure": "The tutorial page exists with the expected content",
        "features": ["One static page"],
        "out_of_scope": ["Deployment", "Styling", "JavaScript"],
        "integrations": ["None"],
        "constraints": ["Local fixture only"],
        "review_owner": "owner",
        "approval_path": "The learner approves with the exact phrase",
    },
    "deploy": {
        "hosting": "Local file",
        "domain": "localhost",
        "tls": "Not applicable",
        "env_names": [],
        "build": "None",
        "migrate": "None",
        "backup": "Copy the directory",
        "restore": "Copy back",
        "ci_cd": "None",
        "rollback": "Copy back",
        "monitoring": "Command output",
        "smoke": "The acceptance check",
    },
    "aftersales": {
        "support_window": "The tutorial session",
        "escalation_owner": "learner",
        "logs": "Command output",
        "metrics": "Acceptance result",
        "alerts": "None",
        "backup_schedule": "None",
        "restore_drill": "Copy back once",
        "update_policy": "None",
        "admin_recovery": "Delete the directory",
        "docs": "CHECKLIST.md",
    },
    "design": {
        "surface_class": "marketing",
        "contract": "One clear heading and one paragraph",
        "references": ["The checklist"],
        "accessibility": "Plain HTML, one h1",
        "responsive": "Not applicable",
        "originality": "Original fixture text",
        "review_owner": "learner",
    },
    "security": {
        "threat_model": "Local fixture: no network, no secrets, no user input",
        "assets": ["The fixture directory"],
        "trust_boundaries": ["None: local file only"],
        "controls": ["Aperio's path policy"],
        "dependency_scan": "Not applicable: no dependencies",
        "secret_scan": "Not applicable: no secrets",
        "headers": "Not applicable: local file",
        "incident": "Delete the fixture directory",
        "unresolved_severity": "none",
    },
}

DISCOVERY_ANSWERS = [
    ("idea", None, "Build a tutorial page"),
    ("users", None, "The learner"),
    ("success", ["launch"], ""),
    ("must_haves", None, "One page with a heading"),
    ("non_goals", None, "No styling, no deployment"),
    ("constraints", ["none"], ""),
    ("ownership", ["owner"], ""),
    ("evidence", ["none"], ""),
    ("labels", ["new"], ""),
    ("name", None, "tutorial"),
]

STARTER_PLAN = {
    "title": "Tutorial page",
    "request": "Build the tutorial's one-page site",
    "allowed_paths": ["site/"],
    "steps": [
        {"id": "write-page", "kind": "write", "path": "site/index.html", "content": "<h1>Tutorial complete</h1>\n<p>This page was built by flying the Aperio loop.</p>\n"}
    ],
    "acceptance": [
        {"id": "page-exists", "command": "test -f site/index.html"},
        {
            "id": "page-content",
            "command": "grep -q 'Tutorial complete' site/index.html",
        },
    ],
}


def build(directory: str | Path) -> dict[str, Any]:
    """Create the practice fixture with every plan gate pre-satisfied."""
    root = Path(directory).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    project = Project.init(root, "tutorial")
    for question_id, choices, text in DISCOVERY_ANSWERS:
        answer_question(project, question_id, choices=choices, text=text)
    dossier_path = root / "learning.json"
    dossier_path.write_text(json.dumps(DOSSIER, indent=2) + "\n", encoding="utf-8")
    import_dossier(project, str(dossier_path))  # rc=1 (not ready) is the contract
    record_proof(project, "python3 -c \"print('tutorial proof')\"")
    todo = todo_add(
        project,
        "Build the tutorial page",
        deliverable="The tutorial page exists with the expected content",
        acceptance="The page exists and its content check passes",
    )
    todo_start(project, todo["id"])
    readiness_path = root / "readiness.json"
    readiness_path.write_text(json.dumps(READINESS, indent=2) + "\n", encoding="utf-8")
    import_readiness(project, str(readiness_path))
    (root / "starter-plan.json").write_text(
        json.dumps(STARTER_PLAN, indent=2) + "\n", encoding="utf-8"
    )
    (root / "CHECKLIST.md").write_text(CHECKLIST, encoding="utf-8")
    return {
        "project": str(root),
        "checklist": str(root / "CHECKLIST.md"),
        "starter_plan": str(root / "starter-plan.json"),
        "next": "Read CHECKLIST.md, then fly the loop. `aperio tutorial . --check` grades your flight.",
    }


def check(directory: str | Path) -> dict[str, Any]:
    """Grade the learner's flight from real state. Read-only."""
    root = Path(directory).expanduser().resolve()
    project = Project.open(root)
    steps: list[dict[str, Any]] = []
    tasks = [t for t in project.tasks() if t.plan_id]
    task = tasks[-1] if tasks else None

    def step(name: str, done: bool, hint: str) -> None:
        steps.append({"step": name, "done": done, **({"hint": hint} if not done else {})})

    planned = task is not None
    step("plan created", planned, "aperio plan starter-plan.json")
    approved = planned and task is not None and task.status in {"approved", "applied", "verified", "reviewed", "done"}
    step("plan approved with the exact phrase", approved, "apero approve <plan-id> --by owner --confirm \"I approve this plan\"")
    applied = planned and task is not None and task.status in {"applied", "verified", "reviewed", "done"}
    step("run applied by a different actor", applied, "apero run <task-id> --actor learner")
    verified = planned and task is not None and task.status in {"verified", "reviewed", "done"}
    step("acceptance checks passed", verified, "apero verify <task-id>")
    reviewed = planned and task is not None and task.status in {"reviewed", "done"}
    step("independent review confirmed", reviewed, "apero review <task-id> --reviewer mentor --verdict confirmed")
    done = planned and task is not None and task.status == "done"
    step("task closed", done, "apero done <task-id>")
    handoff_written = (project.state / "handoff.md").is_file()
    step("handoff written", handoff_written, "apero handoff <task-id>")
    page_ok = (root / "site" / "index.html").is_file()
    step("artifact exists", page_ok, "the run should have created site/index.html")

    passed = sum(1 for s in steps if s["done"])
    grade = "complete" if passed == len(steps) else "in progress"
    return {
        "grade": grade,
        "passed": passed,
        "total": len(steps),
        "steps": steps,
        "read_only": True,
    }
