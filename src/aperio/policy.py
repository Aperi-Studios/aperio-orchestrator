"""Write boundaries and approval rules.

These checks are deliberately conservative. They do not claim to be an OS sandbox:
a shell command can still write outside the project before the runner detects it.
The runner records violations and refuses to mark the task verified.
"""

from __future__ import annotations

from fnmatch import fnmatchcase
from pathlib import Path

from .model import Plan, Step
from .paths import PathSafetyError, normalize_rel


class PolicyError(ValueError):
    """A requested write or command violates the approved plan."""


def normalize_allowed(value: str) -> str:
    if value == "*":
        return "*"
    return normalize_rel(value)


def _matches(path: str, allowed: str) -> bool:
    if allowed == "*":
        return True
    if any(char in allowed for char in "*?["):
        if fnmatchcase(path, allowed):
            return True
        # Treat **/ as zero or more directories, matching common glob intent.
        return bool("**/" in allowed and fnmatchcase(path, allowed.replace("**/", "")))
    return path == allowed or path.startswith(allowed.rstrip("/") + "/")


def path_allowed(path: str, allowed_paths: list[str]) -> bool:
    normalized = normalize_rel(path)
    return any(_matches(normalized, normalize_allowed(item)) for item in allowed_paths)


def protected(path: str, protected_paths: list[str]) -> bool:
    normalized = normalize_rel(path)
    for item in protected_paths:
        candidate = normalize_rel(item)
        if normalized == candidate or normalized.startswith(candidate.rstrip("/") + "/"):
            return True
    return False


def validate_plan_paths(plan: Plan, protected_paths: list[str] | None = None) -> None:
    protected_paths = protected_paths or [".git", ".aperio"]
    for allowed in plan.allowed_paths:
        normalized = normalize_allowed(allowed)
        if normalized == "*":
            continue
        if protected(normalized, protected_paths):
            raise PolicyError(f"plan allows a protected path: {allowed}")
    for step in plan.steps:
        if step.kind == "write":
            assert_writable(step.path or "", plan, protected_paths)
        elif step.kind in {"run", "host"}:
            for target in step.writes:
                assert_writable(target, plan, protected_paths)


def assert_writable(path: str, plan: Plan, protected_paths: list[str] | None = None) -> str:
    protected_paths = protected_paths or [".git", ".aperio"]
    try:
        normalized = normalize_rel(path)
    except PathSafetyError as exc:
        raise PolicyError(str(exc)) from exc
    if protected(normalized, protected_paths):
        raise PolicyError(f"protected path: {path}")
    if not path_allowed(normalized, plan.allowed_paths):
        raise PolicyError(f"path is outside the approved plan: {path}")
    return normalized


def assert_command(command: str, step: Step) -> None:
    if not command or not command.strip():
        raise PolicyError(f"step {step.id}: empty command")
    if "\x00" in command:
        raise PolicyError(f"step {step.id}: command contains a NUL byte")
    if len(command) > 8000:
        raise PolicyError(f"step {step.id}: command is too long")
    if step.cwd not in ("", "."):
        try:
            normalize_rel(step.cwd)
        except PathSafetyError as exc:
            raise PolicyError(f"step {step.id}: unsafe cwd: {exc}") from exc


def assert_reviewer(builder: str, reviewer: str) -> None:
    if not reviewer.strip():
        raise PolicyError("reviewer must be named")
    if reviewer.strip().lower() == builder.strip().lower():
        raise PolicyError("the builder cannot be the sole reviewer")


def resolve_command_cwd(root: Path, cwd: str) -> Path:
    from .paths import resolve_inside

    try:
        return resolve_inside(root, cwd or ".", allow_root=True)
    except PathSafetyError as exc:
        raise PolicyError(str(exc)) from exc
