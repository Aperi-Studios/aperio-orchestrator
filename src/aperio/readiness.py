"""Pre-flight, deployment, after-sales, design, and security readiness records.

This is the structured project-readiness counterpart to the learning dossier.
It records the facts a task needs before work starts and before a production
handoff. It does not deploy anything and it does not replace a threat model
review.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .model import ModelError, utc_now
from .paths import replace_text_atomic
from .store import Project

SCHEMA_VERSION = 1
READINESS_NAME = "readiness.json"
SURFACES = {"marketing", "web_app", "cms", "crm", "erp", "mobile", "desktop"}
SEVERITIES = {"none", "low", "medium", "high", "critical"}


class ReadinessError(ModelError):
    """The readiness record is missing, malformed, or not ready."""


def _path(project: Project) -> Path:
    return project.state / READINESS_NAME


def _read(project: Project) -> dict[str, Any]:
    path = _path(project)
    if not path.is_file():
        raise ReadinessError("readiness record is missing; run aperio readiness import")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReadinessError(f"readiness record is unreadable: {exc}") from exc
    if not isinstance(data, dict):
        raise ReadinessError("readiness record must be a JSON object")
    if data.get("schema") != SCHEMA_VERSION:
        raise ReadinessError(f"readiness schema must be {SCHEMA_VERSION}")
    return data


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _texts(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(item, str) and item.strip() for item in value)


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    section = data.get(name)
    if not isinstance(section, dict):
        raise ReadinessError(f"readiness.{name} must be an object")
    return section


def _check_preflight(section: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for key in ("audience", "success_measure", "review_owner", "approval_path"):
        if not _text(section.get(key)):
            issues.append(f"preflight.{key} is required")
    for key in ("features", "out_of_scope", "integrations", "constraints"):
        if not _texts(section.get(key)):
            issues.append(f"preflight.{key} must be a non-empty list of strings")
    return issues


def _check_deploy(section: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for key in ("hosting", "domain", "tls", "build", "migrate", "backup", "restore", "ci_cd", "rollback", "monitoring", "smoke"):
        if not _text(section.get(key)):
            issues.append(f"deploy.{key} is required")
    env_names = section.get("env_names")
    if not isinstance(env_names, list) or not all(isinstance(item, str) and item.strip() for item in env_names):
        issues.append("deploy.env_names must be a list of names, not values")
    return issues


def _check_aftersales(section: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for key in (
        "support_window",
        "escalation_owner",
        "logs",
        "metrics",
        "alerts",
        "backup_schedule",
        "restore_drill",
        "update_policy",
        "admin_recovery",
        "docs",
    ):
        if not _text(section.get(key)):
            issues.append(f"aftersales.{key} is required")
    return issues


def _check_design(section: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if section.get("surface_class") not in SURFACES:
        issues.append(f"design.surface_class must be one of {sorted(SURFACES)}")
    for key in ("contract", "accessibility", "responsive", "originality", "review_owner"):
        if not _text(section.get(key)):
            issues.append(f"design.{key} is required")
    if not _texts(section.get("references")):
        issues.append("design.references must be a non-empty list")
    return issues


def _check_security(section: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for key in ("threat_model", "assets", "trust_boundaries", "controls", "dependency_scan", "secret_scan", "headers", "incident"):
        value = section.get(key)
        if key in {"assets", "trust_boundaries", "controls"}:
            if not _texts(value):
                issues.append(f"security.{key} must be a non-empty list")
        elif not _text(value):
            issues.append(f"security.{key} is required")
    severity = section.get("unresolved_severity")
    if severity not in SEVERITIES:
        issues.append(f"security.unresolved_severity must be one of {sorted(SEVERITIES)}")
    elif severity in {"high", "critical"}:
        issues.append("security.unresolved_severity is high or critical; resolve it or record owner risk acceptance before handoff")
    return issues


def validate(project: Project) -> list[str]:
    try:
        data = _read(project)
    except ReadinessError as exc:
        return [str(exc)]
    issues: list[str] = []
    try:
        issues.extend(_check_preflight(_section(data, "preflight")))
    except ReadinessError as exc:
        issues.append(str(exc))
    try:
        issues.extend(_check_deploy(_section(data, "deploy")))
    except ReadinessError as exc:
        issues.append(str(exc))
    try:
        issues.extend(_check_aftersales(_section(data, "aftersales")))
    except ReadinessError as exc:
        issues.append(str(exc))
    try:
        issues.extend(_check_design(_section(data, "design")))
    except ReadinessError as exc:
        issues.append(str(exc))
    try:
        issues.extend(_check_security(_section(data, "security")))
    except ReadinessError as exc:
        issues.append(str(exc))
    return issues


def validate_preflight(project: Project) -> list[str]:
    """Validate only the pre-flight section used at plan time."""
    try:
        data = _read(project)
    except ReadinessError as exc:
        return [str(exc)]
    try:
        return _check_preflight(_section(data, "preflight"))
    except ReadinessError as exc:
        return [str(exc)]


def status(project: Project) -> dict[str, Any]:
    try:
        data = _read(project)
        issues = validate(project)
    except ReadinessError as exc:
        data = {}
        issues = [str(exc)]
    return {
        "schema": SCHEMA_VERSION,
        "ready": not issues,
        "issues": issues,
        "updated_at": data.get("updated_at"),
        "sections": {name: isinstance(data.get(name), dict) for name in ("preflight", "deploy", "aftersales", "design", "security")},
    }


def format_status(data: dict[str, Any]) -> str:
    lines = [f"Project readiness: {'READY' if data['ready'] else 'NOT READY'}"]
    for name, present in data["sections"].items():
        lines.append(f"- {name}: {'recorded' if present else 'missing'}")
    if data["issues"]:
        lines.append("Issues:")
        lines.extend(f"- {issue}" for issue in data["issues"])
    return "\n".join(lines)


def import_readiness(project: Project, path: str, *, replace: bool = False) -> dict[str, Any]:
    raw = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReadinessError(f"readiness record is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ReadinessError("readiness record must be a JSON object")
    if _path(project).exists() and not replace:
        raise ReadinessError("readiness record already exists; pass --replace to overwrite it")
    data.pop("digest", None)
    data["schema"] = SCHEMA_VERSION
    data["updated_at"] = utc_now()
    with project.lock():
        _path(project).parent.mkdir(parents=True, exist_ok=True)
        replace_text_atomic(_path(project), json.dumps(data, indent=2, sort_keys=True) + "\n")
        project.append_event("readiness.imported", {"digest": None})
    return status(project)
