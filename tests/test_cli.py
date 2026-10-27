from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from aperio.readiness import import_readiness
from aperio.store import Project

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="aperio-cli-")
        self.root = Path(self.temp.name)
        self.env = os.environ.copy()
        self.env["PYTHONPATH"] = str(SRC)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def learning_dossier(self) -> dict:
        return {
            "schema": 1,
            "stack": {
                "surface": "website",
                "runtime": "Python 3.14",
                "framework": "standard library",
                "package_manager": "none",
                "database": "none",
                "hosting": "local",
                "versions": {"python": "3.14"},
                "constraints": [],
            },
            "sources": [
                {
                    "title": "Python documentation",
                    "url": "https://docs.python.org/3/",
                    "kind": "official_docs",
                    "version": "3.14",
                    "accessed": "2026-10-26",
                    "official": True,
                }
            ],
            "skills": [],
            "skill_gap": {"needed": False, "reason": "The standard library is sufficient for this CLI fixture."},
            "mcps": [],
            "proof": {
                "command": "python3 -c \"print('proof')\"",
                "exit_code": 0,
                "output_sha256": "0" * 64,
                "recorded_at": "2026-10-26T00:00:00Z",
            },
            "teachback": {
                "agent": "agent",
                "summary": "I can explain the Python runtime, the plan format, the acceptance check, and the limits of this fixture.",
                "uncertainties": [],
            },
            "competency": {
                "agent": "agent",
                "verdict": "demonstrated",
                "evidence": "The fixture's local proof command and acceptance check are recorded.",
                "recorded_at": "2026-10-26T00:00:00Z",
            },
        }

    def cli(self, *args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "aperio", "--project", str(self.root), *args],
            check=False,
            input=input_text,
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            env=self.env,
            timeout=30,
        )

    def init(self) -> None:
        result = self.cli("init", str(self.root), "--name", "cli-test")
        self.assertEqual(result.returncode, 0, result.stderr)
        dossier = self.root / "learning.json"
        dossier.write_text(json.dumps(self.learning_dossier()), encoding="utf-8")
        result = self.cli("learn", "import", str(dossier))
        self.assertEqual(result.returncode, 1, result.stderr)
        result = self.cli("learn", "proof", "--command", f'{sys.executable} -c "print(1)"')
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.cli(
            "todo",
            "add",
            "Build the requested page",
            "--deliverable",
            "The requested page is working",
            "--acceptance",
            "The page exists and the acceptance command passes",
            "--json",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        todo_id = json.loads(result.stdout)["id"]
        result = self.cli("todo", "start", todo_id)
        self.assertEqual(result.returncode, 0, result.stderr)
        readiness = {
            "schema": 1,
            "preflight": {
                "audience": "Test users",
                "success_measure": "The test page renders",
                "features": ["A test page"],
                "out_of_scope": ["Production deployment"],
                "integrations": ["None"],
                "constraints": ["Local fixture"],
                "review_owner": "owner",
                "approval_path": "Owner approves the plan",
            },
            "deploy": {
                "hosting": "Local fixture",
                "domain": "localhost",
                "tls": "Not applicable",
                "env_names": [],
                "build": "python3 -m compileall src",
                "migrate": "No migration",
                "backup": "Copy the fixture",
                "restore": "Restore the fixture copy",
                "ci_cd": "Local tests",
                "rollback": "Restore the previous copy",
                "monitoring": "Command output",
                "smoke": "Run the acceptance check",
            },
            "aftersales": {
                "support_window": "Fixture only",
                "escalation_owner": "owner",
                "logs": "Local output",
                "metrics": "Acceptance result",
                "alerts": "Owner notification",
                "backup_schedule": "Daily",
                "restore_drill": "Monthly",
                "update_policy": "Monthly review",
                "admin_recovery": "Owner procedure",
                "docs": "README",
            },
            "design": {
                "surface_class": "marketing",
                "contract": "Clear hierarchy and restrained type",
                "references": ["Owner example"],
                "accessibility": "Keyboard and contrast checked",
                "responsive": "390x844 and 1440x900",
                "originality": "No copied composition",
                "review_owner": "owner",
            },
            "security": {
                "threat_model": "Local fixture: form abuse and path escape",
                "assets": ["Test data"],
                "trust_boundaries": ["Browser to server"],
                "controls": ["Server-side validation"],
                "dependency_scan": "Approved scan",
                "secret_scan": "Approved scan",
                "headers": "Checked on the deployed shape",
                "incident": "Owner disables the form",
                "unresolved_severity": "none",
            },
        }
        readiness_path = self.root / "readiness.json"
        readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
        import_readiness(Project.open(self.root), str(readiness_path))

    def complete_discovery(self) -> None:
        rows = [
            ("idea", [], "Build a page"),
            ("users", [], "Visitors"),
            ("success", ["launch"], ""),
            ("must_haves", [], "One page"),
            ("non_goals", [], "No login"),
            ("constraints", ["none"], ""),
            ("ownership", ["owner"], ""),
            ("evidence", ["none"], ""),
            ("labels", ["new"], ""),
            ("name", [], "cli-test"),
        ]
        for question_id, choices, text in rows:
            command = ["discover", "answer", question_id]
            if choices:
                command += ["--choice", ",".join(choices)]
            if text:
                command += ["--text", text]
            result = self.cli(*command)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_full_cli_flow(self) -> None:
        self.init()
        self.complete_discovery()
        (self.root / "notes.md").write_text("owner notes\n", encoding="utf-8")
        result = self.cli("evidence", "add", "notes.md", "--label", "Brief")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.cli("ask", "Build a page")
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = {
            "title": "Build a page",
            "request": "Build a page",
            "allowed_paths": ["site/"],
            "steps": [
                {"id": "write", "kind": "write", "path": "site/index.html", "content": "hello"},
            ],
            "acceptance": [
                {
                    "id": "check",
                    "command": f'{sys.executable} -c "from pathlib import Path; assert Path(\'site/index.html\').read_text() == \'hello\'"',
                }
            ],
        }
        plan_path = self.root / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        result = self.cli("plan", str(plan_path))
        self.assertEqual(result.returncode, 0, result.stderr)
        first = result.stdout.splitlines()[0].split()
        task_id, plan_id = first[0], first[1]

        result = self.cli("run", task_id)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

        result = self.cli("approve", plan_id, "--by", "owner", "--confirm", "I approve this plan")
        self.assertEqual(result.returncode, 0, result.stderr)

        result = self.cli("run", task_id)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.root / "site/index.html").read_text(), "hello")

        result = self.cli("verify", task_id)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        result = self.cli("review", task_id, "--reviewer", "qa", "--verdict", "confirmed")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        result = self.cli("done", task_id)
        self.assertEqual(result.returncode, 0, result.stderr)

        result = self.cli("approve", plan_id, "--by", "owner", "--confirm", "I approve this plan")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

        result = self.cli("status", task_id, "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "done")

        result = self.cli("handoff", task_id, "--print")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("## Verification", result.stdout)
        self.assertIn("## Evidence files", result.stdout)
        self.assertIn("done", result.stdout)

    def test_learning_change_invalidates_the_plan(self) -> None:
        self.init()
        self.complete_discovery()
        plan = {
            "title": "Learning binding",
            "request": "Prove the learning digest binding",
            "allowed_paths": ["site/"],
            "steps": [{"id": "write", "kind": "write", "path": "site/a.txt", "content": "a"}],
            "acceptance": [{"id": "check", "command": f"{sys.executable} -c \"pass\""}],
        }
        path = self.root / "plan.json"
        path.write_text(json.dumps(plan), encoding="utf-8")
        result = self.cli("plan", str(path))
        self.assertEqual(result.returncode, 0, result.stderr)
        plan_id = result.stdout.split()[1]
        result = self.cli("learn", "proof", "--command", f'{sys.executable} -c "print(2)"')
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.cli(
            "approve", plan_id, "--by", "owner", "--confirm", "I approve this plan"
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("learning dossier changed", result.stderr)

    def test_plan_without_learning_is_refused(self) -> None:
        result = self.cli("init", str(self.root), "--name", "cli-test")
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = {
            "title": "No learning",
            "request": "No learning",
            "allowed_paths": ["site/"],
            "steps": [{"id": "write", "kind": "write", "path": "site/a.txt", "content": "a"}],
            "acceptance": [{"id": "check", "command": f"{sys.executable} -c \"pass\""}],
        }
        path = self.root / "plan.json"
        path.write_text(json.dumps(plan), encoding="utf-8")
        result = self.cli("plan", str(path))
        self.assertEqual(result.returncode, 2)
        self.assertIn("learning dossier is required", result.stderr)

    def test_approve_and_run_without_learning_are_refused(self) -> None:
        # the gate fires before plan/task resolution, so bogus IDs still refuse
        result = self.cli("init", str(self.root), "--name", "cli-test")
        self.assertEqual(result.returncode, 0, result.stderr)
        for args in (
            ("approve", "plan-zzz", "--confirm", "I approve this plan"),
            ("run", "task-zzz", "--actor", "agent"),
        ):
            result = self.cli(*args)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("learning dossier is required", result.stderr)

    def test_plan_without_todo_is_refused(self) -> None:
        result = self.cli("init", str(self.root), "--name", "cli-test")
        self.assertEqual(result.returncode, 0, result.stderr)
        dossier = self.root / "learning.json"
        dossier.write_text(json.dumps(self.learning_dossier()), encoding="utf-8")
        result = self.cli("learn", "import", str(dossier))
        self.assertEqual(result.returncode, 1, result.stderr)
        result = self.cli("learn", "proof", "--command", f'{sys.executable} -c "print(1)"')
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = {
            "title": "No todo",
            "request": "No todo",
            "allowed_paths": ["site/"],
            "steps": [{"id": "write", "kind": "write", "path": "site/a.txt", "content": "a"}],
            "acceptance": [{"id": "check", "command": f"{sys.executable} -c \"pass\""}],
        }
        path = self.root / "plan.json"
        path.write_text(json.dumps(plan), encoding="utf-8")
        result = self.cli("plan", str(path))
        self.assertEqual(result.returncode, 2)
        self.assertIn("todo list is empty", result.stderr)

    def test_plan_without_preflight_is_refused(self) -> None:
        result = self.cli("init", str(self.root), "--name", "cli-test")
        self.assertEqual(result.returncode, 0, result.stderr)
        dossier = self.root / "learning.json"
        dossier.write_text(json.dumps(self.learning_dossier()), encoding="utf-8")
        result = self.cli("learn", "import", str(dossier))
        self.assertEqual(result.returncode, 1, result.stderr)
        result = self.cli("learn", "proof", "--command", f'{sys.executable} -c "print(1)"')
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.cli(
            "todo",
            "add",
            "Build the requested page",
            "--deliverable",
            "The requested page is working",
            "--acceptance",
            "The page exists and the acceptance command passes",
            "--json",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        todo_id = json.loads(result.stdout)["id"]
        result = self.cli("todo", "start", todo_id)
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = {
            "title": "No preflight",
            "request": "No preflight",
            "allowed_paths": ["site/"],
            "steps": [{"id": "write", "kind": "write", "path": "site/a.txt", "content": "a"}],
            "acceptance": [{"id": "check", "command": f"{sys.executable} -c \"pass\""}],
        }
        path = self.root / "plan.json"
        path.write_text(json.dumps(plan), encoding="utf-8")
        result = self.cli("plan", str(path))
        self.assertEqual(result.returncode, 2)
        self.assertIn("pre-flight readiness is required", result.stderr)

    def test_run_rejects_readiness_that_vanished_after_approval(self) -> None:
        # F1: readiness used to be validated only at plan time, so a record
        # deleted or replaced after approval still let `run` execute.
        self.init()
        self.complete_discovery()
        plan = {
            "title": "Readiness vanishes after approval",
            "request": "Readiness vanishes after approval",
            "allowed_paths": ["site/"],
            "steps": [{"id": "write", "kind": "write", "path": "site/a.txt", "content": "a"}],
            "acceptance": [{"id": "check", "command": f"{sys.executable} -c \"pass\""}],
        }
        path = self.root / "plan.json"
        path.write_text(json.dumps(plan), encoding="utf-8")
        result = self.cli("plan", str(path))
        self.assertEqual(result.returncode, 0, result.stderr)
        task_id, plan_id = result.stdout.splitlines()[0].split()[:2]
        result = self.cli("approve", plan_id, "--by", "owner", "--confirm", "I approve this plan")
        self.assertEqual(result.returncode, 0, result.stderr)
        (self.root / ".aperio" / "readiness.json").unlink()
        result = self.cli("run", task_id)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        # The digest binding refuses first ("readiness record is missing");
        # either refusal means the vanished record blocked the run.
        self.assertTrue(
            "pre-flight readiness is required" in result.stderr
            or "readiness record is missing" in result.stderr,
            result.stderr,
        )

    def test_readiness_change_invalidates_the_plan(self) -> None:
        # The plan pins the readiness record it was planned against (like the
        # learning and discovery bindings): a record edited between plan and
        # approval must invalidate the plan, not silently pass with the new
        # facts.
        self.init()
        self.complete_discovery()
        plan = {
            "title": "Readiness binding",
            "request": "Prove the readiness digest binding",
            "allowed_paths": ["site/"],
            "steps": [{"id": "write", "kind": "write", "path": "site/a.txt", "content": "a"}],
            "acceptance": [{"id": "check", "command": f"{sys.executable} -c \"pass\""}],
        }
        path = self.root / "plan.json"
        path.write_text(json.dumps(plan), encoding="utf-8")
        result = self.cli("plan", str(path))
        self.assertEqual(result.returncode, 0, result.stderr)
        plan_id = result.stdout.split()[1]
        record_path = self.root / ".aperio" / "readiness.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["preflight"]["constraints"] = ["weakened after planning"]
        record_path.write_text(json.dumps(record), encoding="utf-8")
        result = self.cli(
            "approve", plan_id, "--by", "owner", "--confirm", "I approve this plan"
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("readiness record changed", result.stderr)

    def test_plan_without_readiness_binding_is_refused_at_approval(self) -> None:
        # A plan body that predates the readiness binding (no digest field)
        # cannot be approved: the owner must re-plan against the current
        # record, mirroring the learning-binding migration rule.
        self.init()
        self.complete_discovery()
        plan = {
            "title": "No readiness binding",
            "request": "Prove the readiness binding is required",
            "allowed_paths": ["site/"],
            "steps": [{"id": "write", "kind": "write", "path": "site/a.txt", "content": "a"}],
            "acceptance": [{"id": "check", "command": f"{sys.executable} -c \"pass\""}],
        }
        path = self.root / "plan.json"
        path.write_text(json.dumps(plan), encoding="utf-8")
        result = self.cli("plan", str(path))
        self.assertEqual(result.returncode, 0, result.stderr)
        plan_id = result.stdout.split()[1]
        plan_state_path = self.root / ".aperio" / "plans" / f"{plan_id}.json"
        plan_state = json.loads(plan_state_path.read_text(encoding="utf-8"))
        plan_state["readiness_digest"] = ""
        plan_state_path.write_text(json.dumps(plan_state), encoding="utf-8")
        result = self.cli(
            "approve", plan_id, "--by", "owner", "--confirm", "I approve this plan"
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("plan has no readiness binding", result.stderr)

    def test_plan_without_discovery_is_refused(self) -> None:
        self.init()
        plan = {
            "title": "No discovery",
            "request": "No discovery",
            "allowed_paths": ["site/"],
            "steps": [{"id": "write", "kind": "write", "path": "site/a.txt", "content": "a"}],
            "acceptance": [{"id": "check", "command": f"{sys.executable} -c \"pass\""}],
        }
        path = self.root / "plan.json"
        path.write_text(json.dumps(plan), encoding="utf-8")
        result = self.cli("plan", str(path))
        self.assertEqual(result.returncode, 2)
        self.assertIn("discovery is required before planning", result.stderr)

    def test_plan_with_malformed_types_is_rejected(self) -> None:
        self.init()
        self.complete_discovery()
        base = {
            "title": "Bad plan",
            "request": "Bad plan",
            "allowed_paths": ["site/"],
            "steps": [{"id": "write", "kind": "write", "path": "site/a.txt", "content": "a"}],
            "acceptance": [{"id": "check", "command": f"{sys.executable} -c \"pass\""}],
        }
        cases = [
            {**base, "allowed_paths": "site/"},
            {**base, "steps": {"id": "write"}},
            {**base, "acceptance": {"id": "check"}},
        ]
        for number, plan in enumerate(cases):
            path = self.root / f"bad-{number}.json"
            path.write_text(json.dumps(plan), encoding="utf-8")
            result = self.cli("plan", str(path))
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("must be a list", result.stderr)
        self.assertEqual(list((self.root / ".aperio" / "plans").glob("*.json")), [])

    def test_project_status_json_includes_discovery(self) -> None:
        self.init()
        self.complete_discovery()
        result = self.cli("status", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["project"], str(self.root.resolve()))
        self.assertTrue(data["discovery"]["ready"])
        self.assertEqual(data["tasks"], [])

    def test_plan_without_acceptance_is_rejected(self) -> None:
        self.init()
        plan = {
            "title": "No checks",
            "request": "No checks",
            "allowed_paths": ["site/"],
            "steps": [{"id": "write", "kind": "write", "path": "site/a.txt", "content": "a"}],
            "acceptance": [],
        }
        path = self.root / "plan.json"
        path.write_text(json.dumps(plan), encoding="utf-8")
        result = self.cli("plan", str(path))
        self.assertEqual(result.returncode, 2)
        self.assertIn("acceptance", result.stderr)

    def test_review_help_lists_only_supported_hosts(self) -> None:
        # D2: the help text used to advertise adapters that _review_command
        # rejects at runtime.
        result = self.cli("review", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        help_text = " ".join(result.stdout.split())
        self.assertIn("claude, codex, dsh, goose", help_text)
        self.assertNotIn("opencode", help_text)

    def test_hosts_command_is_read_only(self) -> None:
        self.init()
        result = self.cli("hosts")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("claude", result.stdout)

    def test_project_outside_init_is_refused(self) -> None:
        result = self.cli("doctor")
        self.assertEqual(result.returncode, 2)
        self.assertIn("not an Aperio project", result.stderr)


if __name__ == "__main__":
    unittest.main()
