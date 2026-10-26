from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from aperio.model import Acceptance, Approval, ModelError, Plan, Step, Task
from aperio.paths import PathSafetyError, normalize_rel, resolve_inside
from aperio.policy import (
    PolicyError,
    assert_reviewer,
    path_allowed,
    validate_plan_paths,
)
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
        acceptance=acceptance or [Acceptance(id="check", command="test -f .aperio/project.json")],
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

    def test_legacy_queue_schema_is_migrated(self) -> None:
        queue = self.project.state / "queue.json"
        data = json.loads(queue.read_text(encoding="utf-8"))
        data.pop("schema", None)
        queue.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(self.project.tasks(), [])
        migrated = json.loads(queue.read_text(encoding="utf-8"))
        self.assertEqual(migrated["schema"], 1)

    def test_future_queue_schema_is_refused(self) -> None:
        queue = self.project.state / "queue.json"
        data = json.loads(queue.read_text(encoding="utf-8"))
        data["schema"] = 999
        queue.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(StoreError) as caught:
            self.project.tasks()
        self.assertIn("unsupported state schema", str(caught.exception))

    def test_future_project_schema_is_refused(self) -> None:
        project_file = self.project.state / "project.json"
        data = json.loads(project_file.read_text(encoding="utf-8"))
        data["schema"] = 999
        project_file.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(StoreError) as caught:
            Project.open(self.root)
        self.assertIn("unsupported state schema", str(caught.exception))

    def test_legacy_discovery_schema_is_migrated(self) -> None:
        path = self.project.state / "discovery.json"
        path.write_text(json.dumps({"answers": {}, "questions": []}), encoding="utf-8")
        result = self.project.discovery()
        assert result is not None
        self.assertEqual(result["schema"], 1)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["schema"], 1)

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

    def test_directory_write_accepts_files_created_by_a_run(self) -> None:
        # Regression: an existing declared directory used to expand to its
        # pre-run files only, so a build step that emitted a new file was
        # rejected as "changed outside declared writes".
        (self.root / "dist").mkdir()
        command = (
            f"{sys.executable} -c \"from pathlib import Path; "
            "Path('dist/new.txt').write_text('built'); "
            "Path('dist/sub').mkdir(exist_ok=True); "
            "Path('dist/sub/nested.txt').write_text('nested')\""
        )
        acceptance_command = (
            f"{sys.executable} -c \"from pathlib import Path; "
            "assert Path('dist/new.txt').read_text() == 'built'\""
        )
        task, plan = make_plan(
            self.project,
            steps=[
                Step(
                    id="build",
                    kind="run",
                    command=command,
                    writes=["dist/"],
                )
            ],
            allowed=["dist/"],
            acceptance=[Acceptance(id="check", command=acceptance_command)],
        )
        result = apply_plan(self.project, plan)
        self.assertEqual(result["status"], "applied", result)
        self.assertEqual(result["violations"], [])
        self.assertTrue((self.root / "dist/new.txt").is_file())
        self.assertTrue((self.root / "dist/sub/nested.txt").is_file())
        verified = verify(self.project, task.id)
        self.assertEqual(verified["status"], "passed", verified)

    def test_read_step_records_output_without_changes(self) -> None:
        task, plan = make_plan(
            self.project,
            steps=[
                Step(
                    id="inspect",
                    kind="read",
                    command=f'{sys.executable} -c "print(123)"',
                )
            ],
        )
        result = apply_plan(self.project, plan)
        self.assertEqual(result["status"], "applied", result)
        self.assertEqual(result["changed_files"], [])
        self.assertEqual(result["steps"][0]["kind"], "read")
        self.assertIn("123", result["steps"][0]["stdout"])
        self.assertEqual(verify(self.project, task.id)["status"], "passed")

    def test_read_step_cannot_change_the_project(self) -> None:
        (self.root / "site").mkdir()
        _, plan = make_plan(
            self.project,
            steps=[
                Step(
                    id="sneaky-read",
                    kind="read",
                    command=(
                        f'{sys.executable} -c "from pathlib import Path; '
                        "Path('site/leak.txt').write_text('x')\""
                    ),
                )
            ],
        )
        result = apply_plan(self.project, plan)
        self.assertEqual(result["status"], "failed", result)
        self.assertTrue(any("read step changed" in item for item in result["violations"]))

    def test_protected_paths_cannot_be_removed_by_policy(self) -> None:
        _, plan = make_plan(
            self.project,
            steps=[Step(id="write", kind="write", path="site/index.html", content="hello")],
            allowed=[".git/"],
            approval=False,
        )
        with self.assertRaises(PolicyError):
            validate_plan_paths(plan, [])
        _, plan = make_plan(
            self.project,
            steps=[Step(id="write", kind="write", path=".aperio/state.json", content="x")],
            allowed=[".aperio/"],
            approval=False,
        )
        with self.assertRaises(PolicyError):
            validate_plan_paths(plan, [])

    def test_read_step_shape_is_rejected_by_the_model(self) -> None:
        # kind="read" validation branches (PRD: read-only steps cannot change the project)
        with self.assertRaises(ModelError) as raised:
            Step(id="read-0", kind="read").validate()
        self.assertIn("read needs a command", str(raised.exception))
        with self.assertRaises(ModelError) as raised:
            Step(id="read-1", kind="read", command="true", writes=["out.txt"]).validate()
        self.assertIn("read must not declare writes", str(raised.exception))
        with self.assertRaises(ModelError) as raised:
            Step(id="read-2", kind="read", command="true", content="x").validate()
        self.assertIn("read cannot write fixed content or use a host", str(raised.exception))
        with self.assertRaises(ModelError) as raised:
            Step(id="read-3", kind="read", command="true", host="claude", prompt="behave").validate()
        self.assertIn("read cannot write fixed content or use a host", str(raised.exception))
        Step(id="read-ok", kind="read", command="true").validate()  # the valid shape passes

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

    def test_verification_timeout_cannot_pass(self) -> None:
        task, plan = make_plan(
            self.project,
            steps=[Step(id="write", kind="write", path="site/index.html", content="hello")],
            acceptance=[Acceptance(id="slow", command="sleep 2", expected_exit=124, timeout_s=1)],
        )
        apply_plan(self.project, plan)
        result = verify(self.project, task.id)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["checks"][0]["timed_out"])
        self.assertFalse(result["checks"][0]["ok"])
        self.assertEqual(self.project.get_task(task.id).status, "failed")

    def test_acceptance_check_cannot_mutate_the_project(self) -> None:
        task, plan = make_plan(
            self.project,
            steps=[Step(id="write", kind="write", path="site/index.html", content="hello")],
            acceptance=[Acceptance(id="writes", command="printf bad > site/extra.txt")],
        )
        apply_plan(self.project, plan)
        result = verify(self.project, task.id)
        self.assertEqual(result["status"], "failed")
        self.assertIn("site/extra.txt", result["mutated_files"])
        self.assertIn("site/extra.txt", result["cleaned_files"])
        self.assertFalse((self.root / "site/extra.txt").exists())
        self.assertEqual(self.project.get_task(task.id).status, "failed")

    def test_dangling_symlink_component_is_refused(self) -> None:
        (self.root / "site").mkdir()
        (self.root / "site" / "link").symlink_to(".aperio/secret")
        with self.assertRaises(PathSafetyError):
            resolve_inside(self.root, "site/link/secret")

    def test_state_symlink_is_refused(self) -> None:
        external = self.root.parent / f"{self.root.name}-external"
        external.mkdir()
        try:
            Project.init(external, name="external")
            shutil.rmtree(self.root / ".aperio")
            (self.root / ".aperio").symlink_to(external / ".aperio", target_is_directory=True)
            with self.assertRaises(StoreError):
                Project.open(self.root)
        finally:
            shutil.rmtree(external, ignore_errors=True)

    def test_state_file_symlink_is_refused(self) -> None:
        external = self.root.parent / f"{self.root.name}-queue.json"
        external.write_text("external\n", encoding="utf-8")
        try:
            (self.root / ".aperio" / "queue.json").unlink()
            (self.root / ".aperio" / "queue.json").symlink_to(external)
            with self.assertRaises(StoreError):
                self.project.save_tasks([])
            self.assertEqual(external.read_text(), "external\n")
        finally:
            external.unlink(missing_ok=True)

    def test_review_refuses_a_project_changed_after_verification(self) -> None:
        task, plan = make_plan(
            self.project,
            steps=[Step(id="write", kind="write", path="site/index.html", content="hello")],
        )
        apply_plan(self.project, plan)
        verify(self.project, task.id)
        (self.root / "site" / "index.html").write_text("changed", encoding="utf-8")
        with self.assertRaises(RunError):
            review(self.project, task.id, "qa", "confirmed")

    def test_finish_refuses_a_project_changed_after_review(self) -> None:
        task, plan = make_plan(
            self.project,
            steps=[Step(id="write", kind="write", path="site/index.html", content="hello")],
        )
        apply_plan(self.project, plan)
        verify(self.project, task.id)
        review(self.project, task.id, "qa", "confirmed")
        (self.root / "site" / "index.html").write_text("changed", encoding="utf-8")
        with self.assertRaises(RunError):
            finish(self.project, task.id)

    def test_review_refuses_a_plan_changed_after_verification(self) -> None:
        task, plan = make_plan(
            self.project,
            steps=[Step(id="write", kind="write", path="site/index.html", content="hello")],
        )
        apply_plan(self.project, plan)
        verify(self.project, task.id)
        plan.acceptance = [Acceptance(id="changed", command="false")]
        self.project.save_plan(plan)
        with self.assertRaises(RunError):
            review(self.project, task.id, "qa", "confirmed")

    def test_glob_cannot_reach_a_protected_path(self) -> None:
        (self.root / ".git").mkdir()
        (self.root / ".git" / "config").write_text("protected\n", encoding="utf-8")
        _task, plan = make_plan(
            self.project,
            steps=[Step(id="run", kind="run", command="true", writes=[".[g]it/*"])],
            allowed=["*"],
        )
        with self.assertRaises(PolicyError):
            apply_plan(self.project, plan)
        self.assertEqual((self.root / ".git" / "config").read_text(), "protected\n")

    def test_task_id_traversal_is_refused(self) -> None:
        with self.assertRaises(ModelError):
            Task.from_dict(
                {
                    "id": "../../escape",
                    "title": "bad",
                    "request": "bad",
                    "status": "planned",
                }
            )

    def test_finish_requires_review_evidence(self) -> None:
        task, plan = make_plan(
            self.project,
            steps=[Step(id="write", kind="write", path="site/index.html", content="hello")],
        )
        apply_plan(self.project, plan)
        verify(self.project, task.id)
        review(self.project, task.id, "qa", "confirmed")
        stored = self.project.get_task(task.id)
        for path in stored.evidence:
            if "review-" in Path(path).name:
                Path(path).unlink()
        with self.assertRaises(RunError):
            finish(self.project, task.id)

    def test_noop_acceptance_is_refused(self) -> None:
        with self.assertRaises(ModelError):
            Acceptance(id="noop", command="true").validate()
        with self.assertRaises(ModelError):
            Acceptance(id="noop", command="exit 0").validate()

    def test_approver_cannot_be_the_run_actor(self) -> None:
        _task, plan = make_plan(
            self.project,
            steps=[Step(id="write", kind="write", path="site/index.html", content="hello")],
            builder="agent",
        )
        plan.approval = Approval(approved_by="agent")
        self.project.save_plan(plan)
        with self.assertRaises(RunError):
            apply_plan(self.project, plan, actor="agent")

    def test_plan_path_matching(self) -> None:
        self.assertTrue(path_allowed("site/index.html", ["site/"]))
        self.assertTrue(path_allowed("site/a/b.txt", ["site"]))
        self.assertFalse(path_allowed("other/site.txt", ["site/"]))
        self.assertTrue(path_allowed("src/a.py", ["src/**/*.py"]))


if __name__ == "__main__":
    unittest.main()
