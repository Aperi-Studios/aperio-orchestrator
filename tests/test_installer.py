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

    def test_dry_run_uninstall_removes_nothing(self) -> None:
        install = self.run_install()
        self.assertEqual(install.returncode, 0, install.stderr)
        result = self.run_install("--uninstall", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.prefix / "bin" / "aperio").is_file())
        self.assertTrue((self.skill_home / "aperio" / "SKILL.md").is_file())
        self.assertIn("would:", result.stdout)

    def test_uninstall_preserves_user_files_in_the_skill_directory(self) -> None:
        install = self.run_install()
        self.assertEqual(install.returncode, 0, install.stderr)
        skill_dir = self.skill_home / "aperio"
        note = skill_dir / "my-notes.md"
        note.write_text("mine\n", encoding="utf-8")
        remove = self.run_install("--uninstall")
        self.assertEqual(remove.returncode, 0, remove.stderr)
        self.assertTrue(note.is_file())
        self.assertFalse((skill_dir / "SKILL.md").exists())

    def test_existing_foreign_skill_file_is_not_overwritten(self) -> None:
        skill_dir = self.skill_home / "aperio"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("someone else's skill\n", encoding="utf-8")
        result = self.run_install()
        self.assertEqual(result.returncode, 2)
        self.assertIn("refusing to overwrite", result.stderr)
        self.assertEqual((skill_dir / "SKILL.md").read_text(), "someone else's skill\n")

    def test_install_is_idempotent_and_uninstalls(self) -> None:
        command = self.home / ".claude" / "commands" / "aperio.md"
        command.parent.mkdir(parents=True)
        command.write_text("---\ndescription: legacy\n---\n\n# /aperio\n\nAperio v2\n", encoding="utf-8")
        first = self.run_install()
        self.assertEqual(first.returncode, 0, first.stderr)
        binary = self.prefix / "bin" / "aperio"
        skill = self.skill_home / "aperio" / "SKILL.md"
        self.assertTrue(binary.is_file())
        self.assertTrue(skill.is_file())
        self.assertFalse(command.exists())
        self.assertEqual((self.skill_home / "aperio" / "VERSION").read_text().strip(), "2.0.0.dev0")
        package = self.prefix / "share" / "aperio" / "aperio"
        self.assertFalse(any(path.name == "__pycache__" for path in package.rglob("*")))

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

    def test_check_reports_version_without_writing(self) -> None:
        result = subprocess.run(
            ["bash", str(ROOT / "install.sh"), "--prefix", str(self.prefix), "--check"],
            check=False,
            capture_output=True,
            text=True,
            env=self.env,
            cwd=str(ROOT),
            timeout=30,
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("installed: not installed", result.stdout)
        self.assertIn("source:", result.stdout)
        self.assertFalse(self.prefix.exists())

    def test_update_backs_up_and_rolls_back(self) -> None:
        install = self.run_install()
        self.assertEqual(install.returncode, 0, install.stderr)
        probe = self.prefix / "share" / "aperio" / "aperio" / "UPDATE_PROBE"
        probe.write_text("old\n", encoding="utf-8")
        update = self.run_install("--update")
        self.assertEqual(update.returncode, 0, update.stderr)
        self.assertFalse(probe.exists())
        backups = list((self.prefix / "share").glob("aperio.backup.*"))
        self.assertEqual(len(backups), 1)
        self.assertTrue((backups[0] / "aperio" / "UPDATE_PROBE").is_file())
        rollback = self.run_install("--rollback")
        self.assertEqual(rollback.returncode, 0, rollback.stderr)
        self.assertTrue(probe.is_file())
        self.assertFalse(backups[0].exists())

    def test_rollback_without_backup_is_refused(self) -> None:
        result = self.run_install("--rollback")
        self.assertEqual(result.returncode, 2)
        self.assertIn("no update backup", result.stderr)

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
        self.assertFalse(any(path.name == "__pycache__" for path in (prefix / "share" / "aperio" / "aperio").rglob("*")))
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

    def test_prefix_that_resolves_to_root_is_refused(self) -> None:
        result = subprocess.run(
            ["bash", str(ROOT / "install.sh"), "--prefix", "/..", "--dry-run"],
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
