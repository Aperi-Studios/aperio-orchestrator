"""Tests for the read-only next-action advisor (apero next)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from aperio.nextstep import next_action
from aperio.store import Project

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
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
            "accessed": "2026-10-26",
            "official": True,
        }
    ],
    "skills": [],
    "skill_gap": {"needed": False, "reason": "The standard library is sufficient."},
    "mcps": [],
    "teachback": {
        "agent": "agent",
        "summary": "I can explain the runtime, plan format, acceptance checks, and limits of this fixture.",
        "uncertainties": [],
    },
    "competency": {
        "agent": "agent",
        "verdict": "demonstrated",
        "evidence": "The local proof command is recorded.",
        "recorded_at": "2026-10-26T00:00:00Z",
    },
}
READINESS = {
    "schema": 1,
    "preflight": {
        "audience": "u",
        "success_measure": "renders",
        "features": ["page"],
        "out_of_scope": ["deploy"],
        "integrations": ["none"],
        "constraints": ["local"],
        "review_owner": "owner",
        "approval_path": "owner approves the plan",
    },
    "deploy": {
        "hosting": "local",
        "domain": "localhost",
        "tls": "n/a",
        "env_names": [],
        "build": "none",
        "migrate": "none",
        "backup": "copy",
        "restore": "copy",
        "ci_cd": "local",
        "rollback": "copy",
        "monitoring": "output",
        "smoke": "check",
    },
    "aftersales": {
        "support_window": "w",
        "escalation_owner": "owner",
        "logs": "l",
        "metrics": "m",
        "alerts": "a",
        "backup_schedule": "d",
        "restore_drill": "m",
        "update_policy": "m",
        "admin_recovery": "owner",
        "docs": "r",
    },
    "design": {
        "surface_class": "marketing",
        "contract": "clear",
        "references": ["ref"],
        "accessibility": "ok",
        "responsive": "390",
        "originality": "original",
        "review_owner": "owner",
    },
    "security": {
        "threat_model": "local",
        "assets": ["a"],
        "trust_boundaries": ["t"],
        "controls": ["c"],
        "dependency_scan": "s",
        "secret_scan": "s",
        "headers": "h",
        "incident": "i",
        "unresolved_severity": "none",
    },
}
DISCOVERY_ANSWERS = [
    ("idea", None, "Build a page"),
    ("users", None, "Visitors"),
    ("success", ["launch"], ""),
    ("must_haves", None, "One page"),
    ("non_goals", None, "No login"),
    ("constraints", ["none"], ""),
    ("ownership", ["owner"], ""),
    ("evidence", ["none"], ""),
    ("labels", ["new"], ""),
    ("name", None, "next-test"),
]


class NextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "proj"
        self.project = Project.init(self.root, "next-test")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def cli(self, *args: str, allow_rc: set[int] | None = None) -> int:
        result = subprocess.run(
            [sys.executable, "-m", "aperio", "--project", str(self.root), *args],
            check=False,
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(SRC)),
            timeout=60,
        )
        allowed = {0} | (allow_rc or set())
        self.assertIn(
            result.returncode,
            allowed,
            f"rc={result.returncode} for {args}: {result.stderr}",
        )
        return result.returncode

    def complete_gates(self) -> None:
        for question_id, choices, text in DISCOVERY_ANSWERS:
            command = ["discover", "answer", question_id]
            if choices:
                command += ["--choice", ",".join(choices)]
            if text:
                command += ["--text", text]
            self.cli(*command)
        dossier = self.root / "learning.json"
        dossier.write_text(json.dumps(DOSSIER), encoding="utf-8")
        self.cli("learn", "import", str(dossier), allow_rc={1})
        self.cli("learn", "proof", "--command", f'{sys.executable} -c "print(1)"')
        self.cli(
            "todo", "add", "Build page",
            "--deliverable", "page works",
            "--acceptance", "page exists",
        )
        listing = json.loads(
            subprocess.run(
                [sys.executable, "-m", "aperio", "--project", str(self.root), "todo", "list", "--json"],
                capture_output=True, text=True, check=True,
                cwd=str(ROOT), env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(SRC)),
            ).stdout
        )
        todo_id = listing["tasks"][0]["id"]
        self.cli("todo", "start", todo_id)
        readiness_path = self.root / "readiness.json"
        readiness_path.write_text(json.dumps(READINESS), encoding="utf-8")
        self.cli("readiness", "import", str(readiness_path))

    # ---- gate stages ----------------------------------------------------

    def test_fresh_project_points_at_learning_first(self) -> None:
        # cmd_plan checks learning before discovery; the advisor mirrors that
        # refusal order (a prior host review caught the mismatch).
        step = next_action(self.project)
        self.assertEqual(step["action"], "learn.import")
        self.assertIn("learn import", step["command"])

    def test_partly_answered_discovery_names_the_next_question(self) -> None:
        # Satisfy the gates cmd_plan checks before discovery so discovery is
        # genuinely the next refusal the agent would hit.
        dossier = self.root / "learning.json"
        dossier.write_text(json.dumps(DOSSIER), encoding="utf-8")
        self.cli("learn", "import", str(dossier), allow_rc={1})
        self.cli("learn", "proof", "--command", f'{sys.executable} -c "print(1)"')
        self.cli(
            "todo", "add", "Build page",
            "--deliverable", "page works",
            "--acceptance", "page exists",
        )
        listing = json.loads(
            subprocess.run(
                [sys.executable, "-m", "aperio", "--project", str(self.root), "todo", "list", "--json"],
                capture_output=True, text=True, check=True,
                cwd=str(ROOT), env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(SRC)),
            ).stdout
        )
        self.cli("todo", "start", listing["tasks"][0]["id"])
        readiness_path = self.root / "readiness.json"
        readiness_path.write_text(json.dumps(READINESS), encoding="utf-8")
        self.cli("readiness", "import", str(readiness_path))
        self.cli("discover", "answer", "idea", "--text", "Build a page")
        step = next_action(self.project)
        self.assertEqual(step["action"], "discover.answer")
        self.assertEqual(step["question"], "users")
        self.assertIn("1/10", step["why"])

    def test_unproven_dossier_points_at_learn_proof(self) -> None:
        for question_id, choices, text in DISCOVERY_ANSWERS:
            command = ["discover", "answer", question_id]
            if choices:
                command += ["--choice", ",".join(choices)]
            if text:
                command += ["--text", text]
            self.cli(*command)
        dossier = self.root / "learning.json"
        dossier.write_text(json.dumps(DOSSIER), encoding="utf-8")
        self.cli("learn", "import", str(dossier), allow_rc={1})
        step = next_action(self.project)
        self.assertEqual(step["action"], "learn.proof")
        self.assertIn("learn proof", step["command"])

    def test_imported_only_proof_points_at_learn_proof(self) -> None:
        # An imported dossier whose proof text is present but unproven must
        # still route to learn proof, mirroring the gate's rule.
        dossier = dict(DOSSIER)
        dossier["proof"] = {
            "command": "python3 -c \"print('x')\"",
            "exit_code": 0,
            "output_sha256": "0" * 64,
            "recorded_at": "2026-10-26T00:00:00Z",
        }
        for question_id, choices, text in DISCOVERY_ANSWERS:
            command = ["discover", "answer", question_id]
            if choices:
                command += ["--choice", ",".join(choices)]
            if text:
                command += ["--text", text]
            self.cli(*command)
        path = self.root / "learning.json"
        path.write_text(json.dumps(dossier), encoding="utf-8")
        self.cli("learn", "import", str(path), allow_rc={1})
        step = next_action(self.project)
        self.assertEqual(step["action"], "learn.proof")

    def test_empty_todo_points_at_todo_add(self) -> None:
        self.complete_discovery_only()
        dossier = self.root / "learning.json"
        dossier.write_text(json.dumps(DOSSIER), encoding="utf-8")
        self.cli("learn", "import", str(dossier), allow_rc={1})
        self.cli("learn", "proof", "--command", f'{sys.executable} -c "print(1)"')
        readiness_path = self.root / "readiness.json"
        readiness_path.write_text(json.dumps(READINESS), encoding="utf-8")
        self.cli("readiness", "import", str(readiness_path))
        step = next_action(self.project)
        self.assertEqual(step["action"], "todo.add")

    def test_pending_todo_points_at_todo_start(self) -> None:
        self.complete_gates()
        # complete_gates started task A; adding task B leaves B pending.
        # With A in progress the advisor stays on the loop, so defer A first:
        # then B is pending and todo.start is the next legal action.
        listing = json.loads(
            subprocess.run(
                [sys.executable, "-m", "aperio", "--project", str(self.root), "todo", "list", "--json"],
                capture_output=True, text=True, check=True,
                cwd=str(ROOT), env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(SRC)),
            ).stdout
        )
        active = listing["tasks"][0]["id"]
        self.cli(
            "todo", "add", "Second slice",
            "--deliverable", "second works",
            "--acceptance", "second exists",
        )
        self.cli("todo", "defer", active, "--by", "probe", "--reason", "probe")
        step = next_action(self.project)
        self.assertEqual(step["action"], "todo.start")
        self.assertIn("todo start", step["command"])
        self.assertIn("todo-", step["todo_id"])

    def test_all_gates_no_task_points_at_plan(self) -> None:
        self.complete_gates()
        step = next_action(self.project)
        self.assertEqual(step["action"], "plan")
        self.assertEqual(
            step["gates"],
            {"discovery": True, "learning": True, "todo_in_progress": 1},
        )

    # ---- loop stages -----------------------------------------------------

    def plan_and_write(self) -> tuple[str, str]:
        """Create an approved-ready planned task; returns (task_id, plan_id)."""
        self.complete_gates()
        plan = {
            "title": "Build a page",
            "request": "Build a page",
            "allowed_paths": ["site/"],
            "steps": [{"id": "w", "kind": "write", "path": "site/index.html", "content": "hello"}],
            "acceptance": [{"id": "c", "command": "test -f site/index.html"}],
        }
        path = self.root / "plan.json"
        path.write_text(json.dumps(plan), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "-m", "aperio", "--project", str(self.root), "plan", str(path)],
            capture_output=True, text=True, check=True,
            cwd=str(ROOT), env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(SRC)),
        )
        task_id, plan_id = result.stdout.splitlines()[0].split()[:2]
        return task_id, plan_id

    def test_planned_task_points_at_approve(self) -> None:
        _task_id, plan_id = self.plan_and_write()
        step = next_action(self.project)
        self.assertEqual(step["action"], "approve")
        self.assertEqual(step["plan_id"], plan_id)
        self.assertIn('--confirm "I approve this plan"', step["command"])

    def test_approved_task_points_at_run(self) -> None:
        task_id, plan_id = self.plan_and_write()
        self.cli("approve", plan_id, "--by", "owner", "--confirm", "I approve this plan")
        step = next_action(self.project)
        self.assertEqual(step["action"], "run")
        self.assertEqual(step["task_id"], task_id)
        self.assertIn("--actor", step["command"])

    def test_stale_readiness_binding_points_at_replan(self) -> None:
        # A prior host review caught that the advisor recommended approve/run
        # without checking the plan's gate bindings. Mutating the readiness
        # record after planning must route to re-plan, because approve and run
        # would refuse on the digest check.
        _task_id, _plan_id = self.plan_and_write()
        record_path = self.root / ".aperio" / "readiness.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["preflight"]["constraints"] = ["changed after planning"]
        record_path.write_text(json.dumps(record), encoding="utf-8")
        step = next_action(self.project)
        self.assertEqual(step["action"], "plan")
        self.assertIn("readiness record changed", step["why"])

    def test_stale_learning_binding_points_at_replan(self) -> None:
        _task_id, _plan_id = self.plan_and_write()
        self.cli("learn", "proof", "--command", f'{sys.executable} -c "print(42)"')
        step = next_action(self.project)
        self.assertEqual(step["action"], "plan")
        self.assertIn("learning dossier changed", step["why"])

    def test_applied_task_points_at_verify(self) -> None:
        task_id, plan_id = self.plan_and_write()
        self.cli("approve", plan_id, "--by", "owner", "--confirm", "I approve this plan")
        self.cli("run", task_id, "--actor", "builder")
        step = next_action(self.project)
        self.assertEqual(step["action"], "verify")
        self.assertEqual(step["task_id"], task_id)

    def test_verified_task_points_at_review(self) -> None:
        task_id, plan_id = self.plan_and_write()
        self.cli("approve", plan_id, "--by", "owner", "--confirm", "I approve this plan")
        self.cli("run", task_id, "--actor", "builder")
        self.cli("verify", task_id)
        step = next_action(self.project)
        self.assertEqual(step["action"], "review")
        self.assertIn("--verdict", step["command"])

    def test_reviewed_task_points_at_done(self) -> None:
        task_id, plan_id = self.plan_and_write()
        self.cli("approve", plan_id, "--by", "owner", "--confirm", "I approve this plan")
        self.cli("run", task_id, "--actor", "builder")
        self.cli("verify", task_id)
        self.cli("review", task_id, "--reviewer", "independent", "--verdict", "confirmed")
        step = next_action(self.project)
        self.assertEqual(step["action"], "done")

    def test_done_task_points_at_handoff(self) -> None:
        task_id, plan_id = self.plan_and_write()
        self.cli("approve", plan_id, "--by", "owner", "--confirm", "I approve this plan")
        self.cli("run", task_id, "--actor", "builder")
        self.cli("verify", task_id)
        self.cli("review", task_id, "--reviewer", "independent", "--verdict", "confirmed")
        self.cli("done", task_id)
        step = next_action(self.project)
        self.assertEqual(step["action"], "handoff")
        self.assertEqual(step["task_id"], task_id)

    def test_incomplete_full_readiness_blocks_done_recommendation(self) -> None:
        # A host review caught the advisor recommending done while cmd_done
        # requires FULL readiness: strip a non-preflight section after the
        # review and the advisor must route to readiness first.
        task_id, plan_id = self.plan_and_write()
        self.cli("approve", plan_id, "--by", "owner", "--confirm", "I approve this plan")
        self.cli("run", task_id, "--actor", "builder")
        self.cli("verify", task_id)
        self.cli("review", task_id, "--reviewer", "independent", "--verdict", "confirmed")
        record_path = self.root / ".aperio" / "readiness.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record.pop("aftersales")
        record_path.write_text(json.dumps(record), encoding="utf-8")
        step = next_action(self.project)
        self.assertEqual(step["action"], "readiness.import")
        self.assertIn("full project readiness", step["why"])

    def test_suggested_commands_carry_the_project_flag(self) -> None:
        # A host review caught bare commands that would act on the caller's
        # cwd instead of the advised project. Every command must target the
        # project root explicitly.
        _task_id, plan_id = self.plan_and_write()
        self.cli("approve", plan_id, "--by", "owner", "--confirm", "I approve this plan")
        step = next_action(self.project)
        # project.root is the resolved path (macOS /var -> /private/var).
        self.assertIn(f'--project "{self.project.root}"', step["command"])

    def test_preflight_gap_beats_pending_todo_start(self) -> None:
        # cmd_plan reaches _require_preflight before _active_todo, so with a
        # pending todo AND broken preflight the advisor must name readiness
        # first (a host review flagged the inverted order).
        dossier = self.root / "learning.json"
        dossier.write_text(json.dumps(DOSSIER), encoding="utf-8")
        self.cli("learn", "import", str(dossier), allow_rc={1})
        self.cli("learn", "proof", "--command", f'{sys.executable} -c "print(1)"')
        self.cli(
            "todo", "add", "Build page",
            "--deliverable", "page works",
            "--acceptance", "page exists",
        )
        # No readiness record at all: preflight is the first refusal.
        step = next_action(self.project)
        self.assertEqual(step["action"], "readiness.import")
        self.assertIn("pre-flight", step["why"])

    def test_applied_task_routes_to_verify_even_when_a_gate_drifted(self) -> None:
        # cmd_verify does not re-check the plan gates, so an applied task must
        # route to verify even if learning became unready after the run (a
        # host review flagged gate-first routing misadvising this stage).
        task_id, plan_id = self.plan_and_write()
        self.cli("approve", plan_id, "--by", "owner", "--confirm", "I approve this plan")
        self.cli("run", task_id, "--actor", "builder")
        record_path = self.root / ".aperio" / "learning.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["competency"]["verdict"] = "not_demonstrated"
        record_path.write_text(json.dumps(record), encoding="utf-8")
        step = next_action(self.project)
        self.assertEqual(step["action"], "verify")
        self.assertEqual(step["task_id"], task_id)

    def test_approved_task_routes_to_run_when_todo_deferred(self) -> None:
        # cmd_approve has no todo check, so a planned task routes to approve
        # even when no todo is in progress; and cmd_run checks the plan's
        # LINKED todo (in progress or accepted), not the global count. A
        # deferred linked todo must route to the linked task's recovery, not
        # to a generic todo.start (host review flagged both).
        task_id, plan_id = self.plan_and_write()
        listing = json.loads(
            subprocess.run(
                [sys.executable, "-m", "aperio", "--project", str(self.root), "todo", "list", "--json"],
                capture_output=True, text=True, check=True,
                cwd=str(ROOT), env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(SRC)),
            ).stdout
        )
        linked = listing["tasks"][0]["id"]
        self.cli("todo", "defer", linked, "--by", "probe", "--reason", "probe")
        step = next_action(self.project)
        # planned + no todo in progress: approve has no todo gate
        self.assertEqual(step["action"], "approve")
        self.cli("approve", plan_id, "--by", "owner", "--confirm", "I approve this plan")
        step = next_action(self.project)
        # approved + linked todo deferred: run would refuse
        self.assertEqual(step["action"], "recover")
        self.assertEqual(step["task_id"], task_id)

    def test_failed_task_inspection_skips_gates(self) -> None:
        # The recover routing suggests aperio status, which enforces no gates;
        # a failed task with a broken gate must still route to the inspection.
        task_id, plan_id = self.plan_and_write()
        self.cli("approve", plan_id, "--by", "owner", "--confirm", "I approve this plan")
        record_path = self.root / ".aperio" / "readiness.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record.pop("preflight")
        record_path.write_text(json.dumps(record), encoding="utf-8")
        task = self.project.get_task(task_id)
        task.status = "failed"
        self.project.put_task(task)
        step = next_action(self.project)
        self.assertEqual(step["action"], "recover")
        self.assertEqual(step["task_id"], task_id)

    # ---- safety ----------------------------------------------------------

    def test_printed_commands_use_the_real_binary_name(self) -> None:
        # A host review caught every suggested command saying "apero" while
        # the installed binary is "aperio"; the stage tests never noticed
        # because they invoke the CLI through -m, not through the printed
        # strings. Walk the loop and check every printed command prefix.
        step = next_action(self.project)
        self.assertTrue(step["command"].startswith("aperio "), step["command"])
        task_id, plan_id = self.plan_and_write()
        for command_args in (
            ("approve", plan_id, "--by", "owner", "--confirm", "I approve this plan"),
            ("run", task_id, "--actor", "builder"),
            ("verify", task_id),
            ("review", task_id, "--reviewer", "independent", "--verdict", "confirmed"),
            ("done", task_id),
        ):
            self.cli(*command_args)
            step = next_action(self.project)
            self.assertTrue(step["command"].startswith("aperio "), step["command"])
            self.assertNotIn("apero ", step["command"])

    def test_next_writes_nothing(self) -> None:
        def snapshot() -> dict[str, bytes]:
            data: dict[str, bytes] = {}
            for path in sorted(self.root.rglob("*")):
                if path.is_file():
                    data[str(path.relative_to(self.root))] = path.read_bytes()
            return data

        # The advisor itself must be pure: snapshot around next_action calls
        # only; the discover answer in between is the test's own write.
        before = snapshot()
        next_action(self.project)
        after = snapshot()
        self.assertEqual(before, after, "next_action must not write any state")
        self.cli("discover", "answer", "idea", "--text", "x")
        before = snapshot()
        step = next_action(self.project)
        after = snapshot()
        self.assertEqual(before, after, "next_action must not write any state")
        # Learning precedes discovery in cmd_plan's refusal order, and no
        # dossier exists here, so the advisor must still point at learn import
        # even though discovery is now partly answered.
        self.assertEqual(step["action"], "learn.import")

    def test_failed_task_routes_to_recover(self) -> None:
        task_id, plan_id = self.plan_and_write()
        self.cli("approve", plan_id, "--by", "owner", "--confirm", "I approve this plan")
        task = self.project.get_task(task_id)
        task.status = "failed"
        self.project.put_task(task)
        step = next_action(self.project)
        self.assertEqual(step["action"], "recover")
        self.assertEqual(step["task_id"], task_id)

    def complete_discovery_only(self) -> None:
        for question_id, choices, text in DISCOVERY_ANSWERS:
            command = ["discover", "answer", question_id]
            if choices:
                command += ["--choice", ",".join(choices)]
            if text:
                command += ["--text", text]
            self.cli(*command)


if __name__ == "__main__":
    unittest.main()
