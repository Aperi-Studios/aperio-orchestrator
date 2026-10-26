"""Tests for the bounded local secret scan."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aperio.security import format_findings, scan
from aperio.store import Project


class SecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="aperio-security-")
        self.project = Project.init(Path(self.temp.name), name="security")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write(self, name: str, text: str) -> Path:
        path = self.project.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_high_confidence_token_is_found(self) -> None:
        self.write("config.py", 'AWS_ACCESS_KEY_ID = "AKIAABCDEFGHIJKLMNOP"\n')
        findings = scan(self.project)
        self.assertTrue(any(item["kind"] == "aws-access-key" for item in findings))
        self.assertEqual(findings[0]["severity"], "high")

    def test_placeholder_is_not_reported(self) -> None:
        self.write("config.py", 'api_key = "changeme"\n')
        self.assertEqual(scan(self.project), [])

    def test_sensitive_filename_is_reported(self) -> None:
        self.write(".env", "SAFE_VALUE=1\n")
        findings = scan(self.project)
        self.assertTrue(any(item["kind"] == "sensitive-file" for item in findings))

    def test_private_key_is_critical(self) -> None:
        self.write("id_rsa", "-----BEGIN OPENSSH PRIVATE KEY-----\nnot-real\n")
        findings = scan(self.project)
        self.assertTrue(any(item["kind"] == "private-key" and item["severity"] == "critical" for item in findings))

    def test_excluded_directories_are_skipped(self) -> None:
        self.write(".git/config", 'token = "AKIAIOSFODNN7EXAMPLE"\n')
        self.assertEqual(scan(self.project), [])

    def test_code_assignment_is_not_a_secret(self) -> None:
        self.write("parser.py", "token = token.strip()\n")
        self.assertEqual(scan(self.project), [])

    def test_format_is_readable(self) -> None:
        self.write("config.py", 'api_key = "sk_live_123456789"\n')
        text = format_findings(scan(self.project))
        self.assertIn("SECURITY SCAN", text)
        self.assertIn("config.py", text)
        self.assertIn("assigned-secret", text)


if __name__ == "__main__":
    unittest.main()
