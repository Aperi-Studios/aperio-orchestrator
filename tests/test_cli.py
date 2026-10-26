from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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
