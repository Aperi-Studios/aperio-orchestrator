"""Manifest-driven toolchain and MCP acquisition.

A project declares tools as argv arrays. Aperio executes only the declared
commands, records exit codes and short output, and requires explicit owner
approval for global, networked, credentialed, paid, or elevated tools.
This is orchestration, not a package-registry endorsement or an OS sandbox.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from .model import ModelError, utc_now
from .paths import replace_text_atomic
from .store import Project, StoreError

SCHEMA_VERSION = 1
TOOLCHAIN_NAME = "toolchain.json"
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
KINDS = {"package", "mcp", "binary"}
SCOPES = {"project", "global"}
APPROVAL = "I approve this tool install"
MAX_OUTPUT = 20_000


class ToolError(ModelError):
    """A tool declaration or installation step is unsafe or invalid."""


def _path(project: Project) -> Path:
    return project.state / TOOLCHAIN_NAME


def _new() -> dict[str, Any]:
    return {"schema": SCHEMA_VERSION, "tools": [], "updated_at": utc_now()}


def _read(project: Project) -> dict[str, Any]:
    path = _path(project)
    if not path.is_file():
        return _new()
    try:
        data = project._read_state_json(path)  # same package; schema is enforced
    except StoreError as exc:
        raise ToolError(f"toolchain state is unreadable: {exc}") from exc
    if not isinstance(data.get("tools"), list):
        raise ToolError("toolchain state is malformed")
    return data


def _write(project: Project, data: dict[str, Any]) -> None:
    data["schema"] = SCHEMA_VERSION
    data["updated_at"] = utc_now()
    _path(project).parent.mkdir(parents=True, exist_ok=True)
    replace_text_atomic(_path(project), json.dumps(data, indent=2, sort_keys=True) + "\n")


def _argv(value: Any, field: str, tool: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise ToolError(f"tool {tool}: {field} must be a non-empty array of strings")
    return list(value)


def validate_manifest(data: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not isinstance(data, dict):
        return ["toolchain must be a JSON object"]
    if data.get("schema") != SCHEMA_VERSION:
        issues.append(f"toolchain schema must be {SCHEMA_VERSION}")
    tools = data.get("tools")
    if not isinstance(tools, list) or not tools:
        return issues + ["toolchain needs a non-empty tools array"]
    seen: set[str] = set()
    for index, tool in enumerate(tools, 1):
        label = f"tool {index}"
        if not isinstance(tool, dict):
            issues.append(f"{label}: must be an object")
            continue
        name = str(tool.get("name", ""))
        label = name or label
        if not NAME_RE.fullmatch(name):
            issues.append(f"{label}: name must match {NAME_RE.pattern}")
        if name in seen:
            issues.append(f"{label}: duplicate tool name")
        seen.add(name)
        if tool.get("kind") not in KINDS:
            issues.append(f"{label}: kind must be one of {sorted(KINDS)}")
        if tool.get("scope") not in SCOPES:
            issues.append(f"{label}: scope must be one of {sorted(SCOPES)}")
        for field in ("source", "version", "license"):
            if not isinstance(tool.get(field), str) or not str(tool.get(field, "")).strip():
                issues.append(f"{label}: {field} must be a non-empty string")
        permissions = tool.get("permissions")
        if not isinstance(permissions, list) or not all(isinstance(item, str) and item for item in permissions):
            issues.append(f"{label}: permissions must be an array of strings")
        for flag in ("network", "credentials", "elevated"):
            if not isinstance(tool.get(flag, False), bool):
                issues.append(f"{label}: {flag} must be true or false")
        cost = tool.get("cost_usd", 0)
        if not isinstance(cost, (int, float)) or cost < 0:
            issues.append(f"{label}: cost_usd must be a non-negative number")
        try:
            _argv(tool.get("install"), "install", label)
            _argv(tool.get("verify"), "verify", label)
        except ToolError as exc:
            issues.append(str(exc))
    return issues


def import_manifest(project: Project, path: str, *, replace: bool = False) -> dict[str, Any]:
    raw = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ToolError(f"toolchain is not valid JSON: {exc}") from exc
    issues = validate_manifest(data)
    if issues:
        raise ToolError("; ".join(issues[:8]))
    if _path(project).exists() and not replace:
        raise ToolError("toolchain already exists; pass --replace to overwrite it")
    clean = {"schema": SCHEMA_VERSION, "tools": data["tools"]}
    with project.lock():
        _write(project, clean)
        project.append_event("toolchain.imported", {"tools": len(clean["tools"])})
    return status(project)


def status(project: Project) -> dict[str, Any]:
    data = _read(project)
    rows = []
    for tool in data["tools"]:
        rows.append(
            {
                "name": tool.get("name"),
                "kind": tool.get("kind"),
                "scope": tool.get("scope"),
                "version": tool.get("version"),
                "installed_at": tool.get("installed_at"),
                "verified_at": tool.get("verified_at"),
                "network": bool(tool.get("network", False)),
                "credentials": bool(tool.get("credentials", False)),
                "elevated": bool(tool.get("elevated", False)),
                "cost_usd": tool.get("cost_usd", 0),
            }
        )
    return {"schema": SCHEMA_VERSION, "tools": rows, "count": len(rows)}


def format_status(data: dict[str, Any]) -> str:
    lines = [f"Toolchain: {data['count']} declared"]
    for tool in data["tools"]:
        marks = []
        if tool["network"]:
            marks.append("network")
        if tool["credentials"]:
            marks.append("credentials")
        if tool["elevated"]:
            marks.append("elevated")
        state = "installed" if tool["installed_at"] else "not installed"
        suffix = f" [{', '.join(marks)}]" if marks else ""
        lines.append(f"- {tool['name']} ({tool['kind']}, {tool['scope']}, {state}){suffix}")
    return "\n".join(lines)


def _run(argv: list[str], cwd: Path, timeout: int) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            argv,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout}s"
    return int(result.returncode), (result.stdout or "")[-MAX_OUTPUT:], (result.stderr or "")[-MAX_OUTPUT:]


def install(
    project: Project,
    name: str,
    *,
    approved_by: str = "",
    confirm: str = "",
    timeout: int = 300,
) -> dict[str, Any]:
    data = _read(project)
    tool = next((item for item in data["tools"] if item.get("name") == name), None)
    if tool is None:
        raise ToolError(f"unknown tool: {name}")
    if timeout < 1 or timeout > 3600:
        raise ToolError("timeout must be 1..3600")
    risky = (
        tool.get("scope") == "global"
        or bool(tool.get("network"))
        or bool(tool.get("credentials"))
        or bool(tool.get("elevated"))
        or float(tool.get("cost_usd", 0)) > 0
    )
    if risky and (not approved_by.strip() or confirm != APPROVAL):
        raise ToolError(
            "global, networked, credentialed, elevated, or paid tools require "
            f"--by <owner> --confirm \"{APPROVAL}\""
        )
    with project.lock():
        if risky:
            data = _read(project)
            tool = next(item for item in data["tools"] if item.get("name") == name)
        install_argv = _argv(tool.get("install"), "install", name)
        verify_argv = _argv(tool.get("verify"), "verify", name)
        code, stdout, stderr = _run(install_argv, project.root, timeout)
        if code != 0:
            raise ToolError(f"tool {name} install exited {code}: {stderr.strip()[:400]}")
        verify_code, verify_out, verify_err = _run(verify_argv, project.root, timeout)
        if verify_code != 0:
            raise ToolError(f"tool {name} verification exited {verify_code}: {verify_err.strip()[:400]}")
        tool["installed_at"] = utc_now()
        tool["installed_by"] = approved_by.strip() or "project-policy"
        tool["install_exit"] = code
        tool["install_output"] = stdout[-2000:]
        tool["verified_at"] = utc_now()
        tool["verify_exit"] = verify_code
        tool["verify_output"] = verify_out[-2000:]
        _write(project, data)
        project.append_event("tool.installed", {"name": name, "verified": True})
    return {key: tool.get(key) for key in ("name", "kind", "scope", "version", "installed_at", "verified_at")}
