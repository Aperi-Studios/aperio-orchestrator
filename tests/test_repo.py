from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from aperio.repo import facts, format_facts
from aperio.store import Project


@unittest.skipUnless(shutil.which("git"), "git is required")
class RepoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="aperio-repo-")
        self.root = Path(self.temp.name) / "project"
        self.root.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.root, check=True)
        (self.root / ".gitignore").write_text(".aperio/\n", encoding="utf-8")
        (self.root / "README.md").write_text("repo\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "initial"], cwd=self.root, check=True)
        self.project = Project.init(self.root, name="repo-test")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_reports_branch_head_and_clean_state(self) -> None:
        data = facts(self.project)
        self.assertIsNotNone(data)
        assert data is not None
        branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=self.root, text=True).strip()
        self.assertEqual(data["branch"], branch)
        self.assertEqual(data["head"], subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=self.root, text=True).strip())
        self.assertFalse(data["dirty"])
        self.assertIn("clean", format_facts(data))

    def test_reports_dirty_state(self) -> None:
        (self.root / "README.md").write_text("changed\n", encoding="utf-8")
        data = facts(self.project)
        assert data is not None
        self.assertTrue(data["dirty"])
        self.assertEqual(data["changed"], 1)
        self.assertIn("dirty", format_facts(data))

    def test_non_git_directory_is_explicit(self) -> None:
        plain = Path(self.temp.name) / "plain"
        plain.mkdir()
        project = Project.init(plain, name="plain")
        self.assertIsNone(facts(project))
        self.assertEqual(format_facts(None), "not a Git repository")
