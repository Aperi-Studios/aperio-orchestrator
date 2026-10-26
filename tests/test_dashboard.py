"""Tests for the read-only status dashboard."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aperio.dashboard import DASHBOARD_NAME, render, write
from aperio.model import Task
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
