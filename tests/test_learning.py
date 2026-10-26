from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from aperio.learning import (
    LearningError,
    import_dossier,
    record_proof,
    status,
    validate,
)
from aperio.store import Project

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def dossier() -> dict:
    return {
        "schema": 1,
        "stack": {
            "surface": "website",
            "runtime": "Python 3.14",
            "framework": "standard library HTTP",
            "package_manager": "none",
            "database": "SQLite 3",
            "hosting": "local",
            "versions": {"python": "3.14.7", "sqlite": "3.45"},
            "constraints": ["No network dependency for the learning proof"],
        },
        "sources": [
            {
                "title": "Python documentation",
                "url": "https://docs.python.org/3/",
                "kind": "official_docs",
                "version": "3.14",
                "accessed": "2026-10-26",
                "official": True,
            }
        ],
        "skills": [],
        "skill_gap": {
            "needed": False,
            "reason": "The standard library is sufficient for this proof; no dedicated skill is required.",
        },
        "mcps": [],
        "proof": {
            "command": "python3 -c \"print('proof')\"",
            "exit_code": 0,
            "output_sha256": "0" * 64,
            "recorded_at": "2026-10-26T00:00:00Z",
        },
        "teachback": {
            "agent": "builder",
            "summary": (
                "I can explain why the standard library is enough for this bounded proof, "
                "which modules implement the state and server, and which parts remain unproven."
            ),
            "uncertainties": ["Production deployment is outside this proof."],
        },
        "competency": {
            "agent": "builder",
            "verdict": "demonstrated",
            "evidence": "The proof command runs and the output is recorded in proof.output_sha256.",
            "recorded_at": "2026-10-26T00:00:00Z",
        },
    }


class LearningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="aperio-learning-")
        self.root = Path(self.temp.name) / "project"
        self.project = Project.init(self.root, name="learning-test")
        self.dossier_path = self.root / "dossier.json"
        self.dossier_path.write_text(json.dumps(dossier()), encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def imported(self, data: dict | None = None, replace: bool = False) -> dict:
        path = self.root / "dossier.json"
        path.write_text(json.dumps(data or dossier()), encoding="utf-8")
        return import_dossier(self.project, str(path), replace=replace)

    def test_valid_dossier_is_ready(self) -> None:
        result = self.imported()
        self.assertFalse(result["ready"])
        result = record_proof(self.project, f'{sys.executable} -c "print(1)"')
        self.assertTrue(result["ready"], result)
        self.assertEqual(result["sources"], 1)
        self.assertEqual(len(result["digest"]), 64)
        self.assertTrue((self.root / ".aperio" / "learning.json").is_file())

    def test_import_requires_replace(self) -> None:
        self.imported()
        with self.assertRaises(LearningError):
            self.imported()

    def test_missing_proof_is_not_ready(self) -> None:
        data = dossier()
        data.pop("proof")
        result = self.imported(data)
        self.assertFalse(result["ready"])
        self.assertTrue(any("proof" in issue for issue in result["issues"]))

    def test_official_source_or_fallback_is_required(self) -> None:
        data = dossier()
        data["sources"][0]["official"] = False
        result = self.imported(data)
        self.assertFalse(result["ready"])
        self.assertTrue(any("official source" in issue for issue in result["issues"]))
        data["stack"]["fallback_reason"] = "Official documentation is unavailable in this fixture."
        result = self.imported(data, replace=True)
        self.assertFalse(result["ready"])
        result = record_proof(self.project, f'{sys.executable} -c "print(1)"')
        self.assertTrue(result["ready"], result)

    def test_global_mcp_needs_owner_approval(self) -> None:
        data = dossier()
        data["mcps"] = [
            {
                "name": "global-tool",
                "source": "https://example.com/tool",
                "version": "1.0.0",
                "license": "MIT",
                "scope": "global",
                "status": "available",
                "permissions": ["filesystem"],
                "credentials": False,
                "paid": False,
                "network": False,
                "elevated": False,
                "approved": False,
            }
        ]
        result = self.imported(data)
        self.assertFalse(result["ready"])
        self.assertTrue(any("approval" in issue for issue in result["issues"]))
        data["mcps"][0]["approved"] = True
        result = self.imported(data, replace=True)
        self.assertFalse(result["ready"])
        result = record_proof(self.project, f'{sys.executable} -c "print(1)"')
        self.assertTrue(result["ready"], result)

    def test_needed_skill_must_be_created_and_tested(self) -> None:
        data = dossier()
        data["skill_gap"] = {"needed": True, "created": True, "path": "skills/custom", "reason": "No bundled skill."}
        result = self.imported(data)
        self.assertFalse(result["ready"])
        self.assertTrue(any("SKILL.md" in issue for issue in result["issues"]))
        (self.root / "skills" / "custom").mkdir(parents=True)
        (self.root / "skills" / "custom" / "SKILL.md").write_text("# Custom skill\n", encoding="utf-8")
        result = self.imported(data, replace=True)
        self.assertFalse(result["ready"])
        result = record_proof(self.project, f'{sys.executable} -c "print(1)"')
        self.assertTrue(result["ready"], result)

    def test_teachback_must_show_understanding(self) -> None:
        data = dossier()
        data["teachback"]["summary"] = "I know it."
        result = self.imported(data)
        self.assertFalse(result["ready"])
        self.assertTrue(any("40 characters" in issue for issue in result["issues"]))

    def test_proof_runs_and_records_exit(self) -> None:
        self.imported()
        command = f'{sys.executable} -c "print(123)"'
        result = record_proof(self.project, command)
        self.assertTrue(result["ready"], result)
        data = json.loads((self.project.root / ".aperio" / "learning.json").read_text(encoding="utf-8"))
        self.assertIsInstance(data["proof"]["duration_ms"], int)
        self.assertGreaterEqual(data["proof"]["duration_ms"], 0)
        result = record_proof(self.project, f'{sys.executable} -c "raise SystemExit(1)"')
        self.assertFalse(result["ready"])
        self.assertTrue(any("exit_code" in issue for issue in result["issues"]))

    def test_tampered_digest_is_refused(self) -> None:
        self.imported()
        path = self.root / ".aperio" / "learning.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["stack"]["framework"] = "tampered"
        path.write_text(json.dumps(data), encoding="utf-8")
        result = status(self.project)
        self.assertFalse(result["ready"])
        self.assertTrue(any("digest" in issue for issue in result["issues"]))
        self.assertIn("digest", " ".join(validate(self.project)))

    def test_cli_import_and_status(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC)
        base = [sys.executable, "-m", "aperio", "--project", str(self.root)]
        result = subprocess.run(
            base + ["learn", "import", str(self.dossier_path), "--json"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(ROOT),
            check=False,
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ready"], payload)
        result = subprocess.run(
            base + ["learn", "proof", "--command", f'{sys.executable} -c "print(1)"', "--json"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(ROOT),
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["ready"])
        result = subprocess.run(
            base + ["learn", "status", "--json"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(ROOT),
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["ready"])


if __name__ == "__main__":
    unittest.main()
