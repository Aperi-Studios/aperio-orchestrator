"""Tests for the gate explainer (apero explain)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from aperio.explain import TOPICS, explain
from aperio.model import Acceptance, Plan, Step
from aperio.store import Project

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


class ExplainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "proj"
        self.project = Project.init(self.root, "explain-test")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_every_topic_explains_without_a_project(self) -> None:
        for topic in TOPICS:
            info = explain(topic)
            self.assertEqual(info["topic"], topic)
            self.assertTrue(info["read_only"])
            for section in ("WHAT IT CHECKS", "WHY IT EXISTS", "COMMANDS"):
                self.assertIn(section, info["text"], topic)

    def test_every_topic_anchors_its_rationale(self) -> None:
        # A host review required each topic to connect its rationale to a
        # traceable source: a repo doc path or a named test. Some gates are
        # design decisions of the rebuild (stated as such) rather than the
        # fix of a single recorded incident; every topic must still cite at
        # least one traceable source.
        import re

        for topic in TOPICS:
            info = explain(topic, self.project)
            why = info["text"].split("WHY IT EXISTS", 1)[1].split("COMMANDS", 1)[0]
            anchors = re.findall(r"(docs/[\w./-]+|tests/[\w./-]+|skill/[\w./-]+)", why)
            self.assertTrue(anchors, f"{topic}: no traceable anchor in WHY section")

    def test_command_guidance_is_shell_safe(self) -> None:
        # A host review caught bare <placeholders> (redirections) and
        # omitted required flags; a later review caught an embedded
        # apostrophe that made a quoted example unparseable. The oracle is
        # sh -n on the assembled command: every printed command must parse.
        for topic in TOPICS:
            info = explain(topic, self.project)
            commands = info["text"].split("COMMANDS", 1)[1]
            # Assemble backslash continuations into whole commands first (a
            # host review caught per-line checking missing malformed joins).
            assembled: list[str] = []
            buffer = ""
            for line in commands.splitlines():
                stripped_line = line.strip()
                if stripped_line.endswith("\\"):
                    buffer += stripped_line[:-1].rstrip() + " "
                else:
                    buffer += stripped_line
                    if buffer.strip():
                        assembled.append(buffer.strip())
                    buffer = ""
            if buffer.strip():
                assembled.append(buffer.strip())
            for command in assembled:
                if not command.startswith("aperio "):
                    continue
                # No unquoted placeholders.
                self.assertNotRegex(command, r"(?<!['\w])<(?!')", f"{topic}: {command}")
                # The command must parse as shell syntax.
                check = subprocess.run(
                    ["/bin/sh", "-n", "-c", command],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(
                    check.returncode, 0, f"{topic}: {command}: {check.stderr.strip()}"
                )
            # Required flags per topic.
            if topic == "review":
                self.assertIn("--verdict", info["text"])
            if topic == "discovery":
                self.assertIn("--confirm 'I accept this risk'", info["text"])
            if topic == "todo":
                self.assertIn("--confirm 'I accept this task'", info["text"])
            if topic == "approval":
                self.assertIn("--confirm 'I approve this plan'", info["text"])
            if topic == "writes":
                self.assertIn("--yes", info["text"])

    def test_read_only_across_all_topics(self) -> None:
        def snapshot() -> dict[str, bytes]:
            return {
                str(p.relative_to(self.root)): p.read_bytes()
                for p in sorted(self.root.rglob("*"))
                if p.is_file()
            }

        before = snapshot()
        for topic in TOPICS:
            result = subprocess.run(
                [sys.executable, "-m", "aperio", "--project", str(self.root), "explain", topic, "--json"],
                capture_output=True, text=True, check=True,
                cwd=str(ROOT), env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(SRC)),
            )
            self.assertEqual(result.returncode, 0, topic)
        self.assertEqual(before, snapshot(), "explain must not write any state")

    def test_every_topic_includes_live_status_with_a_project(self) -> None:
        for topic in TOPICS:
            info = explain(topic, self.project)
            self.assertIn("This project now:", info["text"], topic)

    def test_unknown_topic_is_refused(self) -> None:
        with self.assertRaises(KeyError):
            explain("nonsense")

    def test_learning_status_reflects_a_dossier(self) -> None:
        before = explain("learning", self.project)["text"]
        self.assertIn("no dossier", before)
        from tests.test_next import DOSSIER

        path = self.root / "learning.json"
        path.write_text(json.dumps(DOSSIER), encoding="utf-8")
        subprocess.run(
            [sys.executable, "-m", "aperio", "--project", str(self.root), "learn", "import", str(path), "--replace"],
            capture_output=True, text=True, check=False,
            cwd=str(ROOT), env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(SRC)),
        )
        after = explain("learning", self.project)["text"]
        self.assertNotIn("no dossier", after)

    def test_cli_explain_is_read_only_and_json(self) -> None:
        def snapshot() -> dict[str, bytes]:
            # Contents, not just paths: an in-place state edit must be caught
            # too (a host review caught the path-only snapshot).
            return {
                str(p.relative_to(self.root)): p.read_bytes()
                for p in sorted(self.root.rglob("*"))
                if p.is_file()
            }

        before = snapshot()
        for topic in ("discovery", "approval", "writes"):
            result = subprocess.run(
                [sys.executable, "-m", "aperio", "--project", str(self.root), "explain", topic, "--json"],
                capture_output=True, text=True, check=True,
                cwd=str(ROOT), env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(SRC)),
            )
            data = json.loads(result.stdout)
            self.assertEqual(data["topic"], topic)
            self.assertTrue(data["read_only"])
        self.assertEqual(before, snapshot(), "explain must not write any state")

    def test_explain_does_not_migrate_legacy_state(self) -> None:
        # A host review caught explain migrating a legacy (schema-less) state
        # file under the read-only contract — including via Project.open,
        # which the CLI always calls. Run the real CLI against the legacy
        # state and assert byte-identical files (a later review caught the
        # library-level test bypassing open()).
        import hashlib

        for name in ("queue.json", "project.json", "discovery.json"):
            path = self.project.state / name
            if not path.is_file():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            data.pop("schema", None)
            path.write_text(json.dumps(data), encoding="utf-8")
        # A legacy plan file too: save one, then strip its schema.
        plan = Plan(
            id="plan-legacy-ro", task_id="task-legacy-ro", title="t", request="r",
            allowed_paths=["a.txt"],
            steps=[Step(id="s", kind="write", path="a.txt", content="x")],
            acceptance=[Acceptance(id="c", command="test -f a.txt")],
        )
        self.project.save_plan(plan)
        plan_path = self.project.state / "plans" / "plan-legacy-ro.json"
        pdata = json.loads(plan_path.read_text(encoding="utf-8"))
        pdata.pop("schema", None)
        plan_path.write_text(json.dumps(pdata), encoding="utf-8")
        before = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(self.project.state.rglob("*.json"))
        }
        for topic in TOPICS:
            result = subprocess.run(
                [sys.executable, "-m", "aperio", "--project", str(self.project.root), "explain", topic],
                capture_output=True, text=True, check=True,
                cwd=str(ROOT), env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(SRC)),
            )
            self.assertEqual(result.returncode, 0, topic)
        after = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(self.project.state.rglob("*.json"))
        }
        self.assertEqual(before, after, "explain must not migrate or write legacy state")

    def test_cli_rejects_an_unknown_topic(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "aperio", "--project", str(self.root), "explain", "nonsense"],
            capture_output=True, text=True, check=False,
            cwd=str(ROOT), env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(SRC)),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice", result.stderr)

    def test_commands_in_text_use_the_real_binary_name(self) -> None:
        # The advisor's misspelling incident (apero/aperio) applies here too:
        # every command line in every topic must start with the real binary.
        for topic in TOPICS:
            info = explain(topic, self.project)
            for line in info["text"].splitlines():
                stripped = line.strip()
                if stripped.startswith(("apero ", "aperio ")):
                    self.assertTrue(stripped.startswith("aperio "), f"{topic}: {stripped}")


if __name__ == "__main__":
    unittest.main()
