from __future__ import annotations

import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aperio.handoff import write_handoff
from aperio.model import Acceptance, Approval, ModelError, Plan, Step, Task
from aperio.runner import RunError, apply_plan, finish, review, verify
from aperio.store import Project


def make_plan(project: Project, *, host: str = "claude", prompt: str, writes: list[str]) -> tuple[Task, Plan]:
    task = Task(id="task-host", title="Host task", request="Use a host to write one file", status="planned")
    plan = Plan(
        id="plan-host",
        task_id=task.id,
        title=task.title,
        request=task.request,
        allowed_paths=["site/"],
        steps=[
            Step(
                id="host-step",
                kind="host",
                host=host,
                prompt=prompt,
                writes=writes,
                timeout_s=30,
                max_budget_usd=0.10,
            )
        ],
        acceptance=[
            Acceptance(
                id="check",
                command=f'{sys.executable} -c "from pathlib import Path; assert Path(\'site/index.html\').is_file()"',
            )
        ],
        builder="builder",
    )
    plan.validate()
    plan.approval = Approval(approved_by="owner")
    task.plan_id = plan.id
    task.status = "approved"
    project.save_plan(plan)
    project.put_task(task)
    return task, plan


class AdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="aperio-adapter-")
        self.root = Path(self.temp.name)
        self.project = Project.init(self.root, name="adapter-test")
        self.host = self.root / "fake-host"
        self.host.write_text(
            "#!/usr/bin/env python3\n"
            "from pathlib import Path\n"
            "root = Path.cwd()\n"
            "(root / 'site').mkdir(exist_ok=True)\n"
            "(root / 'site' / 'index.html').write_text('<h1>from host</h1>')\n"
            "print('host done')\n",
            encoding="utf-8",
        )
        self.host.chmod(self.host.stat().st_mode | stat.S_IXUSR)
        self.env = mock.patch.dict(os.environ, {"APERIO_HOST_CLAUDE": str(self.host)})
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()
        self.temp.cleanup()

    def test_host_step_applies_then_verifies_reviews_and_finishes(self) -> None:
        task, plan = make_plan(
            self.project,
            prompt="Create site/index.html with the exact text from host.",
            writes=["site/index.html"],
        )
        result = apply_plan(self.project, plan, actor="builder")
        self.assertEqual(result["status"], "applied", result)
        self.assertEqual((self.root / "site/index.html").read_text(), "<h1>from host</h1>")
        self.assertEqual(result["steps"][0]["kind"], "host")
        self.assertEqual(result["steps"][0]["host"], "claude")
        self.assertIn("host done", result["steps"][0]["stdout"])

        self.assertEqual(verify(self.project, task.id)["status"], "passed")
        self.assertEqual(review(self.project, task.id, reviewer="qa", verdict="confirmed")["verdict"], "confirmed")
        self.assertEqual(finish(self.project, task.id)["status"], "done")
        handoff_text = write_handoff(self.project, task.id).read_text()
        self.assertIn("host `claude`", handoff_text)
        self.assertIn("host claude exit 0", handoff_text)

    def test_goose_adapter_builds_a_run_command(self) -> None:
        with mock.patch.dict(os.environ, {"APERIO_HOST_GOOSE": str(self.host)}):
            _task, plan = make_plan(self.project, host="goose", prompt="Create the page.", writes=["site/index.html"])
            result = apply_plan(self.project, plan)
            self.assertEqual(result["status"], "applied", result)
            self.assertEqual(result["steps"][0]["host"], "goose")
            self.assertIn("run", result["steps"][0]["command"])
            self.assertIn("--no-session", result["steps"][0]["command"])
            self.assertEqual((self.root / "site/index.html").read_text(), "<h1>from host</h1>")

    def test_host_change_outside_plan_is_rejected(self) -> None:
        self.host.write_text(
            "#!/usr/bin/env python3\n"
            "from pathlib import Path\n"
            "Path('outside.txt').write_text('bad')\n"
            "print('escaped')\n",
            encoding="utf-8",
        )
        self.host.chmod(self.host.stat().st_mode | stat.S_IXUSR)
        task, plan = make_plan(self.project, prompt="Write outside.", writes=["site/index.html"])
        result = apply_plan(self.project, plan)
        self.assertEqual(result["status"], "failed")
        self.assertFalse((self.root / "outside.txt").exists())
        self.assertTrue(any("outside.txt" in v for v in result["violations"]))
        with self.assertRaises(RunError):
            verify(self.project, task.id)

    def test_host_without_changes_fails(self) -> None:
        self.host.write_text("#!/usr/bin/env python3\nprint('no change')\n", encoding="utf-8")
        self.host.chmod(self.host.stat().st_mode | stat.S_IXUSR)
        _task, plan = make_plan(self.project, prompt="Do nothing.", writes=["site/index.html"])
        result = apply_plan(self.project, plan)
        self.assertEqual(result["status"], "failed")
        self.assertIn("no changes", " ".join(result["violations"]))

    def test_missing_host_fails_closed(self) -> None:
        _task, plan = make_plan(
            self.project,
            host="definitely-not-installed",
            prompt="Write.",
            writes=["site/index.html"],
        )
        result = apply_plan(self.project, plan)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("not installed" in v for v in result["violations"]))
        self.assertFalse((self.root / "site/index.html").exists())

    def test_host_plan_rejects_empty_writes(self) -> None:
        with self.assertRaises(ModelError):
            Step(id="h", kind="host", host="claude", prompt="x", writes=[]).validate()


if __name__ == "__main__":
    unittest.main()
