"""Optional OS-level isolation for shell steps.

Aperio's path policy detects writes after a command. This module adds an
opt-in boundary where the operating system supports one. It is deliberately
strict: when `plan.sandbox` is true and no supported sandbox exists, the run is
refused rather than silently downgraded.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


class SandboxError(RuntimeError):
    """The requested OS sandbox is unavailable or cannot be constructed."""


def kind() -> str | None:
    if sys.platform == "darwin" and shutil.which("sandbox-exec"):
        return "sandbox-exec"
    if sys.platform.startswith("linux") and shutil.which("bwrap"):
        return "bwrap"
    return None


def _profile(root: Path) -> str:
    # Read-only access to the host is intentional: compilers and interpreters
    # need system libraries. Writes are limited to the project and temporary
    # directories. Network access is denied.
    escaped = str(root.resolve()).replace("\\", "\\\\").replace('"', '\\"')
    return (
        "(version 1)\n"
        "(deny default)\n"
        "(allow process*)\n"
        "(allow sysctl-read)\n"
        "(allow mach-lookup)\n"
        "(allow file-read*)\n"
        "(allow file-write* "
        f'(subpath "{escaped}") '
        '(subpath "/private/tmp") '
        '(subpath "/tmp"))\n'
    )


def wrap(command: str, root: Path, cwd: Path) -> tuple[list[str], dict[str, object]]:
    """Return an argv wrapper and an evidence record for an isolated command."""
    backend = kind()
    if backend is None:
        raise SandboxError("no supported OS sandbox (sandbox-exec or bwrap) is available")
    if backend == "sandbox-exec":
        if not Path("/usr/bin/sandbox-exec").is_file():
            raise SandboxError("sandbox-exec is not installed at /usr/bin/sandbox-exec")
        argv = ["/usr/bin/sandbox-exec", "-p", _profile(root), "/bin/sh", "-c", command]
        return argv, {"requested": True, "active": True, "kind": backend}
    argv = [
        "bwrap",
        "--ro-bind",
        "/",
        "/",
        "--bind",
        str(root),
        str(root),
        "--chdir",
        str(cwd),
        "--unshare-net",
        "/bin/sh",
        "-c",
        command,
    ]
    return argv, {"requested": True, "active": True, "kind": backend}


def wrap_argv(command: list[str], root: Path, cwd: Path) -> tuple[list[str], dict[str, object]]:
    """Wrap an argv-list command (host dispatch) in the OS sandbox.

    Same profile and fail-closed rules as wrap(); the command is exec'd
    directly instead of through /bin/sh -c because the host adapter already
    builds an argv.
    """
    backend = kind()
    if backend is None:
        raise SandboxError("no supported OS sandbox (sandbox-exec or bwrap) is available")
    if backend == "sandbox-exec":
        if not Path("/usr/bin/sandbox-exec").is_file():
            raise SandboxError("sandbox-exec is not installed at /usr/bin/sandbox-exec")
        argv = ["/usr/bin/sandbox-exec", "-p", _profile(root), *command]
        return argv, {"requested": True, "active": True, "kind": backend}
    argv = [
        "bwrap",
        "--ro-bind",
        "/",
        "/",
        "--bind",
        str(root),
        str(root),
        "--chdir",
        str(cwd),
        "--unshare-net",
        *command,
    ]
    return argv, {"requested": True, "active": True, "kind": backend}


def unavailable_record() -> dict[str, object]:
    return {"requested": True, "active": False, "kind": None, "reason": "no supported sandbox"}
