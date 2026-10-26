from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from aperio.readiness import import_readiness
from aperio.store import Project

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def record() -> dict:
    return {
        "schema": 1,
        "preflight": {
            "audience": "Small business owners",
            "success_measure": "A visitor submits a working enquiry",
            "features": ["Public page", "Enquiry form"],
            "out_of_scope": ["Customer accounts"],
            "integrations": ["Email delivery"],
            "constraints": ["Mobile first", "No tracking"],
            "review_owner": "owner",
            "approval_path": "Owner approves the plan and each task",
        },
        "deploy": {
            "hosting": "Local static preview for this fixture",
            "domain": "localhost",
            "tls": "Not applicable to the local fixture",
            "env_names": ["EXAMPLE_API_URL"],
            "build": "python3 -m compileall src",
            "migrate": "No database migration",
            "backup": "Copy the release directory",
            "restore": "Restore the copied release directory",
            "ci_cd": "Local test command",
            "rollback": "Restore the previous release copy",
            "monitoring": "Read the local command output",
            "smoke": "Open the public route and submit the form",
        },
        "aftersales": {
            "support_window": "30 days",
            "escalation_owner": "owner",
            "logs": "Local application log",
            "metrics": "Enquiry count",
            "alerts": "Owner email on failure",
            "backup_schedule": "Daily",
            "restore_drill": "Monthly restore into a scratch directory",
            "update_policy": "Review dependencies monthly",
            "admin_recovery": "Owner holds the recovery procedure",
            "docs": "README and handoff",
        },
        "design": {
            "surface_class": "marketing",
            "contract": "Clear hierarchy, restrained type, one accent, real content",
            "references": ["Owner-provided competitor example"],
            "accessibility": "Keyboard, contrast, labels, visible focus",
            "responsive": "390x844 and 1440x900",
            "originality": "No copied template composition",
            "review_owner": "owner",
        },
        "security": {
            "threat_model": "Local fixture: abuse cases are form spam and path escape",
            "assets": ["Enquiry data"],
            "trust_boundaries": ["Browser to server", "Server to email provider"],
            "controls": ["Server-side validation", "No secrets in the client"],
            "dependency_scan": "Run the approved dependency scan",
            "secret_scan": "Run the approved secret scan",
            "headers": "Set the approved headers on the deployed shape",
            "incident": "Owner disables the form and rotates the mail credential",
            "unresolved_severity": "none",
        },
    }


class ReadinessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="aperio-readiness-")
        self.root = Path(self.temp.name) / "project"
        self.project = Project.init(self.root, name="readiness-test")
        self.file = self.root / "readiness.json"
        self.file.write_text(json.dumps(record()), encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_complete_record_is_ready(self) -> None:
        result = import_readiness(self.project, str(self.file))
        self.assertTrue(result["ready"], result)
        self.assertTrue(all(result["sections"].values()))

    def test_missing_section_blocks(self) -> None:
        data = record()
        data.pop("deploy")
        self.file.write_text(json.dumps(data), encoding="utf-8")
        result = import_readiness(self.project, str(self.file))
        self.assertFalse(result["ready"])
        self.assertTrue(any("deploy" in issue for issue in result["issues"]))

    def test_high_unresolved_security_blocks(self) -> None:
        data = record()
        data["security"]["unresolved_severity"] = "high"
        self.file.write_text(json.dumps(data), encoding="utf-8")
        result = import_readiness(self.project, str(self.file))
        self.assertFalse(result["ready"])
        self.assertTrue(any("high or critical" in issue for issue in result["issues"]))

    def test_design_references_are_required(self) -> None:
        data = record()
        data["design"]["references"] = []
        self.file.write_text(json.dumps(data), encoding="utf-8")
        result = import_readiness(self.project, str(self.file))
        self.assertFalse(result["ready"])
        self.assertTrue(any("design.references" in issue for issue in result["issues"]))

    def test_cli_import_and_status(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC)
        base = [sys.executable, "-m", "aperio", "--project", str(self.root)]
        result = subprocess.run(
            base + ["readiness", "import", str(self.file), "--json"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(ROOT),
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["ready"])
        result = subprocess.run(
            base + ["readiness", "status", "--json"],
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
