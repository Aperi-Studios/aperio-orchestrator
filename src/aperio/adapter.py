"""Bounded dispatch to an installed coding host.

The host works in a disposable copy of the project. Aperio compares the copy
before and after, rejects changes outside the plan's allowed paths, and only
then applies text changes to the real project through the runner's snapshot and
evidence path. The host is not an OS sandbox; this is a reviewable boundary,
not a claim of isolation.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .model import Plan, Step
from .paths import PathSafetyError
from .policy import PolicyError, assert_writable
from .store import Project


class HostError(RuntimeError):
    """The host could not be resolved or its changes were not acceptable."""


EXCLUDED_DIRS = {
    ".git",
    ".aperio",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
}
MAX_WORKSPACE_FILES = 2_000
MAX_WORKSPACE_BYTES = 50 * 1024 * 1024
MAX_FILE_BYTES = 1_000_000
MAX_CAPTURE = 100_000


@dataclass
class HostChange:
    path: str
    op: str  # create, modify, delete
    content: bytes | None = None
    sha256: str | None = None


@dataclass
class HostResult:
    host: str
    status: str
    command: list[str]
    exit_code: int
    duration_s: float
    stdout: str
    stderr: str
    timed_out: bool
    changes: list[HostChange] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    workspace: str = ""
    prompt_sha256: str = ""
    error: str = ""

    def evidence(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "status": self.status,
            "command": self.command,
            "exit_code": self.exit_code,
            "duration_s": self.duration_s,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timed_out": self.timed_out,
            "changes": [
                {"path": c.path, "op": c.op, "sha256": c.sha256, "bytes": len(c.content or b"")}
                for c in self.changes
            ],
            "violations": self.violations,
            "workspace": self.workspace,
            "prompt_sha256": self.prompt_sha256,
            "error": self.error,
        }


def _binary_for(host: str) -> str:
    override = os.environ.get(f"APERIO_HOST_{host.upper()}")
    if override:
        if not Path(override).is_file():
            raise HostError(f"configured host binary does not exist: {override}")
        return override
    found = shutil.which(host)
    if not found:
        raise HostError(f"host is not installed on PATH: {host}")
    return found


def _command_for(host: str, binary: str, prompt: str, step: Step) -> list[str]:
    if host == "claude":
        return [
            binary,
            "-p",
            prompt,
            "--permission-mode",
            "acceptEdits",
            "--max-budget-usd",
            f"{step.max_budget_usd:.2f}",
            "--output-format",
            "text",
        ]
    if host == "goose":
        return [
            binary,
            "run",
            "--no-session",
            "--max-turns",
            "8",
            "--quiet",
            "--text",
            prompt,
        ]
    raise HostError(f"no adapter for host: {host} (supported: claude, goose)")


def _prompt(project: Project, plan: Plan, step: Step) -> str:
    paths = "\n".join(f"- {p}" for p in step.writes)
    return f"""You are a coding host working inside a disposable copy of a project.

Project: {project.metadata.get('name', project.root.name)}
Task: {plan.title}
Request: {plan.request}

Step: {step.id}
{step.description}

You may create or modify files only under these declared paths:
{paths}

Rules:
- Stay inside the current working directory.
- Do not read or write outside the declared paths.
- Do not use the network.
- Do not run git commands.
- Do not install packages.
- Do not delete files.
- Do not print secrets, tokens, or client data.
- Make the smallest change that satisfies the request.
- When done, reply with a short summary of what you changed.

The orchestrator will reject any change outside the declared paths.
"""


def _iter_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        for name in filenames:
            path = Path(dirpath) / name
            if path.is_symlink():
                continue
            files.append(path)
    return files


def _copy_workspace(project: Project, workspace: Path) -> None:
    total = 0
    copied = 0
    for path in _iter_files(project.root):
        rel = path.relative_to(project.root)
        if path.is_symlink():
            continue
        size = path.stat().st_size
        total += size
        copied += 1
        if copied > MAX_WORKSPACE_FILES or total > MAX_WORKSPACE_BYTES:
            raise HostError("workspace copy limit exceeded")
        destination = workspace / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)


def _scan(root: Path) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for path in _iter_files(root):
        rel = path.relative_to(root).as_posix()
        try:
            result[rel] = ("file", hashlib.sha256(path.read_bytes()).hexdigest())
        except OSError:
            continue
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        for name in list(dirnames) + list(filenames):
            path = Path(dirpath) / name
            if path.is_symlink():
                result[path.relative_to(root).as_posix()] = ("symlink", os.readlink(path))
    return result


def _diff(before: dict[str, tuple[str, str]], after: dict[str, tuple[str, str]]) -> list[tuple[str, str]]:
    changes: list[tuple[str, str]] = []
    for rel, record in after.items():
        if rel not in before:
            changes.append((rel, "create"))
        elif before[rel] != record:
            changes.append((rel, "modify"))
    for rel in before:
        if rel not in after:
            changes.append((rel, "delete"))
    return sorted(changes)


def run_host_step(project: Project, plan: Plan, step: Step, run_id: str) -> HostResult:
    if not step.host or not step.prompt:
        raise HostError(f"step {step.id}: missing host or prompt")
    binary = _binary_for(step.host)
    prompt = _prompt(project, plan, step)
    command = _command_for(step.host, binary, prompt, step)
    workspace = project.state / "dispatch" / run_id / "workspace"
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)
    _copy_workspace(project, workspace)
    before = _scan(workspace)
    env = os.environ.copy()
    env.update(
        {
            "APERIO_TASK_ID": plan.task_id,
            "APERIO_PLAN_ID": plan.id,
            "APERIO_RUN_ID": run_id,
            "APERIO_WORKSPACE": str(workspace),
            "APERIO_ALLOWED_PATHS": os.pathsep.join(step.writes),
        }
    )
    started = time.monotonic()
    stdout = ""
    stderr = ""
    timed_out = False
    try:
        completed = subprocess.run(
            command,
            check=False,
            cwd=str(workspace),
            env=env,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=step.timeout_s,
        )
        exit_code = completed.returncode
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
    except subprocess.TimeoutExpired as exc:
        exit_code = 124
        timed_out = True
        stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", errors="replace")
        stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", errors="replace")
    except OSError as exc:
        exit_code = 127
        stderr = str(exc)
    duration = round(time.monotonic() - started, 3)
    after = _scan(workspace)
    diff = _diff(before, after)
    result = HostResult(
        host=step.host,
        status="running",
        command=command,
        exit_code=exit_code,
        duration_s=duration,
        stdout=stdout[-MAX_CAPTURE:],
        stderr=stderr[-MAX_CAPTURE:],
        timed_out=timed_out,
        workspace=str(workspace),
        prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
    )
    if exit_code != 0:
        result.status = "failed"
        result.error = f"host exited {exit_code}" + (" (timeout)" if timed_out else "")
        return result
    if not diff:
        result.status = "failed"
        result.error = "host made no changes"
        return result
    changes: list[HostChange] = []
    for rel, op in diff:
        try:
            normalized = assert_writable(rel, plan)
        except (PolicyError, PathSafetyError) as exc:
            result.violations.append(f"{rel}: {exc}")
            continue
        if op == "delete":
            changes.append(HostChange(path=normalized, op="delete"))
            continue
        path = workspace / rel
        data = path.read_bytes()
        if len(data) > MAX_FILE_BYTES:
            result.violations.append(f"{rel}: file exceeds {MAX_FILE_BYTES} bytes")
            continue
        if b"\x00" in data:
            result.violations.append(f"{rel}: binary file is not accepted by the text adapter")
            continue
        changes.append(
            HostChange(
                path=normalized,
                op=op,
                content=data,
                sha256=hashlib.sha256(data).hexdigest(),
            )
        )
    result.changes = changes
    if result.violations:
        result.status = "failed"
        result.error = "host changed paths outside the approved plan or wrote unacceptable files"
    elif not changes:
        result.status = "failed"
        result.error = "host produced no applicable text changes"
    else:
        result.status = "ok"
    return result
