from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from aperio.cli import cmd_plan
from aperio.discovery import (
    DiscoveryError,
    answer_question,
    next_question,
    parse_choices,
    status,
    summary,
)
from aperio.store import Project

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


class DiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="aperio-discovery-")
        self.root = Path(self.temp.name) / "project"
        self.project = Project.init(self.root, name="discovery-test")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def complete(self) -> None:
        answers = [
            ("idea", [], "A small portfolio site"),
            ("users", [], "Potential clients; they should contact me"),
            ("success", ["orders"], ""),
            ("must_haves", [], "One page, contact form, mobile layout"),
            ("non_goals", [], "No blog, no login"),
            ("constraints", ["deadline", "language"], ""),
            ("ownership", ["owner"], ""),
            ("evidence", ["none"], ""),
            ("labels", ["new", "seo"], ""),
            ("name", [], "Portfolio"),
        ]
        for question_id, choices, text in answers:
            answer_question(self.project, question_id, choices=choices, text=text)

    def test_next_creates_persistent_state(self) -> None:
        question = next_question(self.project)
        assert question is not None
        self.assertEqual(question.id, "idea")
        self.assertTrue((self.root / ".aperio" / "discovery.json").is_file())

    def test_answer_and_status(self) -> None:
        answer_question(self.project, "idea", text="A small portfolio site")
        progress = status(self.project)
        self.assertEqual(progress["answered"], 1)
        self.assertFalse(progress["ready"])
        self.assertEqual(progress["next"], "users")
        reopened = Project.open(self.root)
        self.assertEqual(status(reopened)["answered"], 1)

    def test_choice_validation(self) -> None:
        question = next_question(self.project)
        assert question is not None
        while question is not None and question.id != "constraints":
            answer_question(
                self.project,
                question.id,
                choices=[question.choices[0].value] if question.choices else [],
                text="" if question.choices else "answer",
            )
            question = next_question(self.project)
        assert question is not None
        values = parse_choices(question, "1, 3")
        self.assertEqual(values, ["deadline", "brand"])
        with self.assertRaises(DiscoveryError):
            parse_choices(question, "99")

    def test_not_sure_is_research_not_ready(self) -> None:
        answer_question(self.project, "idea", text="A small portfolio site")
        answer_question(self.project, "users", text="Potential clients")
        answer_question(self.project, "success", choices=["not_sure"])
        progress = status(self.project)
        self.assertEqual(progress["research"], 1)
        self.assertFalse(progress["ready"])
        question = next_question(self.project)
        assert question is not None
        self.assertEqual(question.id, "success")

    def test_complete_discovery_is_ready(self) -> None:
        self.complete()
        progress = status(self.project)
        self.assertTrue(progress["ready"])
        text = summary(self.project)
        self.assertIn("A small portfolio site", text)
        self.assertIn("Portfolio", text)

    def test_plan_refuses_incomplete_discovery(self) -> None:
        plan = ROOT / "examples" / "demo-site-plan.json"
        args = argparse.Namespace(project=str(self.root), file=str(plan))
        answer_question(self.project, "idea", text="A small portfolio site")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            with self.assertRaises(DiscoveryError):
                cmd_plan(args)
            self.complete()
            self.assertEqual(cmd_plan(args), 0)

    def test_cli_discover(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC)
        first = subprocess.run(
            [sys.executable, "-m", "aperio", "--project", str(self.root), "discover", "next", "--json"],
            check=False,
            capture_output=True,
            text=True,
            env=env,
            cwd=str(ROOT),
            timeout=30,
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        payload = json.loads(first.stdout)
        self.assertEqual(payload["question"]["id"], "idea")
        self.assertEqual(payload["question"]["options"], [])
        second = subprocess.run(
            [
                sys.executable,
                "-m",
                "aperio",
                "--project",
                str(self.root),
                "discover",
                "answer",
                "idea",
                "--text",
                "A small portfolio site",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
            cwd=str(ROOT),
            timeout=30,
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("idea recorded", second.stdout)
        status_cmd = subprocess.run(
            [sys.executable, "-m", "aperio", "--project", str(self.root), "discover", "status", "--json"],
            check=False,
            capture_output=True,
            text=True,
            env=env,
            cwd=str(ROOT),
            timeout=30,
        )
        self.assertEqual(status_cmd.returncode, 0, status_cmd.stderr)
        self.assertEqual(json.loads(status_cmd.stdout)["answered"], 1)


if __name__ == "__main__":
    unittest.main()
