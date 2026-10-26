from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, timedelta
from pathlib import Path

from aperio.cli import cmd_approve, cmd_plan
from aperio.discovery import (
    WAIVER_CONFIRM,
    DiscoveryError,
    answer_question,
    format_status,
    next_question,
    parse_choices,
    status,
    summary,
    waive_question,
)
from aperio.store import Project

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FUTURE = (date.today() + timedelta(days=30)).isoformat()


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
            ("labels", ["new"], ""),
            ("name", [], "Portfolio"),
        ]
        for question_id, choices, text in answers:
            answer_question(self.project, question_id, choices=choices, text=text)

    def test_next_is_read_only(self) -> None:
        question = next_question(self.project)
        assert question is not None
        self.assertEqual(question.id, "idea")
        self.assertFalse((self.root / ".aperio" / "discovery.json").exists())
        answer_question(self.project, "idea", text="A small portfolio site")
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

    def test_conditional_commerce_questions_load(self) -> None:
        for question_id, choices, text in [
            ("idea", [], "A jersey store"),
            ("users", [], "Gen-Z sports fans"),
            ("success", ["orders"], ""),
            ("must_haves", [], "Products, cart, COD"),
            ("non_goals", [], "No accounts yet"),
            ("constraints", ["budget"], ""),
            ("ownership", ["owner"], ""),
            ("evidence", ["none"], ""),
            ("labels", ["commerce"], ""),
        ]:
            answer_question(self.project, question_id, choices=choices, text=text)
        progress = status(self.project)
        self.assertEqual(progress["total"], 13)
        question = next_question(self.project)
        assert question is not None
        self.assertEqual(question.id, "commerce_flow")
        answer_question(self.project, "commerce_flow", choices=["cart_cod"])
        answer_question(self.project, "commerce_delivery", choices=["zone"])
        answer_question(self.project, "commerce_returns", choices=["business"])
        answer_question(self.project, "name", text="Jersey Valley")
        self.assertTrue(status(self.project)["ready"])

    def test_waiver_requires_exact_confirmation(self) -> None:
        answer_question(self.project, "idea", text="A small site")
        with self.assertRaises(DiscoveryError):
            waive_question(
                self.project,
                "users",
                by="owner",
                risk="unknown",
                confirm="yes",
                review_at=FUTURE,
            )
        waiver = waive_question(
            self.project,
            "users",
            by="owner",
            risk="user is not known yet",
            confirm=WAIVER_CONFIRM,
            review_at=FUTURE,
        )
        self.assertEqual(waiver["status"], "waived")
        self.assertIn("users", status(self.project)["waived"])
        self.assertIn("WAIVED", summary(self.project))

    def test_answered_question_cannot_be_waived(self) -> None:
        answer_question(self.project, "idea", text="A small site")
        with self.assertRaises(DiscoveryError):
            waive_question(
                self.project,
                "idea",
                by="owner",
                risk="already answered",
                confirm=WAIVER_CONFIRM,
                review_at=FUTURE,
            )

    def test_labels_cannot_be_waived(self) -> None:
        with self.assertRaises(DiscoveryError):
            waive_question(
                self.project,
                "labels",
                by="owner",
                risk="skip module choice",
                confirm=WAIVER_CONFIRM,
                review_at=FUTURE,
            )

    def test_waiver_allows_plan_and_warns(self) -> None:
        for question_id, choices, text in [
            ("idea", [], "A small site"),
            ("users", [], "Visitors"),
            ("success", ["launch"], ""),
            ("must_haves", [], "One page"),
            ("non_goals", [], "No login"),
            ("constraints", ["none"], ""),
            ("ownership", ["owner"], ""),
            ("evidence", ["none"], ""),
            ("labels", ["new"], ""),
        ]:
            answer_question(self.project, question_id, choices=choices, text=text)
        waive_question(
            self.project,
            "name",
            by="owner",
            risk="working name is not decided",
            confirm=WAIVER_CONFIRM,
            review_at=FUTURE,
        )
        self.assertTrue(status(self.project)["ready"])
        self.assertIn("1 waived", format_status(self.project))
        plan = ROOT / "examples" / "demo-site-plan.json"
        args = argparse.Namespace(project=str(self.root), file=str(plan))
        output = io.StringIO()
        errors = io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            self.assertEqual(cmd_plan(args), 0)
        self.assertIn("discovery waivers accepted: name", errors.getvalue())

    def test_parse_choices_rejects_superscript_and_duplicates(self) -> None:
        question = next_question(self.project)
        assert question is not None
        with self.assertRaises(DiscoveryError):
            parse_choices(question, "1,1")
        with self.assertRaises(DiscoveryError):
            parse_choices(question, "²")

    def test_empty_answer_is_not_complete(self) -> None:
        answer_question(self.project, "idea", text="A small portfolio site")
        data = self.project.discovery()
        assert data is not None
        data["answers"]["idea"] = {"status": "answered", "values": [], "text": " "}
        self.project.save_discovery(data)
        self.assertIn("idea", status(self.project)["missing"])
        question = next_question(self.project)
        assert question is not None
        self.assertEqual(question.id, "idea")

    def test_malformed_state_is_rejected(self) -> None:
        answer_question(self.project, "idea", text="A small portfolio site")
        data = self.project.discovery()
        assert data is not None
        data["answers"] = []
        self.project.save_discovery(data)
        with self.assertRaises(DiscoveryError):
            status(self.project)
        with self.assertRaises(DiscoveryError):
            summary(self.project)

    def test_plan_is_invalidated_by_discovery_change(self) -> None:
        self.complete()
        plan = ROOT / "examples" / "demo-site-plan.json"
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(
                cmd_plan(argparse.Namespace(project=str(self.root), file=str(plan))),
                0,
            )
        plan_id = output.getvalue().splitlines()[0].split()[1]
        answer_question(self.project, "labels", choices=["commerce"])
        args = argparse.Namespace(
            project=str(self.root),
            plan_id=plan_id,
            by="owner",
            note="",
            confirm="I approve this plan",
        )
        with self.assertRaises(DiscoveryError):
            cmd_approve(args)

    def test_labels_text_answer_is_rejected(self) -> None:
        with self.assertRaises(DiscoveryError):
            answer_question(self.project, "labels", text="new")

    def test_per_answer_malformed_shape_is_rejected(self) -> None:
        answer_question(self.project, "idea", text="A small portfolio site")
        data = self.project.discovery()
        assert data is not None
        data["answers"]["idea"] = {"values": None, "status": "answered"}
        self.project.save_discovery(data)
        with self.assertRaises(DiscoveryError):
            status(self.project)

    def test_unsupported_schema_is_rejected(self) -> None:
        answer_question(self.project, "idea", text="A small portfolio site")
        data = self.project.discovery()
        assert data is not None
        data["schema"] = 99
        self.project.save_discovery(data)
        with self.assertRaises(DiscoveryError):
            status(self.project)

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
        status_text = subprocess.run(
            [sys.executable, "-m", "aperio", "--project", str(self.root), "status"],
            check=False,
            capture_output=True,
            text=True,
            env=env,
            cwd=str(ROOT),
            timeout=30,
        )
        self.assertIn("Discovery: 1/10 answered", status_text.stdout)
        doctor = subprocess.run(
            [sys.executable, "-m", "aperio", "--project", str(self.root), "doctor"],
            check=False,
            capture_output=True,
            text=True,
            env=env,
            cwd=str(ROOT),
            timeout=30,
        )
        self.assertEqual(doctor.returncode, 0, doctor.stderr)
        self.assertIn("INFO discovery: 1/10 answered", doctor.stdout)


if __name__ == "__main__":
    unittest.main()
