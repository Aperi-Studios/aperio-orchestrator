"""Tests for the read-only status dashboard."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aperio.dashboard import DASHBOARD_NAME, render, write
from aperio.model import Task
from aperio.paths import PathSafetyError
from aperio.store import Project


class DashboardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="aperio-dashboard-")
        self.project = Project.init(Path(self.temp.name), name="Dashboard test")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_render_includes_real_state(self) -> None:
        self.project.put_task(Task(id="task-1", title="Build the page", request="Build it"))
        page = render(self.project)
        self.assertIn("Dashboard test", page)
        self.assertIn("Build the page", page)
        self.assertIn("Read-only Aperio status", page)

    def test_render_escapes_project_text(self) -> None:
        self.project.put_task(
            Task(id="task-2", title="<script>alert('x')</script>", request="Unsafe title")
        )
        page = render(self.project)
        self.assertNotIn("<script>alert", page)
        self.assertIn("&lt;script&gt;alert", page)

    def test_write_uses_the_state_directory_by_default(self) -> None:
        path = Path(write(self.project))
        self.assertEqual(path, self.project.state / DASHBOARD_NAME)
        self.assertTrue(path.is_file())
        self.assertIn("Dashboard test", path.read_text(encoding="utf-8"))

    def test_write_accepts_a_relative_output(self) -> None:
        path = Path(write(self.project, "reports/status.html"))
        self.assertTrue(path.is_file())
        self.assertIn("<!doctype html>", path.read_text(encoding="utf-8"))

    def test_write_refuses_to_clobber_the_control_plane(self) -> None:
        # N3: --output used to be joined straight onto project.root, so a grade
        # report could overwrite project state files.
        project_json = self.project.state / "project.json"
        before = project_json.read_text(encoding="utf-8")
        with self.assertRaises(PathSafetyError):
            write(self.project, ".aperio/project.json")
        self.assertEqual(project_json.read_text(encoding="utf-8"), before)

    def test_write_refuses_traversal(self) -> None:
        outside = Path(self.temp.name) / "escape.html"
        with self.assertRaises(PathSafetyError):
            write(self.project, "../escape.html")
        self.assertFalse(outside.exists())

    def test_dashboard_output_does_not_clobber_tracked_files(self) -> None:
        # D1: an existing tracked file must never be silently replaced by HTML.
        readme = self.project.root / "README.md"
        readme.write_text("# Keep\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            write(self.project, "README.md")
        self.assertEqual(readme.read_text(encoding="utf-8"), "# Keep\n")
        forced = Path(write(self.project, "README.md", force=True))
        self.assertIn("<!doctype html>", forced.read_text(encoding="utf-8"))
