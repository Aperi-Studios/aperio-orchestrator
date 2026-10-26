"""Source-anchored security audit ledger.

This module records what was reviewed and what was found. It does not execute
target code, and a finding is only as strong as the evidence attached to it.
"""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any

from .model import ModelError, utc_now
from .paths import PathSafetyError, normalize_rel, replace_text_atomic
from .store import Project

SCHEMA_VERSION = 1
MAX_UNITS = 500
AUDIT_ID = "audit-"
SKIP_DIRS = {
    ".git",
    ".aperio",
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".venv",
    "venv",
    "__pycache__",
    ".next",
    ".nuxt",
    ".svelte-kit",
    ".idea",
    ".vscode",
}
PROFILES = {"quick", "standard", "deep"}
UNIT_STATUSES = {"planned", "checked", "candidate", "deferred", "out_of_scope"}
FINDING_STATUSES = {"confirmed", "needs_validation", "rejected"}
FINDING_VERDICTS = {"confirmed", "refuted", "not_reproduced"}
SEVERITIES = {"critical", "high", "medium", "low", "info"}
RUN_STATUSES = {"in_progress", "complete", "incomplete"}


class AuditError(ModelError):
    """The audit ledger is missing, malformed, or internally inconsistent."""


def _audit_root(project: Project) -> Path:
    root = project.state / "audits"
    if root.is_symlink():
        raise AuditError("audit directory must not be a symlink")
    return root


def _audit_dir(project: Project, audit_id: str = "") -> Path:
    root = _audit_root(project)
    if audit_id:
        if not audit_id.startswith(AUDIT_ID) or "/" in audit_id or "\\" in audit_id or ".." in audit_id:
            raise AuditError(f"invalid audit id: {audit_id}")
        path = root / audit_id
        if path.is_symlink() or not path.is_dir():
            raise AuditError(f"unknown audit: {audit_id}")
        return path
    candidates: list[tuple[str, float, str, Path]] = []
    for path in root.glob("audit-*"):
        if path.is_symlink() or not path.is_dir() or not (path / "run-metadata.json").is_file():
            continue
        created = ""
        try:
            metadata = json.loads((path / "run-metadata.json").read_text(encoding="utf-8"))
            if isinstance(metadata, dict) and isinstance(metadata.get("created_at"), str):
                created = metadata["created_at"]
        except (OSError, UnicodeError, json.JSONDecodeError):
            pass
        try:
            modified = path.stat().st_mtime
        except OSError:
            continue
        candidates.append((created, modified, path.name, path))
    if not candidates:
        raise AuditError("no security audit exists; run `aperio audit start` first")
    return max(candidates, key=lambda item: (item[0], item[1], item[2]))[3]


def _read(path: Path, label: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuditError(f"{label} is unreadable: {exc}") from exc
    if not isinstance(data, dict):
        raise AuditError(f"{label} must be a JSON object")
    return data


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        replace_text_atomic(path, json.dumps(data, indent=2, sort_keys=True) + "\n")
    except PathSafetyError as exc:
        raise AuditError(f"audit state file is unsafe: {exc}") from exc


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        replace_text_atomic(path, text)
    except PathSafetyError as exc:
        raise AuditError(f"report artifact is unsafe: {exc}") from exc


def _git_ref(root: Path) -> dict[str, Any]:
    if not (root / ".git").exists():
        return {"commit": "", "dirty": None}
    base = [
        "git",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "core.pager=cat",
        "-C",
        str(root),
    ]
    result: dict[str, Any] = {"commit": "", "dirty": None}
    try:
        commit = subprocess.run(
            base + ["rev-parse", "HEAD"], check=False, capture_output=True, text=True, timeout=5
        )
        if commit.returncode == 0:
            result["commit"] = commit.stdout.strip()
        dirty = subprocess.run(
            base + ["status", "--porcelain"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if dirty.returncode == 0:
            result["dirty"] = bool(dirty.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        pass
    return result


def _collect_units(project: Project, scope: str) -> tuple[list[str], bool]:
    root = project.root
    target = Path(scope).expanduser()
    if not target.is_absolute():
        target = root / target
    try:
        resolved = target.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise AuditError(f"audit scope must be an existing path inside the project: {scope}") from exc
    if resolved.is_symlink():
        raise AuditError("audit scope must not be a symlink")
    paths: list[str] = []
    if resolved.is_file():
        paths.append(resolved.relative_to(root).as_posix())
    elif resolved.is_dir():
        for current, dirnames, filenames in os.walk(resolved, followlinks=False):
            dirnames[:] = sorted(
                name
                for name in dirnames
                if name not in SKIP_DIRS and not (Path(current) / name).is_symlink()
            )
            for name in sorted(filenames):
                path = Path(current) / name
                if path.is_symlink() or not path.is_file():
                    continue
                paths.append(path.relative_to(root).as_posix())
                if len(paths) > MAX_UNITS:
                    return sorted(paths[:MAX_UNITS]), True
    else:
        raise AuditError("audit scope must be a file or directory")
    return sorted(paths), False


def start(project: Project, scope: str = ".", profile: str = "quick") -> dict[str, Any]:
    if not isinstance(profile, str) or profile not in PROFILES:
        raise AuditError(f"profile must be one of: {', '.join(sorted(PROFILES))}")
    paths, truncated = _collect_units(project, scope)
    if not paths:
        raise AuditError("audit scope contains no readable files")
    audit_id = f"{AUDIT_ID}{uuid.uuid4().hex[:10]}"
    root = _audit_root(project)
    root.mkdir(parents=True, exist_ok=True)
    directory = root / audit_id
    directory.mkdir(parents=True, exist_ok=False)
    source = _git_ref(project.root)
    metadata = {
        "schema": SCHEMA_VERSION,
        "audit_id": audit_id,
        "created_at": utc_now(),
        "repo": project.metadata.get("name", project.root.name),
        "target": str(project.root),
        "scope": scope,
        "profile": profile,
        "source_ref": source,
        "run_status": "in_progress",
        "execution_policy": "read-only-source-only",
        "limits": [
            "This ledger records source review; it does not execute target code.",
            "A confirmed finding requires evidence, a boundary, and a coverage unit.",
            "A needs_validation finding has no severity until the missing fact is resolved.",
        ],
    }
    ledger = {
        "schema": SCHEMA_VERSION,
        "audit_id": audit_id,
        "units": [
            {"id": f"unit-{index:04d}", "path": path, "status": "planned", "note": ""}
            for index, path in enumerate(paths, 1)
        ],
        "truncated": truncated,
    }
    findings = {"schema": SCHEMA_VERSION, "audit_id": audit_id, "findings": []}
    _write(directory / "run-metadata.json", metadata)
    _write(directory / "coverage-ledger.json", ledger)
    _write(directory / "findings.json", findings)
    project.append_event(
        "audit.started",
        {"audit_id": audit_id, "profile": profile, "units": len(paths), "truncated": truncated},
    )
    return {
        "audit_id": audit_id,
        "path": str(directory),
        "units": len(paths),
        "truncated": truncated,
        "profile": profile,
    }


def load(project: Project, audit_id: str = "") -> tuple[Path, dict[str, Any], dict[str, Any], dict[str, Any]]:
    directory = _audit_dir(project, audit_id)
    metadata = _read(directory / "run-metadata.json", "run metadata")
    ledger = _read(directory / "coverage-ledger.json", "coverage ledger")
    findings = _read(directory / "findings.json", "findings")
    return directory, metadata, ledger, findings


def _unit_ids(ledger: dict[str, Any]) -> set[str]:
    units = ledger.get("units")
    if not isinstance(units, list):
        raise AuditError("coverage ledger units must be a list")
    ids: set[str] = set()
    for unit in units:
        if not isinstance(unit, dict) or not isinstance(unit.get("id"), str):
            raise AuditError("coverage ledger contains a malformed unit")
        if unit["id"] in ids:
            raise AuditError(f"duplicate coverage unit: {unit['id']}")
        ids.add(unit["id"])
    return ids


def set_unit(
    project: Project,
    *,
    unit_id: str,
    status: str,
    note: str = "",
    audit_id: str = "",
) -> dict[str, Any]:
    directory, metadata, ledger, _findings = load(project, audit_id)
    if not isinstance(status, str) or status not in UNIT_STATUSES:
        raise AuditError(f"unit status must be one of: {', '.join(sorted(UNIT_STATUSES))}")
    units = ledger.get("units")
    if not isinstance(units, list):
        raise AuditError("coverage ledger units must be a list")
    for unit in units:
        if isinstance(unit, dict) and unit.get("id") == unit_id:
            unit["status"] = status
            unit["note"] = note.strip()
            _write(directory / "coverage-ledger.json", ledger)
            metadata["run_status"] = "in_progress"
            metadata.pop("reported_at", None)
            _write(directory / "run-metadata.json", metadata)
            project.append_event("audit.unit", {"audit_id": audit_id or directory.name, "unit_id": unit_id, "status": status})
            return unit
    raise AuditError(f"unknown coverage unit: {unit_id}")


def validate(project: Project, audit_id: str = "") -> list[str]:
    directory, metadata, ledger, findings = load(project, audit_id)
    errors: list[str] = []
    audit_id = directory.name
    if metadata.get("schema") != SCHEMA_VERSION:
        errors.append("run metadata has an unsupported schema")
    if metadata.get("audit_id") != audit_id:
        errors.append("run metadata audit_id does not match its directory")
    if not isinstance(metadata.get("profile"), str) or metadata.get("profile") not in PROFILES:
        errors.append("run metadata has an unknown profile")
    if not isinstance(metadata.get("run_status"), str) or metadata.get("run_status") not in RUN_STATUSES:
        errors.append("run metadata has an unknown run_status")
    if ledger.get("schema") != SCHEMA_VERSION:
        errors.append("coverage ledger has an unsupported schema")
    if ledger.get("audit_id") != audit_id:
        errors.append("coverage ledger audit_id does not match its directory")
    if findings.get("schema") != SCHEMA_VERSION:
        errors.append("findings has an unsupported schema")
    if findings.get("audit_id") != audit_id:
        errors.append("findings audit_id does not match its directory")
    if not isinstance(ledger.get("units"), list):
        errors.append("coverage ledger units must be a list")
        units: list[dict[str, Any]] = []
    else:
        units = [unit for unit in ledger["units"] if isinstance(unit, dict)]
        if len(units) != len(ledger["units"]):
            errors.append("coverage ledger contains a non-object unit")
    ids: set[str] = set()
    unit_paths: dict[str, str] = {}
    for unit in units:
        unit_id = unit.get("id")
        path = unit.get("path")
        if not isinstance(unit_id, str) or not unit_id:
            errors.append("coverage unit is missing an id")
            continue
        if unit_id in ids:
            errors.append(f"duplicate coverage unit: {unit_id}")
        ids.add(unit_id)
        if not isinstance(unit.get("status"), str) or unit.get("status") not in UNIT_STATUSES:
            errors.append(f"{unit_id}: unknown coverage status")
        if not isinstance(path, str):
            errors.append(f"{unit_id}: missing path")
            continue
        try:
            normalized = normalize_rel(path)
            unit_paths[unit_id] = normalized
        except PathSafetyError as exc:
            errors.append(f"{unit_id}: unsafe path: {exc}")
    finding_list = findings.get("findings")
    if not isinstance(finding_list, list):
        errors.append("findings must be a list")
        finding_list = []
    seen: set[str] = set()
    for finding in finding_list:
        if not isinstance(finding, dict):
            errors.append("findings contains a non-object entry")
            continue
        finding_id = finding.get("id")
        status = finding.get("status")
        if not isinstance(finding_id, str) or not finding_id:
            errors.append("finding is missing an id")
            continue
        if finding_id in seen:
            errors.append(f"duplicate finding: {finding_id}")
        seen.add(finding_id)
        if not isinstance(status, str) or status not in FINDING_STATUSES:
            errors.append(f"{finding_id}: unknown status")
        if not isinstance(finding.get("title"), str) or not finding["title"].strip():
            errors.append(f"{finding_id}: missing title")
        if not isinstance(finding.get("evidence"), str) or not finding["evidence"].strip():
            errors.append(f"{finding_id}: missing evidence")
        unit_id = finding.get("unit_id")
        if not isinstance(unit_id, str) or unit_id not in ids:
            errors.append(f"{finding_id}: unknown coverage unit")
        path = finding.get("path")
        normalized_path = ""
        if path is not None:
            if not isinstance(path, str):
                errors.append(f"{finding_id}: path must be a string")
            else:
                try:
                    normalized_path = normalize_rel(path)
                except PathSafetyError as exc:
                    errors.append(f"{finding_id}: unsafe path: {exc}")
        if normalized_path and normalized_path not in unit_paths.values():
            errors.append(f"{finding_id}: path is not a coverage unit")
        if status == "confirmed":
            if normalized_path and unit_paths.get(str(unit_id)) != normalized_path:
                errors.append(f"{finding_id}: path does not match its coverage unit")
            if not isinstance(finding.get("line"), int) or isinstance(finding.get("line"), bool) or finding["line"] < 1:
                errors.append(f"{finding_id}: confirmed finding needs a positive line")
            evidence = finding.get("evidence")
            if isinstance(evidence, str) and normalized_path and normalized_path not in evidence:
                errors.append(f"{finding_id}: evidence does not contain the finding path")
        severity = finding.get("severity")
        if status == "confirmed":
            if not isinstance(severity, str) or severity not in SEVERITIES:
                errors.append(f"{finding_id}: confirmed finding needs a severity")
            if not isinstance(finding.get("boundary"), str) or not finding["boundary"].strip():
                errors.append(f"{finding_id}: confirmed finding needs a boundary")
            if not isinstance(finding.get("path"), str) or not finding["path"].strip():
                errors.append(f"{finding_id}: confirmed finding needs a path")
        elif severity not in (None, ""):
            errors.append(f"{finding_id}: only confirmed findings may have severity")
        line = finding.get("line")
        if status != "confirmed" and line is not None and (not isinstance(line, int) or isinstance(line, bool) or line < 1):
            errors.append(f"{finding_id}: line must be a positive integer")
        verification = finding.get("verification")
        if verification is not None:
            if not isinstance(verification, dict):
                errors.append(f"{finding_id}: verification must be an object")
            else:
                if not isinstance(verification.get("verdict"), str) or verification.get("verdict") not in FINDING_VERDICTS:
                    errors.append(f"{finding_id}: verification verdict is invalid")
                if not isinstance(verification.get("by"), str) or not verification["by"].strip():
                    errors.append(f"{finding_id}: verification needs a verifier")
                if not isinstance(verification.get("evidence"), str) or not verification["evidence"].strip():
                    errors.append(f"{finding_id}: verification needs evidence")
    return errors


def _finding_record(
    ledger: dict[str, Any],
    *,
    title: str,
    status: str,
    unit_id: str = "",
    path: str = "",
    line: int | None = None,
    severity: str = "",
    boundary: str = "",
    evidence: str = "",
) -> dict[str, Any]:
    if not isinstance(status, str) or status not in FINDING_STATUSES:
        raise AuditError(f"finding status must be one of: {', '.join(sorted(FINDING_STATUSES))}")
    title = title.strip() if isinstance(title, str) else ""
    evidence = evidence.strip() if isinstance(evidence, str) else ""
    boundary = boundary.strip() if isinstance(boundary, str) else ""
    if not title:
        raise AuditError("finding needs a title")
    if not evidence:
        raise AuditError("finding needs evidence")
    if line is not None and (not isinstance(line, int) or isinstance(line, bool) or line < 1):
        raise AuditError("finding line must be a positive integer")
    if severity and not isinstance(severity, str):
        raise AuditError("finding severity must be a string")
    if status == "confirmed" and severity not in SEVERITIES:
        raise AuditError("a confirmed finding needs a severity")
    if status != "confirmed" and severity:
        raise AuditError("only a confirmed finding may have a severity")
    if status == "confirmed" and not boundary:
        raise AuditError("a confirmed finding needs a boundary")
    ids = _unit_ids(ledger)
    if not unit_id and path:
        matches = [
            unit["id"]
            for unit in ledger["units"]
            if isinstance(unit, dict) and unit.get("path") == path
        ]
        if len(matches) == 1:
            unit_id = matches[0]
    if not isinstance(unit_id, str) or not unit_id or unit_id not in ids:
        raise AuditError("finding must name an existing coverage unit")
    if path and not isinstance(path, str):
        raise AuditError("finding path must be a string")
    if not path:
        path = next(
            (
                unit["path"]
                for unit in ledger["units"]
                if isinstance(unit, dict) and unit.get("id") == unit_id
            ),
            "",
        )
    if path:
        try:
            path = normalize_rel(path)
        except PathSafetyError as exc:
            raise AuditError(f"finding path is unsafe: {exc}") from exc
    unit_path = next(
        (
            unit["path"]
            for unit in ledger["units"]
            if isinstance(unit, dict) and unit.get("id") == unit_id
        ),
        "",
    )
    if path and unit_path and path != unit_path:
        raise AuditError("finding path must match its coverage unit")
    if status == "confirmed":
        if not path:
            raise AuditError("a confirmed finding needs a path")
        if line is None:
            raise AuditError("a confirmed finding needs a source line")
        if path not in evidence:
            raise AuditError("confirmed evidence must contain the finding path")
    return {
        "id": f"finding-{uuid.uuid4().hex[:10]}",
        "status": status,
        "title": title,
        "unit_id": unit_id,
        "path": path,
        "line": line,
        "severity": severity,
        "boundary": boundary,
        "evidence": evidence,
        "recorded_at": utc_now(),
    }


def add_finding(
    project: Project,
    *,
    title: str,
    status: str,
    unit_id: str = "",
    path: str = "",
    line: int | None = None,
    severity: str = "",
    boundary: str = "",
    evidence: str = "",
    audit_id: str = "",
) -> dict[str, Any]:
    directory, metadata, ledger, findings = load(project, audit_id)
    finding = _finding_record(
        ledger,
        title=title,
        status=status,
        unit_id=unit_id,
        path=path,
        line=line,
        severity=severity,
        boundary=boundary,
        evidence=evidence,
    )
    findings.setdefault("findings", []).append(finding)
    _write(directory / "findings.json", findings)
    metadata["run_status"] = "in_progress"
    metadata.pop("reported_at", None)
    _write(directory / "run-metadata.json", metadata)
    project.append_event("audit.finding", {"audit_id": audit_id or directory.name, "finding_id": finding["id"], "status": status})
    return finding


def verify_finding(
    project: Project,
    finding_id: str,
    *,
    by: str,
    verdict: str,
    evidence: str,
    audit_id: str = "",
) -> dict[str, Any]:
    directory, metadata, _ledger, findings = load(project, audit_id)
    if not isinstance(verdict, str) or verdict not in FINDING_VERDICTS:
        raise AuditError(f"verification verdict must be one of: {', '.join(sorted(FINDING_VERDICTS))}")
    by = by.strip() if isinstance(by, str) else ""
    evidence = evidence.strip() if isinstance(evidence, str) else ""
    if not by:
        raise AuditError("verification needs a verifier")
    if not evidence:
        raise AuditError("verification needs evidence")
    for finding in findings.get("findings", []):
        if isinstance(finding, dict) and finding.get("id") == finding_id:
            if finding.get("status") != "confirmed":
                raise AuditError("only a confirmed finding can be independently verified")
            if isinstance(finding.get("verification"), dict):
                raise AuditError("finding already has a verification verdict; start a new audit to re-verify")
            finding["verification"] = {
                "by": by,
                "verdict": verdict,
                "evidence": evidence,
                "at": utc_now(),
            }
            _write(directory / "findings.json", findings)
            metadata["run_status"] = "in_progress"
            metadata.pop("reported_at", None)
            _write(directory / "run-metadata.json", metadata)
            project.append_event(
                "audit.verified",
                {"audit_id": audit_id or directory.name, "finding_id": finding_id, "verdict": verdict},
            )
            return finding
    raise AuditError(f"unknown finding: {finding_id}")


def brief(project: Project, audit_id: str = "") -> dict[str, Any]:
    errors = validate(project, audit_id)
    if errors:
        raise AuditError("audit ledger is invalid: " + "; ".join(errors))
    directory, metadata, ledger, _findings = load(project, audit_id)
    units = ledger["units"]
    lines = [
        "# Security Audit Brief",
        "",
        f"**Audit:** `{directory.name}`  ",
        f"**Scope:** `{metadata.get('scope', '.')}`  ",
        f"**Profile:** {metadata.get('profile', '')}  ",
        f"**Coverage units:** {len(units)}  ",
        "",
        "Review source only. Do not execute target code. Record a finding only when",
        "the evidence anchors it to a coverage unit. A confirmed finding needs a",
        "boundary, severity, positive line, and evidence containing its path.",
        "Anything unresolved is `needs_validation` and has no severity.",
        "",
        "## Output",
        "",
        "Write one JSON object with this shape and import it with `aperio audit ingest`:",
        "",
        "```json",
        "{",
        "  \"schema\": 1,",
        "  \"findings\": [",
        "    {",
        "      \"title\": \"short title\",",
        "      \"status\": \"confirmed|needs_validation|rejected\",",
        "      \"path\": \"relative/path.py\",",
        "      \"line\": 12,",
        "      \"severity\": \"critical|high|medium|low|info\",",
        "      \"boundary\": \"what crosses what\",",
        "      \"evidence\": \"relative/path.py:12 ...\"",
        "    }",
        "  ]",
        "}",
        "```",
        "",
        "## Coverage units",
        "",
        "| Unit | Path | Status |",
        "|---|---|---|",
    ]
    lines.extend(f"| `{unit['id']}` | `{unit['path']}` | {unit['status']} |" for unit in units)
    lines.extend(
        [
            "",
            "The ledger is not a whole-repository guarantee. The host remains responsible",
            "for the review, and a fresh reviewer must verify every confirmed finding.",
            "",
        ]
    )
    target = directory / "AUDIT-BRIEF.md"
    _write_text(target, "\n".join(lines))
    project.append_event("audit.brief", {"audit_id": directory.name, "units": len(units)})
    return {"audit_id": directory.name, "brief": str(target), "units": len(units)}


def ingest(project: Project, source: str, audit_id: str = "") -> dict[str, Any]:
    errors = validate(project, audit_id)
    if errors:
        raise AuditError("audit ledger is invalid: " + "; ".join(errors))
    directory, metadata, ledger, findings = load(project, audit_id)
    path = Path(source).expanduser()
    try:
        if path.is_symlink() or not path.is_file():
            raise AuditError("findings file must be a regular file, not a symlink")
        if path.stat().st_size > 2_000_000:
            raise AuditError("findings file is too large (limit 2 MB)")
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuditError(f"findings file is unreadable: {exc}") from exc
    if isinstance(raw, dict):
        if raw.get("schema") != SCHEMA_VERSION:
            raise AuditError("findings file has an unsupported schema")
        items = raw.get("findings")
    elif isinstance(raw, list):
        items = raw
    else:
        items = None
    if not isinstance(items, list):
        raise AuditError("findings file must contain a findings list")
    if len(items) > 1000:
        raise AuditError("findings file contains more than 1000 findings")
    allowed = {"title", "status", "path", "line", "severity", "boundary", "evidence"}
    records: list[dict[str, Any]] = []
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            raise AuditError(f"finding {index}: must be an object")
        unknown = set(item) - allowed
        if unknown:
            raise AuditError(f"finding {index}: unknown fields: {', '.join(sorted(unknown))}")
        try:
            record = _finding_record(
                ledger,
                title=item.get("title", ""),
                status=item.get("status", ""),
                path=item.get("path", ""),
                line=item.get("line"),
                severity=item.get("severity", ""),
                boundary=item.get("boundary", ""),
                evidence=item.get("evidence", ""),
            )
        except AuditError as exc:
            raise AuditError(f"finding {index}: {exc}") from exc
        records.append(record)
    if not records:
        raise AuditError("findings file contains no findings")
    findings.setdefault("findings", []).extend(records)
    _write(directory / "findings.json", findings)
    metadata["run_status"] = "in_progress"
    metadata.pop("reported_at", None)
    _write(directory / "run-metadata.json", metadata)
    project.append_event("audit.ingested", {"audit_id": directory.name, "findings": len(records)})
    return {"audit_id": directory.name, "imported": len(records)}


def report(project: Project, audit_id: str = "") -> dict[str, Any]:
    errors = validate(project, audit_id)
    if errors:
        raise AuditError("audit ledger is invalid: " + "; ".join(errors))
    directory, metadata, ledger, findings = load(project, audit_id)
    units = ledger["units"]
    records = findings["findings"]
    confirmed = [row for row in records if row["status"] == "confirmed"]
    unresolved = [row for row in records if row["status"] == "needs_validation"]
    rejected = [row for row in records if row["status"] == "rejected"]
    verified = [
        row
        for row in confirmed
        if isinstance(row.get("verification"), dict)
        and row["verification"].get("verdict") == "confirmed"
    ]
    unverified = [row for row in confirmed if row not in verified and not isinstance(row.get("verification"), dict)]
    contradicted = [row for row in confirmed if isinstance(row.get("verification"), dict) and row not in verified]
    open_findings = len(unresolved) + len(unverified) + len(contradicted)
    counts = {status: sum(1 for unit in units if unit["status"] == status) for status in UNIT_STATUSES}
    open_coverage = counts["planned"] + counts["candidate"] + counts["deferred"]
    truncated = bool(ledger.get("truncated"))
    source_ref = metadata.get("source_ref")
    source_commit = source_ref.get("commit", "") if isinstance(source_ref, dict) else ""
    source_dirty = bool(source_ref.get("dirty")) if isinstance(source_ref, dict) else False
    current_ref = _git_ref(project.root)
    source_changed = current_ref != source_ref
    current_commit = current_ref.get("commit", "")
    current_dirty = bool(current_ref.get("dirty"))
    source_label = f"{source_commit or 'unversioned'}{' (dirty)' if source_dirty else ''}"
    if source_changed:
        source_label += " — changed since audit start"
    header = [
        "# Security Audit Report",
        "",
        f"**Audit:** `{directory.name}`  ",
        f"**Profile:** {metadata['profile']}  ",
        f"**Repo:** {metadata.get('repo', '')}  ",
        f"**Source:** {source_label}  ",
        f"**Current source:** {current_commit or 'unversioned'}{' (dirty)' if current_dirty else ''}  ",
        f"**Scope:** `{metadata.get('scope', '.')}`  ",
        f"**Coverage:** {len(units)} units  ",
        f"**Findings:** {len(confirmed)} confirmed · {len(verified)} verified · {len(unverified)} unverified · {len(contradicted)} contradicted · {len(unresolved)} needs validation · {len(rejected)} rejected",
        "",
        "This is a source-anchored ledger, not proof that every path was audited. A `needs_validation` record has no severity until the missing fact is resolved. An unverified confirmed finding keeps the audit incomplete.",
        "",
        "## Coverage",
        "",
        "| Status | Units |",
        "|---|---:|",
    ]
    header.extend(f"| {status} | {counts[status]} |" for status in sorted(counts))
    if open_coverage:
        header.extend(
            [
                "",
                f"**Coverage is incomplete:** {open_coverage} units are still planned, candidate, or deferred.",
            ]
        )
    if truncated:
        header.extend(["", f"Coverage was capped at {MAX_UNITS} files; the scope is not complete."])
    if source_changed:
        header.extend(["", "**Source changed since the audit started.** Coverage may not match the current tree."])
    unit_status = {unit["id"]: unit["status"] for unit in units}
    confirmed_section = ["## Confirmed findings", ""]
    if confirmed:
        for row in confirmed:
            unit_note = "" if unit_status.get(row["unit_id"]) == "checked" else f" (unit status: {unit_status.get(row['unit_id'], 'unknown')})"
            verification = row.get("verification")
            if isinstance(verification, dict):
                verification_line = (
                    f"- Verification: **{verification.get('verdict', 'unknown')}** "
                    f"by {verification.get('by', 'unknown')} — {verification.get('evidence', '')}"
                )
            else:
                verification_line = "- Verification: **UNVERIFIED**"
            confirmed_section.extend(
                [
                    f"### {row['title']}",
                    "",
                    f"- Severity: **{row['severity']}**",
                    f"- Unit: `{row['unit_id']}`{unit_note}",
                    f"- Path: `{row['path']}`:{row['line']}",
                    f"- Boundary: {row['boundary']}",
                    f"- Evidence: {row['evidence']}",
                    verification_line,
                    "",
                ]
            )
    else:
        confirmed_section.append("None recorded.")
    needs_section = ["## Needs validation", ""]
    if unresolved:
        for row in unresolved:
            needs_section.extend(
                [
                    f"- `{row['id']}` {row['title']} — {row['evidence']}",
                    "  No severity is assigned until the missing fact is resolved.",
                ]
            )
    else:
        needs_section.append("None recorded.")
    rejected_section = ["## Rejected", ""]
    if rejected:
        rejected_section.extend(f"- `{row['id']}` {row['title']} — {row['evidence']}" for row in rejected)
    else:
        rejected_section.append("None recorded.")
    limits = [
        "## Limits",
        "",
        "- Source review only; no target-controlled code was executed.",
        "- A confirmed finding is not proof of exploitability outside the reviewed source.",
        "- This report is not a whole-repository security guarantee.",
        "",
    ]
    report_text = "\n".join(
        header
        + [""]
        + confirmed_section
        + [""]
        + needs_section
        + [""]
        + rejected_section
        + [""]
        + limits
    )
    detail = ["# Findings Detail", ""] + confirmed_section[2:] + [""]
    needs = ["# Needs Validation", ""] + needs_section[2:] + [""]
    _write_text(directory / "REPORT.md", report_text)
    _write_text(directory / "FINDINGS-DETAIL.md", "\n".join(detail))
    _write_text(directory / "NEEDS-VALIDATION.md", "\n".join(needs))
    metadata["run_status"] = "incomplete" if (open_coverage or truncated or source_changed or open_findings) else "complete"
    metadata["reported_at"] = utc_now()
    metadata["reported_source_ref"] = current_ref
    metadata["source_changed"] = source_changed
    _write(directory / "run-metadata.json", metadata)
    project.append_event(
        "audit.reported",
        {
            "audit_id": directory.name,
            "confirmed": len(confirmed),
            "verified": len(verified),
            "unverified": len(unverified),
            "needs_validation": len(unresolved),
            "coverage_open": open_coverage,
            "truncated": truncated,
            "source_changed": source_changed,
        },
    )
    return {
        "audit_id": directory.name,
        "report": str(directory / "REPORT.md"),
        "detail": str(directory / "FINDINGS-DETAIL.md"),
        "needs_validation": str(directory / "NEEDS-VALIDATION.md"),
        "confirmed": len(confirmed),
        "verified": len(verified),
        "unverified": len(unverified),
        "contradicted": len(contradicted),
        "unresolved": len(unresolved),
        "coverage_open": open_coverage,
        "truncated": truncated,
        "source_changed": source_changed,
        "rejected": len(rejected),
        "run_status": metadata["run_status"],
    }


def latest(project: Project) -> dict[str, Any] | None:
    root = _audit_root(project)
    if not root.is_dir():
        return None
    if not any(
        path.is_dir()
        and not path.is_symlink()
        and (path / "run-metadata.json").is_file()
        for path in root.glob("audit-*")
    ):
        return None
    return status(project)


def status(project: Project, audit_id: str = "") -> dict[str, Any]:
    errors = validate(project, audit_id)
    if errors:
        raise AuditError("audit ledger is invalid: " + "; ".join(errors))
    directory, metadata, ledger, findings = load(project, audit_id)
    units = ledger.get("units", [])
    records = findings.get("findings", [])
    recorded_ref = metadata.get("reported_source_ref", metadata.get("source_ref"))
    current_ref = _git_ref(project.root)
    source_changed = current_ref != recorded_ref
    trunc = bool(ledger.get("truncated"))
    needs_validation = sum(1 for row in records if row.get("status") == "needs_validation")
    unverified = sum(
        1
        for row in records
        if row.get("status") == "confirmed"
        and not (
            isinstance(row.get("verification"), dict)
            and row["verification"].get("verdict") == "confirmed"
        )
    )
    run_status = metadata.get("run_status")
    if run_status == "complete" and (trunc or source_changed or needs_validation or unverified):
        run_status = "incomplete"
    return {
        "audit_id": directory.name,
        "path": str(directory),
        "profile": metadata.get("profile"),
        "run_status": run_status,
        "source_changed": source_changed,
        "truncated": trunc,
        "units": len(units),
        "checked": sum(1 for unit in units if unit.get("status") == "checked"),
        "planned": sum(1 for unit in units if unit.get("status") == "planned"),
        "findings": len(records),
        "confirmed": sum(1 for row in records if row.get("status") == "confirmed"),
        "unverified": unverified,
        "needs_validation": needs_validation,
        "rejected": sum(1 for row in records if row.get("status") == "rejected"),
    }
