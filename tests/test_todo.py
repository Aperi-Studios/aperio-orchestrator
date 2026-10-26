from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from aperio.store import Project
from aperio.todo import TodoError, accept, add, defer, start, status

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


class TodoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="aperio-todo-")
        self.root = Path(self.temp.name) / "project"
        self.project = Project.init(self.root, name="todo-test")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def task(self, title: str = "Initialize the project") -> dict:
        return add(
            self.project,
            title,
            deliverable="A working initialization step",
            acceptance="The initialization command exits 0",
        )

    def test_add_requires_deliverable_and_acceptance(self) -> None:
        with self.assertRaises(TodoError):
            add(self.project, "Task", deliverable="", acceptance="check")
        with self.assertRaises(TodoError):
            add(self.project, "Task", deliverable="deliverable", acceptance="")

    def test_next_task_cannot_start_before_acceptance(self) -> None:
        first = self.task("Initialize")
        second = self.task("Build the shell")
        start(self.project, first["id"])
        with self.assertRaises(TodoError):
            start(self.project, second["id"])
        accept(
            self.project,
            first["id"],
            by="owner",
            evidence="initialization command exit 0",
            confirm="I accept this task",
        )
        started = start(self.project, second["id"])
        self.assertEqual(started["status"], "in_progress")

    def test_accept_requires_evidence_and_confirmation(self) -> None:
        task = self.task()
        start(self.project, task["id"])
        with self.assertRaises(TodoError):
            accept(self.project, task["id"], by="owner", evidence="", confirm="I accept this task")
        with self.assertRaises(TodoError):
            accept(self.project, task["id"], by="owner", evidence="test", confirm="yes")
        accepted = accept(
            self.project,
            task["id"],
            by="owner",
            evidence="test output",
            confirm="I accept this task",
        )
        self.assertEqual(accepted["status"], "accepted")
        self.assertEqual(accepted["evidence"], "test output")

    def test_deferred_task_unblocks_the_next(self) -> None:
        first = self.task("Initialize")
        second = self.task("Build the shell")
        defer(self.project, first["id"], by="owner", reason="Waiting for the target stack decision")
        started = start(self.project, second["id"])
        self.assertEqual(started["status"], "in_progress")

    def test_status_counts(self) -> None:
        first = self.task()
        start(self.project, first["id"])
        result = status(self.project)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["in_progress"], 1)
        self.assertEqual(result["tasks"][0]["title"], "Initialize the project")

    def test_cli_todo_flow(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC)
        base = [sys.executable, "-m", "aperio", "--project", str(self.root)]
        result = subprocess.run(
            base
            + [
                "todo",
                "add",
                "Initialize",
                "--deliverable",
                "A working initialization",
                "--acceptance",
                "The command exits 0",
                "--json",
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(ROOT),
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        task = json.loads(result.stdout)
        result = subprocess.run(
            base + ["todo", "start", task["id"], "--json"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(ROOT),
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run(
            base
            + [
                "todo",
                "accept",
                task["id"],
                "--by",
                "owner",
                "--evidence",
                "exit 0",
                "--confirm",
                "I accept this task",
                "--json",
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(ROOT),
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "accepted")
        result = subprocess.run(
            base + ["todo", "list", "--json"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(ROOT),
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["accepted"], 1)


if __name__ == "__main__":
    unittest.main()
