"""Tests for the tutorial flight simulator (apero tutorial build/check)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from aperio.store import Project
from aperio.tutorial import build, check

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


class TutorialTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "tutorial"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def cli(self, *args: str, allow_rc: set[int] | None = None) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, "-m", "aperio", "--project", str(self.root), *args],
            capture_output=True, text=True, check=False,
            cwd=str(ROOT),
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(SRC)),
            timeout=60,
        )
        allowed = {0} | (allow_rc or set())
        self.assertIn(result.returncode, allowed, f"rc={result.returncode} for {args}: {result.stderr}")
        return result

    def test_build_creates_a_ready_fixture(self) -> None:
        build(self.root)
        self.assertTrue((self.root / "CHECKLIST.md").is_file())
        self.assertTrue((self.root / "starter-plan.json").is_file())
        project = Project.open(self.root)
        # Every plan gate pre-satisfied: learning proof recorded, todo started,
        # readiness imported, discovery answered.
        self.assertTrue((project.state / "readiness.json").is_file())
        self.assertTrue((project.state / "discovery.json").is_file())
        # The starter plan is valid JSON with the three plan parts.
        plan = json.loads((self.root / "starter-plan.json").read_text(encoding="utf-8"))
        for key in ("allowed_paths", "steps", "acceptance"):
            self.assertIn(key, plan)

    def test_build_is_refused_on_an_existing_fixture(self) -> None:
        from aperio.store import StoreError

        build(self.root)
        with self.assertRaises(StoreError):
            build(self.root)

    def test_build_refuses_a_nonempty_foreign_directory(self) -> None:
        # A host review caught build clobbering pre-existing files (it
        # write_text's CHECKLIST.md et al). A nonempty directory that is not
        # a tutorial fixture must be refused, and the user's file preserved.
        self.root.mkdir(parents=True)
        (self.root / "notes.md").write_text("USER'S PRECIOUS NOTES", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            build(self.root)
        self.assertEqual(
            (self.root / "notes.md").read_text(encoding="utf-8"),
            "USER'S PRECIOUS NOTES",
        )
        self.assertFalse((self.root / "CHECKLIST.md").exists())

    def test_fresh_fixture_grades_in_progress(self) -> None:
        build(self.root)
        result = check(self.root)
        self.assertEqual(result["grade"], "in progress")
        self.assertEqual(result["passed"], 0)
        self.assertFalse(result["steps"][0]["done"])
        self.assertIn("aperio plan", result["steps"][0]["hint"])

    def test_full_flight_grades_complete(self) -> None:
        build(self.root)
        self.cli("plan", str(self.root / "starter-plan.json"))
        status = json.loads(self.cli("status", "--json").stdout)
        task = [t for t in status["tasks"] if t.get("plan_id")][-1]
        plan_id = task["plan_id"]
        task_id = task["id"]
        self.cli("approve", plan_id, "--by", "owner", "--confirm", "I approve this plan")
        self.cli("run", task_id, "--actor", "learner")
        self.cli("verify", task_id)
        self.cli("review", task_id, "--reviewer", "mentor", "--verdict", "confirmed")
        self.cli("done", task_id)
        self.cli("handoff", task_id)
        result = check(self.root)
        self.assertEqual(result["grade"], "complete", result)
        self.assertEqual(result["passed"], result["total"])
        self.assertTrue((self.root / "site" / "index.html").is_file())

    def test_fixture_gates_refuse_wrong_phrase_and_self_review(self) -> None:
        # The tutorial's point is meeting the real gates: a wrong approval
        # phrase and a builder self-review must be refused inside the
        # fixture, exactly as in a real project (a host review caught the
        # happy-path-only coverage).
        build(self.root)
        self.cli("plan", str(self.root / "starter-plan.json"))
        status = json.loads(self.cli("status", "--json").stdout)
        task = [t for t in status["tasks"] if t.get("plan_id")][-1]
        plan_id, task_id = task["plan_id"], task["id"]
        bad_phrase = self.cli("approve", plan_id, "--by", "owner", "--confirm", "sure whatever", allow_rc={2})
        self.assertEqual(bad_phrase.returncode, 2)
        self.assertIn("I approve this plan", bad_phrase.stderr)
        self.cli("approve", plan_id, "--by", "owner", "--confirm", "I approve this plan")
        self.cli("run", task_id, "--actor", "learner")
        self.cli("verify", task_id)
        self_review = self.cli("review", task_id, "--reviewer", "agent", "--verdict", "confirmed", allow_rc={2})
        self.assertEqual(self_review.returncode, 2)
        self.assertTrue(
            "builder" in self_review.stderr.lower() or "reviewer" in self_review.stderr.lower(),
            self_review.stderr,
        )

    def test_check_is_read_only(self) -> None:
        build(self.root)
        self.cli("plan", str(self.root / "starter-plan.json"))

        def snapshot() -> dict[str, bytes]:
            return {
                str(p.relative_to(self.root)): p.read_bytes()
                for p in sorted(self.root.rglob("*"))
                if p.is_file()
            }

        before = snapshot()
        check(self.root)
        self.assertEqual(before, snapshot(), "check must not write any state")

    def test_cli_build_and_check_roundtrip(self) -> None:
        result = self.cli("tutorial", "build", str(self.root))
        self.assertIn("Tutorial ready", result.stdout)
        result = self.cli("tutorial", "check", str(self.root), "--json")
        data = json.loads(result.stdout)
        self.assertEqual(data["grade"], "in progress")
        self.assertTrue(data["read_only"])


if __name__ == "__main__":
    unittest.main()
