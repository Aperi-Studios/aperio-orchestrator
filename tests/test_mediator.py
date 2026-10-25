from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aperio.mediator import mediate
from aperio.model import Acceptance, Approval, Plan, Step, Task
from aperio.runner import apply_plan, review, verify
from aperio.store import Project


class MediatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="aperio-mediator-")
        self.root = Path(self.temp.name)
        self.project = Project.init(self.root, name="mediator-test")
        self.task = Task(id="task-mediate", title="Mediate", request="Do work", status="planned")
        self.plan = Plan(
            id="plan-mediate",
            task_id=self.task.id,
            title="Mediate",
            request="Do work",
            allowed_paths=["site/"],
            steps=[Step(id="write", kind="write", path="site/index.html", content="ok")],
            acceptance=[Acceptance(id="check", command="test -f site/index.html")],
            builder="builder",
        )
        self.plan.validate()
        self.plan.approval = Approval(approved_by="owner")
        self.task.plan_id = self.plan.id
        self.task.status = "approved"
        self.project.save_plan(self.plan)
        self.project.put_task(self.task)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_missing_run_is_blocked(self) -> None:
        record = mediate(self.project, self.task.id)
        self.assertEqual(record["disposition"], "BLOCKED")
        self.assertIn("no run evidence", record["reason"])
        self.assertTrue(Path(record["evidence_path"]).is_file())

    def test_confirmed_review_is_confirmed(self) -> None:
        apply_plan(self.project, self.plan)
        verify(self.project, self.task.id)
        self.assertEqual(mediate(self.project, self.task.id)["disposition"], "BLOCKED")
        review(self.project, self.task.id, "qa", "confirmed", notes="checked")
        record = mediate(self.project, self.task.id)
        self.assertEqual(record["disposition"], "CONFIRMED")
        self.assertEqual(record["reviewer"], "qa")

    def test_refuted_review_is_refuted(self) -> None:
        apply_plan(self.project, self.plan)
        verify(self.project, self.task.id)
        review(self.project, self.task.id, "qa", "refuted", notes="bad")
        self.assertEqual(mediate(self.project, self.task.id)["disposition"], "REFUTED")

    def test_later_failed_verification_is_refuted(self) -> None:
        apply_plan(self.project, self.plan)
        verify(self.project, self.task.id)
        review(self.project, self.task.id, "qa", "confirmed", notes="checked")
        self.assertEqual(mediate(self.project, self.task.id)["disposition"], "CONFIRMED")
        self.plan.acceptance = [Acceptance(id="check", command="false")]
        self.project.save_plan(self.plan)
        verify(self.project, self.task.id)
        record = mediate(self.project, self.task.id)
        self.assertEqual(record["disposition"], "REFUTED")
        self.assertEqual(record["task_status"], "failed")


if __name__ == "__main__":
    unittest.main()
