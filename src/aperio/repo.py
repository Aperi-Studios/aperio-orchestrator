"""Read-only Git facts for status and handoff.

This reports the local checkout only. It does not fetch, pull, push, or claim
that a remote branch or CI check is current.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .store import Project


def _git(root: Path, args: list[str]) -> str:
    command = [
        "git",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "core.pager=cat",
        "-C",
        str(root),
        *args,
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _safe_remote(remote: str) -> str:
    if not remote:
        return ""
    try:
        parts = urlsplit(remote)
        if parts.scheme and parts.hostname:
            host = parts.hostname
            if parts.port:
                host += f":{parts.port}"
            return urlunsplit((parts.scheme, host, parts.path, "", ""))
    except ValueError:
        return "<remote>"
    if "@" in remote and "://" not in remote:
        return remote.split("@", 1)[1]
    return remote


def facts(project: Project) -> dict[str, Any] | None:
    if not (project.root / ".git").exists():
        return None
    branch = _git(project.root, ["symbolic-ref", "--short", "HEAD"]) or "detached"
    head = _git(project.root, ["rev-parse", "--short", "HEAD"])
    if not head:
        return None
    status = _git(project.root, ["status", "--porcelain=v1", "--untracked-files=normal"])
    changed = len([line for line in status.splitlines() if line.strip()])
    remote = _safe_remote(_git(project.root, ["remote", "get-url", "origin"]))
    return {
        "branch": branch,
        "head": head,
        "dirty": changed > 0,
        "changed": changed,
        "remote": remote,
    }


def format_facts(data: dict[str, Any] | None) -> str:
    if not data:
        return "not a Git repository"
    state = "dirty" if data.get("dirty") else "clean"
    changed = data.get("changed", 0)
    suffix = f", {changed} changed" if changed else ""
    return f"{data.get('branch')} {data.get('head')} ({state}{suffix})"
