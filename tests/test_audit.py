from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from aperio.audit import (
    AuditError,
    add_finding,
    brief,
    ingest,
    load,
    report,
    set_unit,
    start,
    status,
    validate,
)
from aperio.cli import cmd_audit
from aperio.handoff import build_handoff
from aperio.model import Task, new_id
from aperio.store import Project

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


class AuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="aperio-audit-")
        self.root = Path(self.temp.name) / "project"
        self.project = Project.init(self.root, name="audit-test")
        (self.root / "src" / "deep").mkdir(parents=True)
        (self.root / "src" / "app.py").write_text("print('app')\n", encoding="utf-8")
        (self.root / "src" / "deep" / "util.py").write_text("x = 1\n", encoding="utf-8")
        (self.root / "node_modules").mkdir()
        (self.root / "node_modules" / "ignored.js").write_text("ignored\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_start_creates_bounded_coverage_ledger(self) -> None:
        result = start(self.project, scope="src", profile="quick")
        self.assertTrue(result["audit_id"].startswith("audit-"))
        self.assertEqual(result["units"], 2)
        _directory, metadata, ledger, findings = load(self.project, result["audit_id"])
        paths = [unit["path"] for unit in ledger["units"]]
        self.assertEqual(paths, ["src/app.py", "src/deep/util.py"])
        self.assertNotIn(".aperio", json.dumps(ledger))
        self.assertFalse(ledger["truncated"])
        self.assertEqual(findings["findings"], [])
        self.assertEqual(metadata["execution_policy"], "read-only-source-only")
        self.assertEqual(status(self.project, result["audit_id"])["planned"], 2)

    def test_confirmed_finding_requires_evidence_and_severity(self) -> None:
        start(self.project, scope="src")
        with self.assertRaises(AuditError):
            add_finding(
                self.project,
                title="Missing check",
                status="confirmed",
                path="src/app.py",
                evidence="",
                severity="high",
            )
        with self.assertRaises(AuditError):
            add_finding(
                self.project,
                title="Missing check",
                status="confirmed",
                path="src/app.py",
                evidence="source line 1",
                severity="",
                boundary="untrusted input reaches a trusted command",
            )
        finding = add_finding(
            self.project,
            title="Missing check",
            status="confirmed",
            path="src/app.py",
            line=1,
            evidence="src/app.py:1 no validation",
            severity="high",
            boundary="untrusted input crosses into a trusted command",
        )
        self.assertTrue(finding["id"].startswith("finding-"))
        self.assertEqual(finding["unit_id"], "unit-0001")

    def test_needs_validation_cannot_have_severity(self) -> None:
        start(self.project, scope="src")
        with self.assertRaises(AuditError):
            add_finding(
                self.project,
                title="Unresolved deployment behavior",
                status="needs_validation",
                path="src/app.py",
                evidence="The proxy configuration is not in source.",
                severity="critical",
            )
        finding = add_finding(
            self.project,
            title="Unresolved deployment behavior",
            status="needs_validation",
            path="src/app.py",
            evidence="The proxy configuration is not in source.",
        )
        self.assertEqual(finding["status"], "needs_validation")
        self.assertEqual(finding["severity"], "")

    def test_confirmed_requires_boundary_line_and_anchored_evidence(self) -> None:
        start(self.project, scope="src")
        base = {
            "title": "Candidate issue",
            "status": "confirmed",
            "path": "src/app.py",
            "line": 1,
            "severity": "high",
            "boundary": "untrusted input reaches a trusted command",
            "evidence": "src/app.py:1 source line",
        }
        for omitted in ("boundary", "line"):
            values = dict(base)
            values.pop(omitted)
            with self.assertRaises(AuditError):
                add_finding(self.project, **values)
        with self.assertRaises(AuditError):
            add_finding(self.project, **{**base, "evidence": "trust me"})
        with self.assertRaises(AuditError):
            add_finding(self.project, **{**base, "unit_id": "unit-0001", "path": "src/deep/util.py"})
        self.assertTrue(add_finding(self.project, **base)["id"].startswith("finding-"))

    def test_validate_handles_malformed_values_without_crashing(self) -> None:
        start(self.project, scope="src")
        add_finding(
            self.project,
            title="Needs a fact",
            status="needs_validation",
            path="src/app.py",
            evidence="The deployment configuration is absent.",
        )
        directory, metadata, ledger, findings = load(self.project)
        metadata["profile"] = []
        findings["findings"][0]["status"] = ["confirmed"]
        findings["findings"][0]["severity"] = []
        ledger["units"][0]["status"] = []
        (directory / "run-metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        (directory / "coverage-ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
        (directory / "findings.json").write_text(json.dumps(findings), encoding="utf-8")
        errors = validate(self.project)
        self.assertTrue(errors)
        self.assertTrue(any("unknown status" in error for error in errors))
        self.assertTrue(any("unknown profile" in error for error in errors))

    def test_coverage_cap_is_only_marked_when_files_remain(self) -> None:
        many = self.root / "many"
        many.mkdir()
        for number in range(500):
            (many / f"file-{number:03d}.txt").write_text("x\n", encoding="utf-8")
        result = start(self.project, scope="many")
        self.assertFalse(result["truncated"])
        self.assertEqual(result["units"], 500)
        (many / "file-500.txt").write_text("x\n", encoding="utf-8")
        result = start(self.project, scope="many")
        self.assertTrue(result["truncated"])
        self.assertEqual(result["units"], 500)

    def test_latest_audit_uses_creation_time_not_directory_mtime(self) -> None:
        first = start(self.project, scope="src")
        directory, metadata, _ledger, _findings = load(self.project, first["audit_id"])
        metadata["created_at"] = "2099-01-01T00:00:00+00:00"
        (directory / "run-metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        second = start(self.project, scope="src")
        self.assertNotEqual(first["audit_id"], second["audit_id"])
        self.assertEqual(status(self.project)["audit_id"], first["audit_id"])

    def test_brief_and_atomic_ingest(self) -> None:
        start(self.project, scope="src")
        result = brief(self.project)
        text = Path(result["brief"]).read_text()
        self.assertIn("# Security Audit Brief", text)
        self.assertIn("src/app.py", text)
        self.assertIn('"schema": 1', text)
        source = self.root / "host-findings.json"
        source.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "findings": [
                        {
                            "title": "Anchored finding",
                            "status": "confirmed",
                            "path": "src/app.py",
                            "line": 1,
                            "severity": "high",
                            "boundary": "input reaches a trusted operation",
                            "evidence": "src/app.py:1 source",
                        },
                        {
                            "title": "Unresolved fact",
                            "status": "needs_validation",
                            "path": "src/deep/util.py",
                            "evidence": "The deployment config is absent.",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        imported = ingest(self.project, str(source))
        self.assertEqual(imported["imported"], 2)
        self.assertEqual(len(load(self.project)[3]["findings"]), 2)
        source.write_text(
            json.dumps(
                [
                    {
                        "title": "Late valid",
                        "status": "needs_validation",
                        "path": "src/app.py",
                        "evidence": "Unresolved.",
                    },
                    {"title": "Bad", "status": "needs_validation", "path": "src/app.py", "evidence": "x", "extra": 1},
                ]
            ),
            encoding="utf-8",
        )
        with self.assertRaises(AuditError):
            ingest(self.project, str(source))
        self.assertEqual(len(load(self.project)[3]["findings"]), 2)

    def test_handoff_without_audit_is_explicit(self) -> None:
        task = Task(id=new_id("task"), title="No audit yet", request="Review the build.")
        self.project.put_task(task)
        handoff = build_handoff(self.project, task.id)
        self.assertIn("## Security audit", handoff)
        self.assertIn("No source audit recorded.", handoff)

    def test_validate_rejects_orphaned_finding(self) -> None:
        start(self.project, scope="src")
        add_finding(
            self.project,
            title="Orphan",
            status="needs_validation",
            path="src/app.py",
            evidence="Unresolved.",
        )
        directory, _metadata, _ledger, findings = load(self.project)
        findings["findings"][0]["unit_id"] = "unit-9999"
        (directory / "findings.json").write_text(json.dumps(findings), encoding="utf-8")
        errors = validate(self.project)
        self.assertTrue(any("unknown coverage unit" in error for error in errors))

    def test_report_writes_artifacts_and_counts(self) -> None:
        result = start(self.project, scope="src")
        add_finding(
            self.project,
            title="Confirmed issue",
            status="confirmed",
            path="src/app.py",
            line=1,
            evidence="src/app.py:1 source line 1",
            severity="medium",
            boundary="untrusted input reaches a trusted command",
        )
        add_finding(
            self.project,
            title="Needs deployment fact",
            status="needs_validation",
            path="src/app.py",
            evidence="The proxy configuration is not in source.",
        )
        first = report(self.project, result["audit_id"])
        self.assertEqual(first["coverage_open"], 2)
        self.assertIn("Coverage is incomplete", Path(first["report"]).read_text())
        for unit in load(self.project, result["audit_id"])[2]["units"]:
            set_unit(self.project, unit_id=unit["id"], status="checked")
        report_result = report(self.project, result["audit_id"])
        self.assertEqual(report_result["confirmed"], 1)
        self.assertEqual(report_result["unresolved"], 1)
        self.assertEqual(report_result["coverage_open"], 0)
        text = Path(report_result["report"]).read_text()
        self.assertIn("# Security Audit Report", text)
        self.assertIn("Confirmed issue", text)
        self.assertIn("Needs deployment fact", text)
        self.assertEqual(status(self.project)["run_status"], "complete")
        self.assertTrue(Path(report_result["detail"]).is_file())
        self.assertTrue(Path(report_result["needs_validation"]).is_file())
        task = Task(id=new_id("task"), title="Audit handoff", request="Deliver with an audit record.")
        self.project.put_task(task)
        handoff = build_handoff(self.project, task.id)
        self.assertIn("## Security audit", handoff)
        self.assertIn("Status: **complete**", handoff)
        self.assertIn("1 confirmed", handoff)
        add_finding(
            self.project,
            title="Late finding",
            status="needs_validation",
            path="src/app.py",
            evidence="A fact arrived after the report.",
        )
        self.assertEqual(status(self.project)["run_status"], "in_progress")
        handoff = build_handoff(self.project, task.id)
        self.assertIn("Status: **in_progress**", handoff)

    def test_cli_audit_flow(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC)
        base = [sys.executable, "-m", "aperio", "--project", str(self.root)]
        result = subprocess.run(
            base + ["audit", "start", "--scope", "src", "--json"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(self.root),
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        audit_id = json.loads(result.stdout)["audit_id"]
        result = subprocess.run(
            base
            + [
                "audit",
                "add",
                "--title",
                "Evidence-backed issue",
                "--status",
                "needs_validation",
                "--path",
                "src/app.py",
                "--evidence",
                "Unresolved external fact.",
                "--json",
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(self.root),
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run(
            base + ["audit", "validate", "--audit-id", audit_id, "--json"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(self.root),
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])
        result = subprocess.run(
            base + ["audit", "report", "--audit-id", audit_id, "--json"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(self.root),
            check=False,
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(json.loads(result.stdout)["run_status"], "incomplete")
        for unit_id in ("unit-0001", "unit-0002"):
            result = subprocess.run(
                base + ["audit", "unit", "--unit-id", unit_id, "--status", "checked"],
                capture_output=True,
                text=True,
                env=env,
                cwd=str(self.root),
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run(
            base + ["audit", "report", "--audit-id", audit_id, "--json"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(self.root),
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["run_status"], "complete")

    def test_scope_outside_project_is_refused(self) -> None:
        with self.assertRaises(AuditError):
            start(self.project, scope="/tmp", profile="quick")

    def test_cmd_audit_start_prints_result(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(
                cmd_audit(
                    argparse.Namespace(
                        project=str(self.root),
                        audit_command="start",
                        scope="src",
                        profile="quick",
                        json=True,
                    )
                ),
                0,
            )
        self.assertIn("audit_id", output.getvalue())


if __name__ == "__main__":
    unittest.main()
