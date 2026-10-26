from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from aperio.evidence import EvidenceError, add, entries, format_entries
from aperio.store import Project

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


class EvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="aperio-evidence-")
        self.root = Path(self.temp.name) / "project"
        self.project = Project.init(self.root, name="evidence-test")
        (self.root / "notes.md").write_text("owner notes\n", encoding="utf-8")
        (self.root / "image.bin").write_bytes(b"\x00\x01\x02")
        (self.root / ".env").write_text("SECRET=do-not-read\n", encoding="utf-8")
        (self.root / ".env.example").write_text("SECRET=\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_add_records_hash_without_copying_content(self) -> None:
        entry = add(self.project, "notes.md", label="Owner brief")
        self.assertEqual(entry["label"], "Owner brief")
        self.assertEqual(entry["path"], "notes.md")
        self.assertEqual(len(entry["sha256"]), 64)
        self.assertEqual(entry["bytes"], 12)
        self.assertNotIn("owner notes", json.dumps(entries(self.project)))
        self.assertTrue((self.root / ".aperio" / "evidence" / "manifest.json").is_file())

    def test_duplicate_is_idempotent(self) -> None:
        first = add(self.project, "notes.md")
        second = add(self.project, "notes.md", label="Other label")
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(entries(self.project)["entries"]), 1)

    def test_paths_outside_and_symlinks_are_refused(self) -> None:
        outside = Path(self.temp.name) / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        with self.assertRaises(EvidenceError):
            add(self.project, str(outside))
        link = self.root / "link.txt"
        link.symlink_to(outside)
        with self.assertRaises(EvidenceError):
            add(self.project, "link.txt")

    def test_environment_files_are_refused(self) -> None:
        with self.assertRaises(EvidenceError):
            add(self.project, ".env")
        entry = add(self.project, ".env.example")
        self.assertEqual(entry["path"], ".env.example")

    def test_cli_add_and_list(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC)
        base = [sys.executable, "-m", "aperio", "--project", str(self.root)]
        result = subprocess.run(
            base + ["evidence", "add", "notes.md", "--label", "Brief", "--json"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(self.root),
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("sha256", result.stdout)
        result = subprocess.run(
            base + ["evidence", "list", "--json"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(self.root),
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(result.stdout)["entries"]), 1)
        self.assertIn("Evidence files", format_entries(entries(self.project)))


if __name__ == "__main__":
    unittest.main()
