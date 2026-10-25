"""Read-only host detection.

A found executable is not proof that a host is authenticated, permitted, or able
to run a task. This module reports presence and version only.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Host:
    name: str
    binary: str
    path: str | None
    version: str
    status: str


CANDIDATES: list[tuple[str, str]] = [
    ("claude", "claude"),
    ("codex", "codex"),
    ("codexx", "codexx"),
    ("goose", "goose"),
    ("opencode", "opencode"),
    ("agy", "agy"),
    ("dsh", "dsh"),
    ("kilocode", "kilocode"),
    ("cline", "cline"),
    ("gemini", "gemini"),
    ("cursor", "cursor-agent"),
]


def _version(binary: str, timeout: int = 5) -> str:
    try:
        result = subprocess.run(
            [binary, "--version"],
            check=False,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
        )
        text = (result.stdout or result.stderr or "").strip().splitlines()
        return text[0][:120] if text else "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


def detect_hosts() -> list[Host]:
    hosts: list[Host] = []
    for name, binary in CANDIDATES:
        path = shutil.which(binary)
        if not path:
            hosts.append(Host(name=name, binary=binary, path=None, version="", status="not found"))
            continue
        hosts.append(
            Host(
                name=name,
                binary=binary,
                path=str(Path(path)),
                version=_version(path),
                status="found",
            )
        )
    return hosts


def hosts_as_dicts() -> list[dict[str, str | None]]:
    return [asdict(host) for host in detect_hosts()]
