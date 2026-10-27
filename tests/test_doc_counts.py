"""Guard: documentation test counts must match the measured suite.

The count of real test definitions (measured with ast, so string fixtures
that merely contain ``def test_`` are not miscounted) must equal every
claimed suite total in the count-bearing docs. This converts the manual
"bump doc counts in the same commit" rule into an enforced gate.
"""

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Documents allowed to state a suite total, with the pattern that states it.
COUNT_BEARING = [
    ("docs/TESTING.md", r"Expected on a clean v2 tree: (\d+) tests pass"),
    ("docs/STATUS.md", r"\| Total test suite \| (\d+) passed \|"),
    ("docs/STATUS.md", r"The (\d+)-test suite"),
    ("docs/PRD.md", r"\| Total test suite \| \*\*(\d+) passed\*\* \|"),
    ("HANDOFF.md", r"\*\*(\d+) tests pass\*\*"),
    ("HANDOFF.md", r"Full suite: (\d+) tests"),
    ("HANDOFF.md", r"\| Current tests \| (\d+) passing at handoff"),
    ("HANDOFF.md", r"(\d+) tests pass locally"),
]

# STATUS.md per-suite rows: row label -> test file measured for that row.
PER_SUITE = [
    ("Core unit tests", "tests/test_core.py"),
    ("Adapter tests", "tests/test_adapter.py"),
    ("Drift tests", "tests/test_drift.py"),
    ("Mesh tests", "tests/test_mesh.py"),
    ("Mediator tests", "tests/test_mediator.py"),
    ("CLI tests", "tests/test_cli.py"),
    ("Learning tests", "tests/test_learning.py"),
    ("Skill tests", "tests/test_skillgen.py"),
    ("Toolchain tests", "tests/test_toolchain.py"),
    ("Dashboard tests", "tests/test_dashboard.py"),
    ("Security tests", "tests/test_security.py"),
    ("Todo tests", "tests/test_todo.py"),
    ("Readiness tests", "tests/test_readiness.py"),
    ("Discovery tests", "tests/test_discovery.py"),
    ("Inspection tests", "tests/test_inspect.py"),
    ("Evidence tests", "tests/test_evidence.py"),
    ("Audit tests", "tests/test_audit.py"),
    ("Repo tests", "tests/test_repo.py"),
    ("Installer tests", "tests/test_installer.py"),
]


def _file_test_count(rel: str) -> int:
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
    )


def measured_test_count() -> int:
    return sum(_file_test_count(path.relative_to(ROOT).as_posix()) for path in sorted(ROOT.glob("tests/test_*.py")))


class DocCountTests(unittest.TestCase):
    def test_documented_suite_counts_match_the_measured_suite(self) -> None:
        measured = measured_test_count()
        self.assertGreater(measured, 0, "ast found no tests; the guard is broken")
        mismatches: list[str] = []
        for rel, pattern in COUNT_BEARING:
            text = (ROOT / rel).read_text(encoding="utf-8")
            for match in re.finditer(pattern, text):
                claimed = int(match.group(1))
                if claimed != measured:
                    mismatches.append(f"{rel}: claims {claimed}, measured {measured}")
        self.assertEqual(mismatches, [], "doc test-count drift")

    def test_status_per_suite_rows_match_the_measured_modules(self) -> None:
        # Both count-bearing tables are checked: STATUS.md's plain rows and
        # PRD.md's bold rows (a previous host review caught PRD drifting
        # while STATUS was correct).
        mismatches: list[str] = []
        for doc, bold in (("docs/STATUS.md", False), ("docs/PRD.md", True)):
            text = (ROOT / doc).read_text(encoding="utf-8")
            for label, test_file in PER_SUITE:
                measured = _file_test_count(test_file)
                claimed = r"\*\*(\d+) passed\*\*" if bold else r"(\d+) passed"
                pattern = rf"\| {re.escape(label)} \| {claimed} \|"
                match = re.search(pattern, text)
                if match is None:
                    mismatches.append(f"{doc}: no per-suite row for {label}")
                elif int(match.group(1)) != measured:
                    mismatches.append(f"{doc} {label}: claims {match.group(1)}, measured {measured}")
        self.assertEqual(mismatches, [], "per-suite doc drift")


if __name__ == "__main__":
    unittest.main()
