from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aperio.drift import check

ROOT = Path(__file__).resolve().parents[1]


class DriftTests(unittest.TestCase):
    def test_missing_relative_link_is_reported(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aperio-drift-") as temp:
            root = Path(temp)
            (root / "README.md").write_text("[missing](docs/nope.md)\n", encoding="utf-8")
            findings = check(root)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].target, "docs/nope.md")

    def test_existing_link_passes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aperio-drift-") as temp:
            root = Path(temp)
            (root / "docs").mkdir()
            (root / "docs" / "exists.md").write_text("# exists\n", encoding="utf-8")
            (root / "README.md").write_text("[exists](docs/exists.md)\n", encoding="utf-8")
            self.assertEqual(check(root), [])

    def test_missing_inline_path_is_reported(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aperio-drift-") as temp:
            root = Path(temp)
            (root / "README.md").write_text("See `src/aperio/missing.py`.\n", encoding="utf-8")
            findings = check(root)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].target, "src/aperio/missing.py")

    def test_fenced_code_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aperio-drift-") as temp:
            root = Path(temp)
            (root / "README.md").write_text("```\n[missing](docs/nope.md)\n```\n", encoding="utf-8")
            self.assertEqual(check(root), [])

    def test_this_repository_is_clean(self) -> None:
        self.assertEqual(check(ROOT), [])


if __name__ == "__main__":
    unittest.main()
