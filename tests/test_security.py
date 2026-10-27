"""Tests for the bounded local secret scan."""

from __future__ import annotations

import json
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

    def test_upper_snake_assignment_is_found(self) -> None:
        # S1/F-1: names prefixed with underscores (DB_PASSWORD), keyword-internal
        # compounds (SECRET_FALLBACK, AWS_SECRET_ACCESS_KEY, API_KEY_RESTRICTED),
        # and letter-prefixed compounds (MYSECRET, AUTHTOKEN, ADMINPASSWORD) are
        # all found; F-2: the regex floor matches the value filter (>= 12 chars).
        self.write(
            "config.py",
            'DB_PASSWORD = "Sup3rSecret99"\n'
            'SECRET_FALLBACK = "Sup3rSecret99"\n'
            'AWS_SECRET_ACCESS_KEY = "Sup3rSecret99"\n'
            'API_KEY_RESTRICTED = "Sup3rSecret99"\n'
            'MYSECRET = "Sup3rSecret99"\n'
            'AUTHTOKEN = "Sup3rSecret99"\n'
            'ADMINPASSWORD = "Sup3rSecret99"\n'
            'DB_PASSWORD = "Sup3rS123"\n',  # 9-char value: below the 12-char floor
        )
        findings = scan(self.project)
        matches = [
            item for item in findings
            if item["kind"] == "assigned-secret" and "Sup3rSecret99" in json.dumps(item)
        ]
        self.assertEqual(len(matches), 7, findings)

    def test_format_is_readable(self) -> None:
        self.write("config.py", 'api_key = "sk_live_123456789"\n')
        text = format_findings(scan(self.project))
        self.assertIn("SECURITY SCAN", text)
        self.assertIn("config.py", text)
        self.assertIn("assigned-secret", text)


if __name__ == "__main__":
    unittest.main()
