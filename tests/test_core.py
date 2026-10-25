from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from aperio.model import Acceptance, Approval, Plan, Step, Task
from aperio.paths import PathSafetyError, normalize_rel, resolve_inside
from aperio.policy import PolicyError, assert_reviewer, path_allowed
from aperio.runner import RunError, apply_plan, finish, review, rollback, verify
from aperio.store import Project, StoreError


def make_plan(
    project: Project,
    *,
    steps: list[Step],
    acceptance: list[Acceptance] | None = None,
    allowed: list[str] | None = None,
    builder: str = "agent",
    approval: bool = True,
) -> tuple[Task, Plan]:
    task = Task(id="task-test", title="Test task", request="Do the test work", status="planned")
    plan = Plan(
        id="plan-test",
        task_id=task.id,
        title=task.title,
        request=task.request,
        allowed_paths=allowed or ["site/"],
        steps=steps,
        acceptance=acceptance or [Acceptance(id="check", command="true")],
        builder=builder,
    )
    plan.validate()
    task.plan_id = plan.id
    if approval:
        plan.approval = Approval(approved_by="owner")
        task.status = "approved"
    project.save_plan(plan)
    project.put_task(task)
    return task, plan


class CoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="aperio-test-")
        self.root = Path(self.temp.name)
        self.project = Project.init(self.root, name="test")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_init_refuses_second_initialization(self) -> None:
        with self.assertRaises(StoreError):
            Project.init(self.root, name="again")

    def test_ask_is_append_only(self) -> None:
        first = self.project.add_ask("Build a page")
        second = self.project.add_ask("Add a CMS field")
        asks = self.project.asks()
        self.assertEqual([a.id for a in asks], [first.id, second.id])
        self.assertEqual(asks[0].text, "Build a page")

    def test_unapproved_plan_never_writes(self) -> None:
        _, plan = make_plan(
            self.project,
            steps=[Step(id="write", kind="write", path="site/index.html", content="hello")],
            approval=False,
        )
        with self.assertRaises(RunError):
            apply_plan(self.project, plan)
        self.assertFalse((self.root / "site/index.html").exists())

    def test_plan_runs_verifies_reviews_and_finishes(self) -> None:
        task, plan = make_plan(
            self.project,
            steps=[
                Step(id="write", kind="write", path="site/index.html", content="hello"),
                Step(
                    id="build",
                    kind="run",
                    command=f'{sys.executable} -c "from pathlib import Path; Path(\'site/out.txt\').write_text(\'ok\')"',
                    cwd=".",
                    writes=["site/out.txt"],
                ),
            ],
            acceptance=[
                Acceptance(
                    id="check",
                    command=f'{sys.executable} -c "from pathlib import Path; assert Path(\'site/index.html\').read_text() == \'hello\'; assert Path(\'site/out.txt\').read_text() == \'ok\'"',
                )
            ],
        )
        result = apply_plan(self.project, plan)
        self.assertEqual(result["status"], "applied", result)
        self.assertTrue((self.root / "site/index.html").is_file())
        verified = verify(self.project, task.id)
        self.assertEqual(verified["status"], "passed", verified)
        reviewed = review(self.project, task.id, reviewer="qa", verdict="confirmed", notes="ok")
        self.assertEqual(reviewed["verdict"], "confirmed")
        done = finish(self.project, task.id)
        self.assertEqual(done["status"], "done")
        with self.assertRaises(RunError):
            apply_plan(self.project, plan)

    def test_reviewer_must_differ_from_builder(self) -> None:
        with self.assertRaises(PolicyError):
            assert_reviewer("agent", "agent")

    def test_self_review_is_refused(self) -> None:
        task, plan = make_plan(
            self.project,
            steps=[Step(id="write", kind="write", path="site/index.html", content="hello")],
            builder="agent",
        )
        apply_plan(self.project, plan)
        verify(self.project, task.id)
        with self.assertRaises(RunError):
            review(self.project, task.id, reviewer="agent", verdict="confirmed")

    def test_path_traversal_is_refused(self) -> None:
        with self.assertRaises(PathSafetyError):
            normalize_rel("../outside.txt")
        with self.assertRaises(PathSafetyError):
            resolve_inside(self.root, "/etc/passwd")
        with self.assertRaises(PathSafetyError):
            resolve_inside(self.root, "site/../../outside.txt")

    def test_symlink_component_is_refused(self) -> None:
        outside = self.root.parent / "outside-target"
        outside.mkdir(exist_ok=True)
        link = self.root / "site"
        link.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(PathSafetyError):
            resolve_inside(self.root, "site/file.txt")
        link.unlink()
        outside.rmdir()

    def test_write_outside_allowed_plan_is_refused(self) -> None:
        _task, plan = make_plan(
            self.project,
            steps=[Step(id="write", kind="write", path="other/index.html", content="bad")],
            allowed=["site/"],
        )
        with self.assertRaises(RunError):
            apply_plan(self.project, plan)
        self.assertFalse((self.root / "other/index.html").exists())

    def test_protected_path_is_refused(self) -> None:
        _task, plan = make_plan(
            self.project,
            steps=[Step(id="git", kind="write", path=".git/config", content="bad")],
            allowed=["*"],
        )
        with self.assertRaises(RunError):
            apply_plan(self.project, plan)
        self.assertFalse((self.root / ".git/config").exists())

    def test_absolute_write_is_refused(self) -> None:
        _task, plan = make_plan(
            self.project,
            steps=[Step(id="abs", kind="write", path="/tmp/aperio-absolute.txt", content="bad")],
            allowed=["*"],
        )
        with self.assertRaises(RunError):
            apply_plan(self.project, plan)

    def test_refuted_review_blocks_finish(self) -> None:
        task, plan = make_plan(
            self.project,
            steps=[Step(id="write", kind="write", path="site/index.html", content="hello")],
        )
        apply_plan(self.project, plan)
        verify(self.project, task.id)
        review(self.project, task.id, reviewer="qa", verdict="refuted", notes="not acceptable")
        with self.assertRaises(RunError):
            finish(self.project, task.id)
        self.assertEqual(self.project.get_task(task.id).status, "failed")

    def test_command_outside_write_is_detected(self) -> None:
        task, plan = make_plan(
            self.project,
            steps=[
                Step(
                    id="escape",
                    kind="run",
                    command=f'{sys.executable} -c "from pathlib import Path; Path(\'outside.txt\').write_text(\'bad\')"',
                    cwd=".",
                    writes=[],
                )
            ],
        )
        result = apply_plan(self.project, plan)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("outside.txt" in v for v in result["violations"]))
        self.assertEqual(self.project.get_task(task.id).status, "failed")
        with self.assertRaises(RunError):
            verify(self.project, task.id)

    def test_created_symlink_is_detected(self) -> None:
        task, plan = make_plan(
            self.project,
            steps=[
                Step(id="seed", kind="write", path="site/index.html", content="hello"),
                Step(
                    id="link",
                    kind="run",
                    command=f'{sys.executable} -c "import os; os.symlink(\'/etc/hosts\', \'site/link\')"',
                    cwd=".",
                    writes=[],
                ),
            ],
        )
        result = apply_plan(self.project, plan)
        self.assertEqual(result["status"], "failed")
        self.assertIn("site/link", result["changed_files"])
        self.assertTrue((self.root / "site/link").is_symlink())
        self.assertEqual(self.project.get_task(task.id).status, "failed")

    def test_rollback_restores_modified_and_removes_created(self) -> None:
        (self.root / "site").mkdir()
        original = self.root / "site/index.html"
        original.write_text("old", encoding="utf-8")
        task, plan = make_plan(
            self.project,
            steps=[
                Step(id="replace", kind="write", path="site/index.html", content="new"),
                Step(id="create", kind="write", path="site/new.txt", content="created"),
            ],
        )
        result = apply_plan(self.project, plan)
        self.assertEqual(result["status"], "applied", result)
        self.assertEqual(original.read_text(), "new")
        rollback(self.project, task.id)
        self.assertEqual(original.read_text(), "old")
        self.assertFalse((self.root / "site/new.txt").exists())

    def test_verification_failure_is_reported(self) -> None:
        task, plan = make_plan(
            self.project,
            steps=[Step(id="write", kind="write", path="site/index.html", content="hello")],
            acceptance=[Acceptance(id="bad", command="false")],
        )
        apply_plan(self.project, plan)
        result = verify(self.project, task.id)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.project.get_task(task.id).status, "failed")

    def test_plan_path_matching(self) -> None:
        self.assertTrue(path_allowed("site/index.html", ["site/"]))
        self.assertTrue(path_allowed("site/a/b.txt", ["site"]))
        self.assertFalse(path_allowed("other/site.txt", ["site/"]))
        self.assertTrue(path_allowed("src/a.py", ["src/**/*.py"]))


if __name__ == "__main__":
    unittest.main()
