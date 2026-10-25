"""Deterministic documentation drift checks.

This is the code-level part of the Elephant-Goldfish drift idea: a document that
points at a missing source file, test, or example is drift. It does not call an
LLM and it does not judge prose.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

DOC_FILES = ["README.md", "START-HERE.md"]
DOC_DIR = "docs"
EXCLUDED_DOCS = {"docs/ARCHIVE.md"}
PATH_PREFIXES = ("src/", "tests/", "docs/", "examples/", "skill/", "commands/", ".github/")
PATH_SUFFIXES = (".py", ".md", ".sh", ".json", ".toml", ".yml", ".yaml")
SKIP_TOKENS = {"src/", "tests/", "docs/", "examples/", "skill/", "commands/", ".github/"}


@dataclass
class Finding:
    document: str
    line: int
    target: str
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {"document": self.document, "line": self.line, "target": self.target, "reason": self.reason}


def documents(root: Path) -> list[Path]:
    result: list[Path] = []
    for name in DOC_FILES:
        path = root / name
        if path.is_file():
            result.append(path)
    docs = root / DOC_DIR
    if docs.is_dir():
        for path in sorted(docs.glob("*.md")):
            if path.relative_to(root).as_posix() not in EXCLUDED_DOCS:
                result.append(path)
    return result


def _strip_fenced(text: str) -> list[tuple[int, str]]:
    """Return (line number, line) outside triple-backtick fences."""
    rows: list[tuple[int, str]] = []
    in_fence = False
    for number, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            rows.append((number, line))
    return rows


def _exists(root: Path, target: str) -> bool:
    if any(char in target for char in "<>{}$*?["):
        return bool(list(root.glob(target)))
    return (root / target).exists()


def check_document(root: Path, path: Path) -> list[Finding]:
    root = root.resolve()
    findings: list[Finding] = []
    relative_doc = path.relative_to(root).as_posix()
    text = path.read_text(encoding="utf-8", errors="replace")
    for number, line in _strip_fenced(text):
        for match in re.finditer(r"\[[^\]]*\]\(([^)]+)\)", line):
            target = match.group(1).strip().split("#")[0]
            if not target or target.startswith(("http://", "https://", "mailto:", "/")):
                continue
            if target.startswith(("#", "~/")):
                continue
            if not (path.parent / target).exists():
                findings.append(Finding(relative_doc, number, target, "linked path does not exist"))
        for match in re.finditer(r"`([^`]+)`", line):
            token = match.group(1).strip()
            if token in SKIP_TOKENS or token.startswith(("~", ".aperio", "reports/", "Shahid/", "$")):
                continue
            if " " in token or "\n" in token or token.startswith("-"):
                continue
            if not (token.startswith(PATH_PREFIXES) or token.endswith(PATH_SUFFIXES)):
                continue
            lookup = token.split("::", 1)[0]
            if lookup.endswith("/") and (root / lookup).is_dir():
                continue
            if not _exists(root, lookup):
                findings.append(Finding(relative_doc, number, lookup, "referenced path does not exist"))
    return findings


def check(root: str | Path) -> list[Finding]:
    root_path = Path(root).resolve()
    findings: list[Finding] = []
    for path in documents(root_path):
        findings.extend(check_document(root_path, path))
    return findings


def format_findings(findings: list[Finding]) -> str:
    if not findings:
        return "DRIFT CHECK: clean"
    lines = [f"DRIFT CHECK: {len(findings)} finding(s)"]
    for finding in findings:
        lines.append(f"{finding.document}:{finding.line}: {finding.target}: {finding.reason}")
    return "\n".join(lines)
