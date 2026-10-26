"""Bounded evidence manifest: record a file reference and its hash, not its contents."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .model import ModelError, utc_now
from .paths import replace_text_atomic
from .store import Project

SCHEMA_VERSION = 1
MAX_BYTES = 20_000_000
MANIFEST_NAME = "manifest.json"


class EvidenceError(ModelError):
    """An evidence attachment is outside the project, unsafe, or too large."""


def _manifest_path(project: Project) -> Path:
    return project.state / "evidence" / MANIFEST_NAME


def _read(project: Project) -> dict[str, Any]:
    path = _manifest_path(project)
    if not path.is_file():
        return {"schema": SCHEMA_VERSION, "entries": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"unreadable evidence manifest: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        raise EvidenceError("evidence manifest is malformed")
    if data.get("schema", SCHEMA_VERSION) != SCHEMA_VERSION:
        raise EvidenceError("evidence manifest has an unsupported schema")
    return data


def _write(project: Project, data: dict[str, Any]) -> None:
    path = _manifest_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    replace_text_atomic(path, json.dumps(data, indent=2, sort_keys=True) + "\n")


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _safe_path(project: Project, value: str) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = project.root / candidate
    if candidate.is_symlink():
        raise EvidenceError("evidence path must not be a symlink")
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise EvidenceError(f"cannot read evidence path: {value}") from exc
    if resolved.is_symlink():
        raise EvidenceError("evidence path must not be a symlink")
    if not resolved.is_file():
        raise EvidenceError("evidence path must be a regular file")
    try:
        resolved.relative_to(project.root)
    except ValueError as exc:
        raise EvidenceError("evidence path must stay inside the project") from exc
    name = resolved.name
    if name == ".env" or (
        name.startswith(".env.") and not name.endswith((".example", ".sample", ".template"))
    ):
        raise EvidenceError("refusing to attach an environment file that may contain secrets")
    return resolved


def add(project: Project, path: str, label: str = "") -> dict[str, Any]:
    resolved = _safe_path(project, path)
    size = resolved.stat().st_size
    if size > MAX_BYTES:
        raise EvidenceError(f"evidence file is larger than {MAX_BYTES} bytes")
    digest = _hash(resolved)
    relative = resolved.relative_to(project.root).as_posix()
    data = _read(project)
    for entry in data["entries"]:
        if isinstance(entry, dict) and entry.get("path") == relative and entry.get("sha256") == digest:
            return entry
    entry = {
        "id": f"ev-{digest[:12]}",
        "label": label.strip() or relative,
        "path": relative,
        "sha256": digest,
        "bytes": size,
        "captured_at": utc_now(),
    }
    data["entries"].append(entry)
    _write(project, data)
    project.append_event("evidence.attached", {"id": entry["id"], "path": relative})
    return entry


def entries(project: Project) -> dict[str, Any]:
    return _read(project)


def format_entries(data: dict[str, Any]) -> str:
    rows = data.get("entries", [])
    if not rows:
        return "No evidence files recorded."
    lines = [f"Evidence files: {len(rows)}", ""]
    for entry in rows:
        lines.append(
            f"{entry.get('id', '?')}  {entry.get('label', '')}  "
            f"{entry.get('path', '')}  {entry.get('sha256', '')[:12]}  "
            f"{entry.get('bytes', 0)} bytes"
        )
    return "\n".join(lines)
