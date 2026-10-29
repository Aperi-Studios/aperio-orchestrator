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
        checks.append({"file": name, "present": path.is_file()})
    return {"project": str(project.root), "checks": checks}


def _open(args: dict[str, Any], *, required: bool = True) -> Project | None:
    root = str(args.get("project", "") or ".")
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
        params = request.get("params", {})
        name = params.get("name", "")
        handler = _HANDLERS.get(name)
        if handler is None:
            return err(-32602, f"unknown tool: {name}")
        try:
            result = handler(params.get("arguments", {}))
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
                    {"type": "text", "text": json.dumps(result, indent=2, sort_keys=True, default=str)}
                ]
            }
        )
    return err(-32601, f"method not found: {method}")


def serve(stdin: Any = None, stdout: Any = None) -> None:
    """Serve JSON-RPC 2.0 over stdio until EOF. One request per line."""
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
