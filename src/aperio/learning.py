"""Stack-mastery dossier, local proof, and competency gate.

The dossier is project state, not documentation. It records what the agent
actually learned, which official sources it used, which tools it intends to
install, and what it proved locally. A dossier is ready only when the required
facts are present and internally consistent.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

from .model import ModelError, utc_now
from .paths import replace_text_atomic
from .store import Project

SCHEMA_VERSION = 1
DOSSIER_NAME = "learning.json"
MAX_COMMAND = 8000
MAX_OUTPUT = 20_000
PROOF_TIMEOUT = 120
PROOF_MARKER = "aperio learn proof"
HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")
SOURCE_KINDS = {"official_docs", "release_notes", "migration", "security_advisory", "fallback"}
MCP_STATUSES = {"available", "installed", "not-needed"}
COMPETENCY_VERDICTS = {"demonstrated", "not_demonstrated"}


class LearningError(ModelError):
    """The learning dossier is missing, malformed, or not ready."""


def _path(project: Project) -> Path:
    return project.state / DOSSIER_NAME


def _canonical(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(data: dict[str, Any]) -> str:
    payload = {key: value for key, value in data.items() if key != "digest"}
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _read(project: Project) -> dict[str, Any]:
    path = _path(project)
    if not path.is_file():
        raise LearningError("learning dossier is missing; run aperio learn import")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LearningError(f"learning dossier is unreadable: {exc}") from exc
    if not isinstance(data, dict):
        raise LearningError("learning dossier must be a JSON object")
    stored = data.get("digest")
    if stored is not None and (not isinstance(stored, str) or stored != digest(data)):
        raise LearningError("learning dossier digest mismatch; re-import the dossier")
    return data


def _write(project: Project, data: dict[str, Any]) -> None:
    data["updated_at"] = utc_now()
    data["digest"] = digest(data)
    path = _path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    replace_text_atomic(path, json.dumps(data, indent=2, sort_keys=True) + "\n")


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _http_url(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(("https://", "http://"))


def _iso_date(value: Any) -> bool:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _check_stack(stack: Any) -> list[str]:
    issues: list[str] = []
    if not isinstance(stack, dict):
        return ["stack must be an object"]
    for key in ("surface", "runtime", "framework", "package_manager", "database", "hosting"):
        if not _is_text(stack.get(key)):
            issues.append(f"stack.{key} is required")
    versions = stack.get("versions")
    if not isinstance(versions, dict) or not versions:
        issues.append("stack.versions must record at least one version")
    else:
        for name, version in versions.items():
            if not isinstance(name, str) or not name.strip() or not _is_text(version):
                issues.append("stack.versions entries must be name: version strings")
                break
    constraints = stack.get("constraints")
    if constraints is not None and (
        not isinstance(constraints, list) or not all(isinstance(item, str) for item in constraints)
    ):
        issues.append("stack.constraints must be a list of strings")
    return issues


def _check_sources(sources: Any, stack: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not isinstance(sources, list) or not sources:
        return ["sources must include at least one source"]
    official = False
    for index, source in enumerate(sources):
        prefix = f"sources[{index}]"
        if not isinstance(source, dict):
            issues.append(f"{prefix} must be an object")
            continue
        for key in ("title", "kind", "version"):
            if not _is_text(source.get(key)):
                issues.append(f"{prefix}.{key} is required")
        if not _http_url(source.get("url")):
            issues.append(f"{prefix}.url must be an http(s) URL")
        if source.get("kind") not in SOURCE_KINDS:
            issues.append(f"{prefix}.kind must be one of {sorted(SOURCE_KINDS)}")
        if not _iso_date(source.get("accessed")):
            issues.append(f"{prefix}.accessed must be YYYY-MM-DD")
        if source.get("official") is True:
            official = True
    if not official and not _is_text(stack.get("fallback_reason")):
        issues.append("at least one official source is required unless stack.fallback_reason explains the fallback")
    return issues


def _check_skills(skills: Any, skill_gap: Any, project: Project) -> list[str]:
    issues: list[str] = []
    if not isinstance(skills, list):
        return ["skills must be a list"]
    for index, skill in enumerate(skills):
        prefix = f"skills[{index}]"
        if not isinstance(skill, dict):
            issues.append(f"{prefix} must be an object")
            continue
        for key in ("name", "source", "version", "license", "scope"):
            if not _is_text(skill.get(key)):
                issues.append(f"{prefix}.{key} is required")
        if skill.get("verified") is not True:
            issues.append(f"{prefix}.verified must be true")
    if not isinstance(skill_gap, dict):
        return issues + ["skill_gap must be an object"]
    if not isinstance(skill_gap.get("needed"), bool):
        issues.append("skill_gap.needed must be true or false")
    if not _is_text(skill_gap.get("reason")):
        issues.append("skill_gap.reason is required")
    if skill_gap.get("needed") is True:
        if skill_gap.get("created") is not True:
            issues.append("skill_gap.created must be true when a skill is needed")
        raw_path = skill_gap.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            issues.append("skill_gap.path is required when a skill is created")
        else:
            candidate = (project.root / raw_path).resolve()
            try:
                candidate.relative_to(project.root)
            except ValueError:
                issues.append("skill_gap.path must stay inside the project")
            else:
                if not (candidate / "SKILL.md").is_file():
                    issues.append("skill_gap.path must contain a SKILL.md")
    return issues


def _check_mcps(mcps: Any) -> list[str]:
    issues: list[str] = []
    if not isinstance(mcps, list):
        return ["mcps must be a list"]
    for index, mcp in enumerate(mcps):
        prefix = f"mcps[{index}]"
        if not isinstance(mcp, dict):
            issues.append(f"{prefix} must be an object")
            continue
        for key in ("name", "source", "version", "license", "scope"):
            if not _is_text(mcp.get(key)):
                issues.append(f"{prefix}.{key} is required")
        if mcp.get("scope") not in {"project", "global"}:
            issues.append(f"{prefix}.scope must be project or global")
        if mcp.get("status") not in MCP_STATUSES:
            issues.append(f"{prefix}.status must be one of {sorted(MCP_STATUSES)}")
        permissions = mcp.get("permissions", [])
        if not isinstance(permissions, list) or not all(isinstance(item, str) for item in permissions):
            issues.append(f"{prefix}.permissions must be a list of strings")
        for flag in ("credentials", "paid", "network", "elevated"):
            if not isinstance(mcp.get(flag, False), bool):
                issues.append(f"{prefix}.{flag} must be true or false")
        risky = (
            mcp.get("scope") == "global"
            or mcp.get("credentials") is True
            or mcp.get("paid") is True
            or mcp.get("network") is True
            or mcp.get("elevated") is True
        )
        if risky and mcp.get("approved") is not True:
            issues.append(f"{prefix} requires explicit owner approval for global/paid/credentialed/network/elevated use")
    return issues


def _check_proof(proof: Any) -> list[str]:
    if not isinstance(proof, dict):
        return ["proof must be an object"]
    issues: list[str] = []
    if not _is_text(proof.get("command")):
        issues.append("proof.command is required")
    if proof.get("exit_code") != 0:
        issues.append("proof.exit_code must be 0")
    if proof.get("recorded_by") != PROOF_MARKER:
        issues.append("proof.recorded_by must be aperio learn proof; imported proof text is not accepted")
    if not _is_text(proof.get("output_sha256")):
        issues.append("proof.output_sha256 is required")
    elif not HEX_DIGEST.fullmatch(str(proof["output_sha256"])):
        issues.append("proof.output_sha256 must be a SHA-256 hex digest")
    if not _is_text(proof.get("recorded_at")):
        issues.append("proof.recorded_at is required")
    return issues


def _check_teaching(teachback: Any, competency: Any) -> list[str]:
    issues: list[str] = []
    if not isinstance(teachback, dict):
        return ["teachback must be an object", "competency must be an object"]
    for key in ("agent", "summary"):
        if not _is_text(teachback.get(key)):
            issues.append(f"teachback.{key} is required")
    if isinstance(teachback.get("summary"), str) and len(teachback["summary"].strip()) < 40:
        issues.append("teachback.summary must demonstrate understanding in at least 40 characters")
    uncertainties = teachback.get("uncertainties")
    if not isinstance(uncertainties, list) or not all(isinstance(item, str) for item in uncertainties):
        issues.append("teachback.uncertainties must be a list of strings")
    if not isinstance(competency, dict):
        return issues + ["competency must be an object"]
    for key in ("agent", "evidence"):
        if not _is_text(competency.get(key)):
            issues.append(f"competency.{key} is required")
    if competency.get("verdict") not in COMPETENCY_VERDICTS:
        issues.append(f"competency.verdict must be one of {sorted(COMPETENCY_VERDICTS)}")
    if competency.get("verdict") != "demonstrated":
        issues.append("competency.verdict must be demonstrated")
    if teachback.get("agent") and competency.get("agent") and teachback["agent"] != competency["agent"]:
        issues.append("teachback.agent and competency.agent must match")
    return issues


def validate(project: Project) -> list[str]:
    """Return every reason the dossier is not ready. Never raises for content."""
    try:
        data = _read(project)
    except LearningError as exc:
        return [str(exc)]
    issues: list[str] = []
    if data.get("schema") != SCHEMA_VERSION:
        issues.append(f"schema must be {SCHEMA_VERSION}")
    stack = data.get("stack")
    issues.extend(_check_stack(stack))
    issues.extend(_check_sources(data.get("sources"), stack if isinstance(stack, dict) else {}))
    issues.extend(_check_skills(data.get("skills"), data.get("skill_gap"), project))
    issues.extend(_check_mcps(data.get("mcps")))
    issues.extend(_check_proof(data.get("proof")))
    issues.extend(_check_teaching(data.get("teachback"), data.get("competency")))
    return issues


def status(project: Project) -> dict[str, Any]:
    issues: list[str] = []
    data: dict[str, Any] | None
    try:
        data = _read(project)
    except LearningError as exc:
        data = None
        issues = [str(exc)]
    if data is not None:
        issues = validate(project)
    stack = data.get("stack", {}) if isinstance(data, dict) else {}
    return {
        "schema": SCHEMA_VERSION,
        "ready": not issues,
        "issues": issues,
        "digest": data.get("digest") if isinstance(data, dict) else None,
        "updated_at": data.get("updated_at") if isinstance(data, dict) else None,
        "stack": stack,
        "sources": len(data.get("sources", [])) if isinstance(data, dict) else 0,
        "skills": len(data.get("skills", [])) if isinstance(data, dict) else 0,
        "mcps": len(data.get("mcps", [])) if isinstance(data, dict) else 0,
    }


def format_status(data: dict[str, Any]) -> str:
    stack = data.get("stack") or {}
    lines = [
        f"Learning dossier: {'READY' if data['ready'] else 'NOT READY'}",
        f"Stack: {stack.get('surface', '?')} / {stack.get('framework', '?')} / {stack.get('runtime', '?')}",
        f"Sources: {data.get('sources', 0)} · Skills: {data.get('skills', 0)} · MCPs: {data.get('mcps', 0)}",
    ]
    if data.get("digest"):
        lines.append(f"Digest: {data['digest']}")
    if data["issues"]:
        lines.append("Issues:")
        lines.extend(f"- {issue}" for issue in data["issues"])
    return "\n".join(lines)


def import_dossier(project: Project, path: str, *, replace: bool = False) -> dict[str, Any]:
    raw = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LearningError(f"dossier is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise LearningError("dossier must be a JSON object")
    if _path(project).exists() and not replace:
        raise LearningError("learning dossier already exists; pass --replace to overwrite it")
    data.pop("digest", None)
    data.pop("proof", None)
    data["schema"] = SCHEMA_VERSION
    data["updated_at"] = utc_now()
    with project.lock():
        _write(project, data)
        project.append_event("learning.imported", {"digest": data["digest"]})
    return status(project)


def record_proof(project: Project, command: str, *, timeout: int = PROOF_TIMEOUT) -> dict[str, Any]:
    if not command.strip():
        raise LearningError("proof command must not be empty")
    if "\x00" in command:
        raise LearningError("proof command contains a NUL byte")
    if len(command) > MAX_COMMAND:
        raise LearningError(f"proof command is longer than {MAX_COMMAND} characters")
    data = _read(project)
    try:
        completed = subprocess.run(
            command,
            shell=True,
            check=False,
            cwd=str(project.root),
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
        )
        exit_code = completed.returncode
        stdout = completed.stdout[:MAX_OUTPUT]
        stderr = completed.stderr[:MAX_OUTPUT]
    except subprocess.TimeoutExpired as exc:
        exit_code = 124
        raw_stdout = exc.stdout
        raw_stderr = exc.stderr
        stdout = raw_stdout.decode("utf-8", errors="replace") if isinstance(raw_stdout, bytes) else (raw_stdout or "")
        stderr = raw_stderr.decode("utf-8", errors="replace") if isinstance(raw_stderr, bytes) else (raw_stderr or "")
        stdout = stdout[:MAX_OUTPUT]
        stderr = (stderr[:MAX_OUTPUT] + f"\nproof timed out after {timeout}s").strip()
    payload = (stdout + "\x00" + stderr).encode("utf-8", errors="replace")
    data["proof"] = {
        "command": command,
        "exit_code": exit_code,
        "duration_ms": 0,
        "stdout_tail": stdout[-2000:],
        "stderr_tail": stderr[-2000:],
        "output_sha256": hashlib.sha256(payload).hexdigest(),
        "recorded_at": utc_now(),
        "recorded_by": PROOF_MARKER,
    }
    with project.lock():
        _write(project, data)
        project.append_event(
            "learning.proof",
            {"exit_code": exit_code, "digest": data["digest"]},
        )
    return status(project)
