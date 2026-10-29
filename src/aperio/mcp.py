"""The MCP facade: Aperio's read-only advisors over JSON-RPC 2.0 on stdio.

Zero dependencies: JSON-RPC 2.0 framing on stdin/stdout, methods for the
MCP lifecycle (initialize, tools/list, tools/call) and a deliberately
read-only tool set — next, explain, status, lessons, doctor. Write tools
are excluded by design: the approval phrase must never travel through an
RPC pipe, and a facade that can mutate state is a gate-bypass waiting to
happen. Teach, never automate; advise, never mutate.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .explain import TOPICS as EXPLAIN_TOPICS
from .explain import explain
from .lessons import read_lessons
from .nextstep import next_action
from .store import Project, StoreError

PROTOCOL_VERSION = "2024-11-05"


def _tool_next(args: dict[str, Any]) -> dict[str, Any]:
    project = _open(args)
    return next_action(project)


def _tool_explain(args: dict[str, Any]) -> dict[str, Any]:
    topic = str(args.get("topic", "")).strip().lower()
    if topic not in EXPLAIN_TOPICS:
        raise ValueError(f"unknown topic: {topic} (topics: {', '.join(EXPLAIN_TOPICS)})")
    project = _open(args, required=False)
    return explain(topic, project)


def _tool_status(args: dict[str, Any]) -> dict[str, Any]:
    project = _open(args)
    tasks = [t.to_dict() for t in project.tasks_readonly()]
    return {
        "project": str(project.root),
        "tasks": [
            {k: t.get(k) for k in ("id", "status", "title", "plan_id", "run_id")}
            for t in tasks
        ],
    }


def _tool_lessons(args: dict[str, Any]) -> dict[str, Any]:
    project = _open(args)
    return read_lessons(project)


def _tool_doctor(args: dict[str, Any]) -> dict[str, Any]:
    project = _open(args)
    checks = []
    for name in ("project.json", "queue.json", "lessons.json"):
        path = project.state / name
        entry: dict[str, Any] = {"file": name, "present": path.is_file()}
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                entry["parseable"] = isinstance(data, dict)
                entry["schema"] = data.get("schema") if isinstance(data, dict) else None
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                entry["parseable"] = False
                entry["error"] = str(exc)[:200]
        checks.append(entry)
    return {"project": str(project.root), "checks": checks}


# The default project, set from the CLI's --project at serve time: a tool
# call that omits its project argument targets the server's own project
# (a host review caught the CLI value being ignored).
_DEFAULT_PROJECT: list[str] = []


def _open(args: dict[str, Any], *, required: bool = True) -> Project | None:
    root = str(args.get("project", "") or (_DEFAULT_PROJECT[0] if _DEFAULT_PROJECT else "."))
    try:
        return Project.open(Path(root).expanduser())
    except StoreError:
        if required:
            raise
        return None  # explain works without a project; no live status


TOOLS = [
    {
        "name": "aperio_next",
        "description": (
            "The single next legal action in the Aperio loop, with the exact "
            "command and the gate that requires it. Read-only."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Path to the Aperio project (default: cwd)"},
            },
        },
    },
    {
        "name": "aperio_explain",
        "description": (
            "Explain one Aperio gate: what it checks, why it exists, and the "
            "project's live status. Topics: " + ", ".join(EXPLAIN_TOPICS) + ". Read-only."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "enum": list(EXPLAIN_TOPICS)},
                "project": {"type": "string"},
            },
            "required": ["topic"],
        },
    },
    {
        "name": "aperio_status",
        "description": "Task list with statuses for the Aperio project. Read-only.",
        "inputSchema": {
            "type": "object",
            "properties": {"project": {"type": "string"}},
        },
    },
    {
        "name": "aperio_lessons",
        "description": "The project's lessons ledger: what went wrong before. Read-only.",
        "inputSchema": {
            "type": "object",
            "properties": {"project": {"type": "string"}},
        },
    },
    {
        "name": "aperio_doctor",
        "description": "Check the project's state files are present and parseable. Read-only.",
        "inputSchema": {
            "type": "object",
            "properties": {"project": {"type": "string"}},
        },
    },
]

_HANDLERS = {
    "aperio_next": _tool_next,
    "aperio_explain": _tool_explain,
    "aperio_status": _tool_status,
    "aperio_lessons": _tool_lessons,
    "aperio_doctor": _tool_doctor,
}

# The approval phrase never travels through the facade: over RPC it would
# be a copy-paste-ready bypass an agent could run without the owner ever
# typing it. CLI users keep the guidance; RPC agents get a pointer to it.
APPROVAL_PHRASE = "I approve this plan"
PHRASE_REDACTION = (
    "<redacted: the exact approval phrase is documented in docs/TEACHING.md "
    "and printed by `aperio explain approval` at the CLI; the owner types it>"
)


def _redact_phrase(payload: Any) -> Any:
    """Replace the approval phrase anywhere in a response payload."""
    if isinstance(payload, str):
        return payload.replace(f'--confirm "{APPROVAL_PHRASE}"', f'--confirm {PHRASE_REDACTION}').replace(
            f"--confirm '{APPROVAL_PHRASE}'", f"--confirm {PHRASE_REDACTION}"
        ).replace(APPROVAL_PHRASE, PHRASE_REDACTION)
    if isinstance(payload, dict):
        return {k: _redact_phrase(v) for k, v in payload.items()}
    if isinstance(payload, list):
        return [_redact_phrase(item) for item in payload]
    return payload


def handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    """Handle one JSON-RPC 2.0 request; returns the response or None for notifications."""
    method = request.get("method", "")
    msg_id = request.get("id")

    def ok(result: Any) -> dict[str, Any]:
        if msg_id is None:
            return {}  # notification: no response
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    def err(code: int, message: str, data: Any = None) -> dict[str, Any]:
        if msg_id is None:
            return {}
        error: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return {"jsonrpc": "2.0", "id": msg_id, "error": error}

    if not isinstance(method, str) or not method:
        return err(-32600, "method must be a non-empty string")
    if request.get("jsonrpc") != "2.0":
        return err(-32600, "jsonrpc must be '2.0'")
    if msg_id is not None and (not isinstance(msg_id, (str, int, float)) or isinstance(msg_id, bool)):
        return err(-32600, "id must be a string or number")

    if method == "initialize":
        return ok(
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "aperio", "version": __version__},
            }
        )
    if method == "notifications/initialized":
        return ok(None)
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": TOOLS})
    if method == "tools/call":
        params = request.get("params")
        if not isinstance(params, dict):
            return err(-32602, "tools/call params must be an object")
        name = params.get("name", "")
        if not isinstance(name, str):
            return err(-32602, "tool name must be a string")
        handler = _HANDLERS.get(name)
        if handler is None:
            return err(-32602, f"unknown tool: {name}")
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            return err(-32602, "tool arguments must be an object")
        try:
            result = handler(arguments)
        except (StoreError, ValueError) as exc:
            return ok(
                {
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                }
            )
        return ok(
            {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            _redact_phrase(result), indent=2, sort_keys=True, default=str
                        ),
                    }
                ]
            }
        )
    return err(-32601, f"method not found: {method}")


def serve(stdin: Any = None, stdout: Any = None, *, default_project: str = "") -> None:
    """Serve JSON-RPC 2.0 over stdio until EOF. One request per line."""
    if default_project:
        _DEFAULT_PROJECT.clear()
        _DEFAULT_PROJECT.append(default_project)
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            response: dict[str, Any] | None = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"parse error: {exc}"},
            }
        else:
            if not isinstance(request, dict):
                response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32600, "message": "request must be an object"},
                }
            else:
                response = handle_request(request)
        if response:
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()
