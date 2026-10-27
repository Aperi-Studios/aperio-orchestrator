"""Local secret and sensitive-file scan.

This is a fast, bounded review aid. It does not replace a dependency scanner,
an entropy scanner, a history scan, or an external penetration test.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .store import Project

MAX_FILE_BYTES = 1_000_000
EXCLUDED_DIRS = {
    ".git",
    ".aperio",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
}
TEST_DIRS = {"tests", "test"}
SENSITIVE_NAMES = {".env", ".env.local", ".env.production", ".npmrc", ".pypirc"}
PLACEHOLDERS = {"", "changeme", "change-me", "example", "placeholder", "your-key", "xxx", "todo"}
EXAMPLE_VALUES = {"AKIAIOSFODNN7EXAMPLE", "***", "do-not-read"}

PATTERNS = [
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"), "critical"),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "high"),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"), "high"),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "high"),
    (
        "assigned-secret",
        re.compile(
            # no prefix restriction: letter-prefixed compounds like MYSECRET,
            # AUTHTOKEN, ADMINPASSWORD count. Prose can false-positive (e.g.
            # "password: authentication") — findings are reviewable output,
            # not automated actions. {12,} mirrors the value filter's <12
            # drop: anything the regex admits this short never becomes a finding.
            r"(?i)(?:api[_-]?key|secret|token|password|passwd|client[_-]?secret)[a-z0-9_]*"
            r"\s*[:=]\s*['\"]?([^\s'\"#]{12,})"
        ),
        "medium",
    ),
]


def _iter_files(root: Path, include_tests: bool = False):
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(root)
        if any(part in EXCLUDED_DIRS for part in rel.parts):
            continue
        if not include_tests and any(part in TEST_DIRS for part in rel.parts):
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        yield rel, path


def scan(project: Project, include_tests: bool = False) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for rel, path in _iter_files(project.root, include_tests=include_tests):
        if path.name in SENSITIVE_NAMES:
            findings.append(
                {
                    "path": rel.as_posix(),
                    "line": 0,
                    "kind": "sensitive-file",
                    "severity": "medium",
                    "preview": path.name,
                }
            )
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            for kind, pattern, severity in PATTERNS:
                match = pattern.search(line)
                if not match:
                    continue
                value = match.group(1) if match.lastindex else match.group(0)
                if (
                    value.strip() in EXAMPLE_VALUES
                    or value.strip().lower() in PLACEHOLDERS
                    or value.startswith("<")
                    or len(value.strip()) < 12
                    or any(char in value for char in ".[]()")
                ):
                    continue
                preview = line.strip()
                if len(preview) > 160:
                    preview = preview[:157] + "..."
                findings.append(
                    {
                        "path": rel.as_posix(),
                        "line": number,
                        "kind": kind,
                        "severity": severity,
                        "preview": preview,
                    }
                )
    # One row per location and kind; the same line can match a broad and a
    # narrow rule, but the report should stay readable.
    unique: dict[tuple[str, int, str], dict[str, Any]] = {}
    for finding in findings:
        unique[(finding["path"], finding["line"], finding["kind"])] = finding
    return sorted(unique.values(), key=lambda item: (item["path"], item["line"], item["kind"]))


def format_findings(findings: list[dict[str, Any]]) -> str:
    if not findings:
        return "SECURITY SCAN: no obvious secrets found"
    lines = [f"SECURITY SCAN: {len(findings)} finding(s)"]
    for finding in findings:
        where = finding["path"] + (f":{finding['line']}" if finding["line"] else "")
        lines.append(f"- {finding['severity'].upper()} {finding['kind']} at {where}: {finding['preview']}")
    return "\n".join(lines)
