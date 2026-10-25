from __future__ import annotations

import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aperio.adapter import HostError, run_host_review
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

    def test_codex_adapter_builds_an_exec_command(self) -> None:
        with mock.patch.dict(os.environ, {"APERIO_HOST_CODEX": str(self.host)}):
            _task, plan = make_plan(self.project, host="codex", prompt="Create the page.", writes=["site/index.html"])
            result = apply_plan(self.project, plan)
            self.assertEqual(result["status"], "applied", result)
            self.assertEqual(result["steps"][0]["host"], "codex")
            self.assertIn("exec", result["steps"][0]["command"])
            self.assertIn("--sandbox", result["steps"][0]["command"])
            self.assertIn("workspace-write", result["steps"][0]["command"])
            self.assertEqual((self.root / "site/index.html").read_text(), "<h1>from host</h1>")

    def test_host_review_confirms_a_verified_task(self) -> None:
        task, plan = make_plan(
            self.project,
            prompt="Create the page.",
            writes=["site/index.html"],
        )
        apply_plan(self.project, plan)
        verify(self.project, task.id)
        reviewer = self.root / "fake-reviewer"
        reviewer.write_text(
            "#!/usr/bin/env python3\n"
            "print('{\"verdict\":\"confirmed\",\"findings\":[],\"notes\":\"checked\"}')\n",
            encoding="utf-8",
        )
        reviewer.chmod(reviewer.stat().st_mode | stat.S_IXUSR)
        with mock.patch.dict(os.environ, {"APERIO_HOST_CLAUDE": str(reviewer)}):
            result = run_host_review(self.project, task.id, host="claude", budget_usd=0.10)
        self.assertEqual(result["verdict"], "confirmed")
        stored = self.project.get_task(task.id)
        self.assertEqual(stored.status, "reviewed")
        self.assertIsNotNone(stored.review)
        assert stored.review is not None
        self.assertEqual(stored.review.reviewer, "claude")

    def test_host_review_refutation_sets_failed(self) -> None:
        task, plan = make_plan(self.project, prompt="Create the page.", writes=["site/index.html"])
        apply_plan(self.project, plan)
        verify(self.project, task.id)
        reviewer = self.root / "fake-reviewer-refute"
        reviewer.write_text(
            "#!/usr/bin/env python3\n"
            "print('{\"verdict\":\"refuted\",\"findings\":[{\"severity\":\"P1\",\"claim\":\"missing heading\"}],\"notes\":\"not acceptable\"}')\n",
            encoding="utf-8",
        )
        reviewer.chmod(reviewer.stat().st_mode | stat.S_IXUSR)
        with mock.patch.dict(os.environ, {"APERIO_HOST_CLAUDE": str(reviewer)}):
            result = run_host_review(self.project, task.id, host="claude", budget_usd=0.10)
        self.assertEqual(result["verdict"], "refuted")
        self.assertEqual(self.project.get_task(task.id).status, "failed")
        self.assertEqual(len(result["findings"]), 1)

    def test_host_review_malformed_output_fails(self) -> None:
        task, plan = make_plan(self.project, prompt="Create the page.", writes=["site/index.html"])
        apply_plan(self.project, plan)
        verify(self.project, task.id)
        reviewer = self.root / "fake-reviewer-bad"
        reviewer.write_text("#!/usr/bin/env python3\nprint('not json')\n", encoding="utf-8")
        reviewer.chmod(reviewer.stat().st_mode | stat.S_IXUSR)
        with mock.patch.dict(os.environ, {"APERIO_HOST_CLAUDE": str(reviewer)}), self.assertRaises(HostError):
            run_host_review(self.project, task.id, host="claude", budget_usd=0.10)

    def test_host_cannot_review_its_own_build(self) -> None:
        task, plan = make_plan(self.project, prompt="Create the page.", writes=["site/index.html"])
        plan.builder = "claude"
        self.project.save_plan(plan)
        apply_plan(self.project, plan)
        verify(self.project, task.id)
        with self.assertRaises(HostError):
            run_host_review(self.project, task.id, host="claude", budget_usd=0.10)

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

    def test_host_change_outside_step_writes_is_rejected(self) -> None:
        self.host.write_text(
            "#!/usr/bin/env python3\n"
            "from pathlib import Path\n"
            "Path('site').mkdir(exist_ok=True)\n"
            "Path('site/index.html').write_text('<h1>ok</h1>')\n"
            "Path('site/extra.html').write_text('undeclared')\n"
            "print('wrote extra')\n",
            encoding="utf-8",
        )
        self.host.chmod(self.host.stat().st_mode | stat.S_IXUSR)
        _task, plan = make_plan(self.project, prompt="Write one page.", writes=["site/index.html"])
        result = apply_plan(self.project, plan)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("site/extra.html" in v for v in result["violations"]))
        self.assertFalse((self.root / "site/extra.html").exists())
        self.assertFalse((self.root / "site/index.html").exists())

    def test_host_symlink_is_rejected(self) -> None:
        self.host.write_text(
            "#!/usr/bin/env python3\n"
            "from pathlib import Path\n"
            "Path('site').mkdir(exist_ok=True)\n"
            "Path('site/link').symlink_to('/etc/passwd')\n"
            "print('made link')\n",
            encoding="utf-8",
        )
        self.host.chmod(self.host.stat().st_mode | stat.S_IXUSR)
        _task, plan = make_plan(self.project, prompt="Make a link.", writes=["site/link"])
        result = apply_plan(self.project, plan)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("symlink" in v for v in result["violations"]))
        self.assertFalse((self.root / "site/link").exists())

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
