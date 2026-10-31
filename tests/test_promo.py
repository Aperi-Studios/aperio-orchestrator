"""Tests for the promo generator (apero promo — launch-video plan from a done task)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from aperio.promo import PromoError, build_promo
from aperio.store import Project

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def _fly_task_to_done(project: Project) -> None:
    """Build a real done task: run, verify, review — through the real runner."""
    from aperio.model import Acceptance, Approval, Plan, Step, plan_body_digest
    from aperio.runner import apply_plan, finish, review, verify

    (project.root / "site").mkdir(exist_ok=True)
    (project.root / "site" / "index.html").write_text("<h1>draft</h1>", encoding="utf-8")
    task = __import__("aperio.model", fromlist=["Task"]).Task(
        id="task-promo-src", title="Landing page", request="Build the landing page"
    )
    task.status = "approved"
    tasks = project.tasks()
    tasks.append(task)
    project.save_tasks(tasks)
    plan = Plan(
        id="plan-promo-src",
        task_id=task.id,
        title="Landing page",
        request=task.request,
        allowed_paths=["site/"],
        steps=[Step(id="w", kind="write", path="site/index.html", content="<h1>done</h1>")],
        acceptance=[Acceptance(id="check", command="test -f site/index.html")],
    )
    task.plan_id = plan.id
    project.put_task(task)
    plan.approval = Approval(approved_by="owner", plan_sha256=plan_body_digest(plan))
    project.save_plan(plan)
    plan = project.get_plan(plan.id)
    apply_plan(project, plan, actor="builder")
    verify(project, task.id)
    review(project, task.id, reviewer="qa", verdict="confirmed")
    finish(project, task.id)


class PromoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.project = Project.init(Path(self.temp.name) / "proj", "promo-test")
        _fly_task_to_done(self.project)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_generates_sheet_and_plan_from_done_task(self) -> None:
        result = build_promo(self.project, "task-promo-src")
        sheet = result["sheet"]
        self.assertEqual(sheet["duration_s"], 12)
        self.assertEqual(sheet["width"], 1920)
        self.assertEqual(sheet["height"], 1080)
        total = sum(scene["duration"] for scene in sheet["scenes"])
        self.assertAlmostEqual(total, 12, places=2)
        # Sourced from real evidence: the changed file and the check are cited.
        self.assertIn("site/index.html", sheet["sourced_from"]["changed_files"])
        self.assertTrue(sheet["sourced_from"]["acceptance_checks"])
        # The promo plan is a valid plan-shaped dict with bounded paths.
        promo_plan = result["promo_plan"]
        self.assertEqual(promo_plan["allowed_paths"], ["promo/"])
        for step in promo_plan["steps"]:
            self.assertEqual(step["kind"], "write")
            self.assertTrue(step["path"].startswith("promo/"))

    def test_refuses_a_task_that_is_not_done(self) -> None:
        from aperio.model import Task

        tasks = self.project.tasks()
        tasks.append(
            Task(id="task-early", title="early", request="r", status="planned")
        )
        self.project.save_tasks(tasks)
        with self.assertRaises(PromoError):
            build_promo(self.project, "task-early")

    def test_duration_bounds(self) -> None:
        with self.assertRaises(PromoError):
            build_promo(self.project, "task-promo-src", duration=4)
        with self.assertRaises(PromoError):
            build_promo(self.project, "task-promo-src", duration=60)

    def test_vertical_option(self) -> None:
        result = build_promo(self.project, "task-promo-src", vertical=True)
        self.assertEqual(result["sheet"]["width"], 1080)
        self.assertEqual(result["sheet"]["height"], 1920)

    def test_determinism_contract_in_generated_plan(self) -> None:
        # The generated composition must carry the docs/MOTION.md contract:
        # declared meta, no random/now, paused timeline.
        result = build_promo(self.project, "task-promo-src")
        composition = next(
            s["content"] for s in result["promo_plan"]["steps"] if s["path"] == "promo/composition.html"
        )
        self.assertIn('name="hyperframes"', composition)
        self.assertNotIn("Math.random", composition)
        self.assertNotIn("Date.now", composition)
        self.assertIn("__timelines", composition)

    def test_generated_plan_passes_aperio_validation(self) -> None:
        # The strongest check: the generated promo plan is a real Aperio plan
        # — it validates through the model and saves into a project.
        result = build_promo(self.project, "task-promo-src")
        from aperio.model import Plan

        data = dict(result["promo_plan"])
        data["id"] = "plan-generated"
        data["task_id"] = "task-generated"
        data["steps"] = [
            {**s, "id": f"{s['id']}-gen"} for s in data["steps"]
        ]
        plan = Plan.from_dict(data)
        self.project.save_plan(plan)
        loaded = self.project.get_plan("plan-generated")
        self.assertEqual(len(loaded.steps), 3)

    def test_cli_promo_on_done_task(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "aperio", "--project", str(self.project.root),
             "promo", "task-promo-src", "--json"],
            capture_output=True, text=True, check=False,
            cwd=str(ROOT),
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(SRC)),
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["sheet"]["duration_s"], 12)

    def test_cli_promo_refuses_undone_task(self) -> None:
        from aperio.model import Task

        tasks = self.project.tasks()
        tasks.append(Task(id="task-early2", title="early", request="r", status="planned"))
        self.project.save_tasks(tasks)
        result = subprocess.run(
            [sys.executable, "-m", "aperio", "--project", str(self.project.root),
             "promo", "task-early2"],
            capture_output=True, text=True, check=False,
            cwd=str(ROOT),
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(SRC)),
            timeout=60,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("done", result.stderr)


if __name__ == "__main__":
    unittest.main()
