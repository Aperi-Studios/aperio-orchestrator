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
    ("docs/PRD.md", r"\| Total test suite \| \*\*(\d+) passed\*\* \|"),
    ("HANDOFF.md", r"\*\*(\d+) tests pass\*\*"),
    ("HANDOFF.md", r"Full suite: (\d+) tests"),
    ("HANDOFF.md", r"\| Current tests \| (\d+) passing at handoff"),
    ("HANDOFF.md", r"(\d+) tests pass locally"),
]


def measured_test_count() -> int:
    total = 0
    for path in sorted(ROOT.glob("tests/test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        total += sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        )
    return total


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


if __name__ == "__main__":
    unittest.main()
