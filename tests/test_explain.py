"""Tests for the gate explainer (apero explain)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from aperio.explain import TOPICS, explain
from aperio.store import Project

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


class ExplainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "proj"
        self.project = Project.init(self.root, "explain-test")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_every_topic_explains_without_a_project(self) -> None:
        for topic in TOPICS:
            info = explain(topic)
            self.assertEqual(info["topic"], topic)
            self.assertTrue(info["read_only"])
            for section in ("WHAT IT CHECKS", "WHY IT EXISTS", "COMMANDS"):
                self.assertIn(section, info["text"], topic)

    def test_every_topic_includes_live_status_with_a_project(self) -> None:
        for topic in TOPICS:
            info = explain(topic, self.project)
            self.assertIn("This project now:", info["text"], topic)

    def test_unknown_topic_is_refused(self) -> None:
        with self.assertRaises(KeyError):
            explain("nonsense")

    def test_learning_status_reflects_a_dossier(self) -> None:
        before = explain("learning", self.project)["text"]
        self.assertIn("no dossier", before)
        from tests.test_next import DOSSIER

        path = self.root / "learning.json"
        path.write_text(json.dumps(DOSSIER), encoding="utf-8")
        subprocess.run(
            [sys.executable, "-m", "aperio", "--project", str(self.root), "learn", "import", str(path), "--replace"],
            capture_output=True, text=True, check=False,
            cwd=str(ROOT), env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(SRC)),
        )
        after = explain("learning", self.project)["text"]
        self.assertNotIn("no dossier", after)

    def test_cli_explain_is_read_only_and_json(self) -> None:
        def snapshot() -> set[str]:
            return {str(p.relative_to(self.root)) for p in self.root.rglob("*") if p.is_file()}

        before = snapshot()
        for topic in ("discovery", "approval", "writes"):
            result = subprocess.run(
                [sys.executable, "-m", "aperio", "--project", str(self.root), "explain", topic, "--json"],
                capture_output=True, text=True, check=True,
                cwd=str(ROOT), env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(SRC)),
            )
            data = json.loads(result.stdout)
            self.assertEqual(data["topic"], topic)
            self.assertTrue(data["read_only"])
        self.assertEqual(before, snapshot(), "explain must not write any state")

    def test_cli_rejects_an_unknown_topic(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "aperio", "--project", str(self.root), "explain", "nonsense"],
            capture_output=True, text=True, check=False,
            cwd=str(ROOT), env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(SRC)),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice", result.stderr)

    def test_commands_in_text_use_the_real_binary_name(self) -> None:
        # The advisor's misspelling incident (apero/aperio) applies here too:
        # every command line in every topic must start with the real binary.
        for topic in TOPICS:
            info = explain(topic, self.project)
            for line in info["text"].splitlines():
                stripped = line.strip()
                if stripped.startswith(("apero ", "aperio ")):
                    self.assertTrue(stripped.startswith("aperio "), f"{topic}: {stripped}")


if __name__ == "__main__":
    unittest.main()
