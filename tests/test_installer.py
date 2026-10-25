from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("bash") and os.name != "nt", "bash installer test")
class InstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="aperio-installer-")
        self.root = Path(self.temp.name)
        self.prefix = self.root / "prefix"
        self.home = self.root / "home"
        self.skill_home = self.root / "skills"
        self.home.mkdir()
        self.env = os.environ.copy()
        self.env["HOME"] = str(self.home)
        self.env["APERIO_SKILL_HOME"] = str(self.skill_home)
        self.env.pop("APERIO_PREFIX", None)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_install(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(ROOT / "install.sh"), "--prefix", str(self.prefix), *args],
            check=False,
            capture_output=True,
            text=True,
            env=self.env,
            cwd=str(ROOT),
            timeout=60,
        )

    def test_dry_run_writes_nothing(self) -> None:
        result = self.run_install("--no-skill", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.prefix.exists())
        self.assertIn("dry run", result.stdout)

    def test_dry_run_does_not_create_the_command(self) -> None:
        result = self.run_install("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.home / ".claude" / "commands" / "aperio.md").exists())
        self.assertFalse((self.skill_home / "aperio").exists())

    def test_install_is_idempotent_and_uninstalls(self) -> None:
        first = self.run_install()
        self.assertEqual(first.returncode, 0, first.stderr)
        binary = self.prefix / "bin" / "aperio"
        skill = self.skill_home / "aperio" / "SKILL.md"
        command = self.home / ".claude" / "commands" / "aperio.md"
        self.assertTrue(binary.is_file())
        self.assertTrue(skill.is_file())
        self.assertTrue(command.is_file())
        self.assertIn("Aperio v2", command.read_text())
        self.assertEqual((self.skill_home / "aperio" / "VERSION").read_text().strip(), "2.0.0.dev0")

        version = subprocess.run(
            [str(binary), "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(version.returncode, 0, version.stderr)
        self.assertIn("aperio 2.0.0.dev0", version.stdout)

        project = self.root / "project"
        init = subprocess.run(
            [str(binary), "--project", str(project), "init", str(project), "--name", "installed"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(init.returncode, 0, init.stderr)
        doctor = subprocess.run(
            [str(binary), "--project", str(project), "doctor"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)

        second = self.run_install()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(len(list((self.skill_home).glob("aperio*"))), 1)

        removed = self.run_install("--uninstall")
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertFalse(binary.exists())
        self.assertFalse((self.skill_home / "aperio").exists())
        self.assertFalse(command.exists())

    def test_prefix_with_spaces(self) -> None:
        prefix = self.root / "prefix with spaces"
        install = subprocess.run(
            ["bash", str(ROOT / "install.sh"), "--prefix", str(prefix), "--no-skill"],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(install.returncode, 0, install.stderr)
        version = subprocess.run(
            [str(prefix / "bin" / "aperio"), "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(version.returncode, 0, version.stderr)
        self.assertIn("aperio", version.stdout.lower())

    def test_powershell_installer(self) -> None:
        if not shutil.which("pwsh"):
            self.skipTest("pwsh is not installed")
        prefix = self.root / "ps-prefix"
        install = subprocess.run(
            ["pwsh", "-NoProfile", "-File", str(ROOT / "install.ps1"), "-Prefix", str(prefix), "-NoSkill"],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(install.returncode, 0, install.stderr)
        launcher = prefix / "bin" / "aperio_launcher.py"
        self.assertTrue(launcher.is_file())
        version = subprocess.run(
            [sys.executable, str(launcher), "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(version.returncode, 0, version.stderr)
        remove = subprocess.run(
            ["pwsh", "-NoProfile", "-File", str(ROOT / "install.ps1"), "-Prefix", str(prefix), "-NoSkill", "-Uninstall"],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(remove.returncode, 0, remove.stderr)
        self.assertFalse((prefix / "bin" / "aperio.cmd").exists())

    def test_unsafe_prefix_is_refused(self) -> None:
        result = subprocess.run(
            ["bash", str(ROOT / "install.sh"), "--prefix", "/", "--dry-run"],
            check=False,
            capture_output=True,
            text=True,
            env=self.env,
            cwd=str(ROOT),
            timeout=30,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("unsafe prefix", result.stderr)


if __name__ == "__main__":
    unittest.main()
