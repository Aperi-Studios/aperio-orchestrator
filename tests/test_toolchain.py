"""Tests for the manifest-driven toolchain installer."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from aperio.store import Project
from aperio.toolchain import (
    APPROVAL,
    ToolError,
    format_status,
    import_manifest,
    install,
    status,
    validate_manifest,
)


def tool(**overrides):
    row = {
        "name": "demo-tool",
        "kind": "package",
        "source": "local test fixture",
        "version": "1.0.0",
        "license": "MIT",
        "scope": "project",
        "permissions": ["project files"],
        "network": False,
        "credentials": False,
        "elevated": False,
        "cost_usd": 0,
        "install": [sys.executable, "-c", "print('installed')"],
        "verify": [sys.executable, "-c", "print('verified')"],
    }
    row.update(overrides)
    return row


class ToolchainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="aperio-tool-")
        self.root = Path(self.temp.name)
        self.project = Project.init(self.root, name="tools")
        self.manifest = self.root / "toolchain.json"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write(self, tools: list[dict]) -> Path:
        self.manifest.write_text(json.dumps({"schema": 1, "tools": tools}), encoding="utf-8")
        return self.manifest

    def test_import_and_status(self) -> None:
        data = import_manifest(self.project, str(self.write([tool()])))
        self.assertEqual(data["count"], 1)
        self.assertIsNone(status(self.project)["tools"][0]["installed_at"])
        self.assertIn("demo-tool", format_status(data))

    def test_project_scoped_tool_installs_and_verifies_without_owner_prompt(self) -> None:
        import_manifest(self.project, str(self.write([tool()])))
        result = install(self.project, "demo-tool")
        self.assertEqual(result["name"], "demo-tool")
        self.assertTrue(result["installed_at"])
        self.assertTrue(status(self.project)["tools"][0]["verified_at"])

    def test_risky_tool_requires_exact_owner_confirmation(self) -> None:
        import_manifest(self.project, str(self.write([tool(network=True)])))
        with self.assertRaises(ToolError) as caught:
            install(self.project, "demo-tool")
        self.assertIn("--confirm", str(caught.exception))
        result = install(
            self.project,
            "demo-tool",
            approved_by="owner",
            confirm=APPROVAL,
        )
        self.assertTrue(result["installed_at"])

    def test_global_tool_requires_exact_owner_confirmation(self) -> None:
        import_manifest(self.project, str(self.write([tool(scope="global")])))
        with self.assertRaises(ToolError):
            install(self.project, "demo-tool")
        result = install(self.project, "demo-tool", approved_by="owner", confirm=APPROVAL)
        self.assertEqual(result["scope"], "global")

    def test_bad_manifest_is_rejected(self) -> None:
        data = {"schema": 1, "tools": [tool(license="")]}
        issues = validate_manifest(data)
        self.assertTrue(any("license" in issue for issue in issues))
        with self.assertRaises(ToolError):
            import_manifest(self.project, str(self.write([tool(license="")])))

    def test_failed_verification_blocks_the_install_record(self) -> None:
        import_manifest(
            self.project,
            str(
                self.write(
                    [
                        tool(
                            verify=[
                                sys.executable,
                                "-c",
                                "import sys; sys.exit(3)",
                            ]
                        )
                    ]
                )
            ),
        )
        with self.assertRaises(ToolError):
            install(self.project, "demo-tool")
        self.assertIsNone(status(self.project)["tools"][0]["installed_at"])

    def test_unknown_tool_is_refused(self) -> None:
        import_manifest(self.project, str(self.write([tool()])))
        with self.assertRaises(ToolError):
            install(self.project, "missing-tool")

    def test_future_state_schema_is_refused(self) -> None:
        path = self.project.state / "toolchain.json"
        path.write_text(json.dumps({"schema": 999, "tools": []}), encoding="utf-8")
        with self.assertRaises(ToolError) as caught:
            status(self.project)
        self.assertIn("unsupported state schema", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
