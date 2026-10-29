"""Tests for the lessons ledger (apero lesson add/list/remove + plan surfacing)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from aperio.lessons import LessonsError, add, read_lessons, relevant_lessons, remove
from aperio.store import Project

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


class LessonsUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.project = Project.init(Path(self.temp.name) / "proj", "lessons-test")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_add_and_read_roundtrip(self) -> None:
        entry = add(self.project, "Glob writes do not cross directories", paths=["src/"])
        self.assertEqual(entry["id"], "lesson-0001")
        data = read_lessons(self.project)
        self.assertEqual(len(data["lessons"]), 1)
        self.assertEqual(data["lessons"][0]["text"], "Glob writes do not cross directories")

    def test_empty_text_refused(self) -> None:
        with self.assertRaises(LessonsError):
            add(self.project, "   ")

    def test_glob_and_traversal_paths_refused(self) -> None:
        with self.assertRaises(LessonsError):
            add(self.project, "x", paths=["src/*.py"])
        with self.assertRaises(LessonsError):
            add(self.project, "x", paths=["../escape"])

    def test_remove_removes_and_reports_unknown(self) -> None:
        entry = add(self.project, "lesson one")
        remove(self.project, entry["id"])
        self.assertEqual(read_lessons(self.project)["lessons"], [])
        with self.assertRaises(LessonsError):
            remove(self.project, entry["id"])

    def test_relevant_lessons_match_by_prefix(self) -> None:
        add(self.project, "runner lessons live here", paths=["src/aperio"])
        matches = relevant_lessons(self.project, ["src/aperio/runner.py"])
        self.assertEqual(len(matches), 1)
        self.assertEqual(relevant_lessons(self.project, ["docs/"]), [])

    def test_lessons_without_paths_never_match(self) -> None:
        add(self.project, "a general lesson with no paths")
        self.assertEqual(relevant_lessons(self.project, ["src/"]), [])


class LessonsCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "proj"

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

    def test_cli_add_list_remove(self) -> None:
        self.cli("init", str(self.root))
        self.cli("lesson", "add", "The Floor catches sneaky markers", "--paths", "src/,tests/")
        result = self.cli("lesson", "list")
        self.assertIn("The Floor catches sneaky markers", result.stdout)
        listing = json.loads(self.cli("lesson", "list", "--json").stdout)
        lesson_id = listing["lessons"][0]["id"]
        self.cli("lesson", "remove", lesson_id)
        listing = json.loads(self.cli("lesson", "list", "--json").stdout)
        self.assertEqual(listing["lessons"], [])

    def test_plan_surfaces_relevant_lessons(self) -> None:
        # The compounding mechanism: a lesson bound to src/ is surfaced at
        # plan time when the plan's allowed paths touch src/.
        self.cli("init", str(self.root))
        self.cli("lesson", "add", "watch the cli gate order", "--paths", "src/")
        self.cli(
            "todo", "add", "Build page",
            "--deliverable", "page works",
            "--acceptance", "page exists",
        )
        listing = json.loads(self.cli("todo", "list", "--json").stdout)
        self.cli("todo", "start", listing["tasks"][0]["id"])
        dossier = {
            "schema": 1,
            "stack": {"surface": "website", "runtime": "Python 3.10", "framework": "standard library",
                      "package_manager": "none", "database": "none", "hosting": "local",
                      "versions": {"python": "3.10"}, "constraints": []},
            "sources": [{"title": "Python documentation", "url": "https://docs.python.org/3/",
                         "kind": "official_docs", "version": "3.10", "accessed": "2026-10-29", "official": True}],
            "skills": [], "skill_gap": {"needed": False, "reason": "stdlib sufficient."},
            "mcps": [],
            "teachback": {"agent": "agent",
                          "summary": "I can explain the runtime, plan format, acceptance checks, and limits of this fixture.",
                          "uncertainties": []},
            "competency": {"agent": "agent", "verdict": "demonstrated",
                           "evidence": "local proof recorded", "recorded_at": "2026-10-29T00:00:00Z"},
        }
        (self.root / "learning.json").write_text(json.dumps(dossier), encoding="utf-8")
        self.cli("learn", "import", str(self.root / "learning.json"), allow_rc={1})
        self.cli("learn", "proof", "--command", f'{sys.executable} -c "print(1)"')
        readiness = {
            "schema": 1,
            "preflight": {"audience": "u", "success_measure": "renders", "features": ["page"],
                          "out_of_scope": ["deploy"], "integrations": ["none"], "constraints": ["local"],
                          "review_owner": "owner", "approval_path": "owner approves"},
            "deploy": {"hosting": "local", "domain": "localhost", "tls": "n/a", "env_names": [],
                       "build": "none", "migrate": "none", "backup": "copy", "restore": "copy",
                       "ci_cd": "local", "rollback": "copy", "monitoring": "out", "smoke": "check"},
            "aftersales": {"support_window": "w", "escalation_owner": "owner", "logs": "l", "metrics": "m",
                           "alerts": "a", "backup_schedule": "d", "restore_drill": "m", "update_policy": "m",
                           "admin_recovery": "owner", "docs": "r"},
            "design": {"surface_class": "marketing", "contract": "clear", "references": ["ref"],
                       "accessibility": "ok", "responsive": "390", "originality": "orig",
                       "review_owner": "owner"},
            "security": {"threat_model": "local", "assets": ["a"], "trust_boundaries": ["t"],
                         "controls": ["c"], "dependency_scan": "s", "secret_scan": "s",
                         "headers": "h", "incident": "i", "unresolved_severity": "none"},
        }
        (self.root / "readiness.json").write_text(json.dumps(readiness), encoding="utf-8")
        self.cli("readiness", "import", str(self.root / "readiness.json"))
        rows = [("idea", None, "Build a page"), ("users", None, "Visitors"), ("success", ["launch"], ""),
                ("must_haves", None, "One page"), ("non_goals", None, "No login"),
                ("constraints", ["none"], ""), ("ownership", ["owner"], ""), ("evidence", ["none"], ""),
                ("labels", ["new"], ""), ("name", None, "lessons-test")]
        for qid, choices, text in rows:
            cmd = ["discover", "answer", qid]
            if choices:
                cmd += ["--choice", ",".join(choices)]
            if text:
                cmd += ["--text", text]
            self.cli(*cmd)
        plan = {"title": "t", "request": "r", "allowed_paths": ["src/"],
                "steps": [{"id": "s", "kind": "write", "path": "src/x.txt", "content": "x"}],
                "acceptance": [{"id": "c", "command": "test -f src/x.txt"}]}
        (self.root / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        result = self.cli("plan", str(self.root / "plan.json"))
        self.assertIn("LESSON", result.stderr, "relevant lesson not surfaced at plan time")


if __name__ == "__main__":
    unittest.main()
