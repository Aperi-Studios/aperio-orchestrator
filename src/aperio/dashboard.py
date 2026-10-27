"""Generate a self-contained status dashboard from project state.

The page is a read-only view. It does not call a server, load remote assets, or
execute project code. Every value is escaped before it is written.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any

from .audit import AuditError
from .audit import latest as audit_latest
from .discovery import DiscoveryError
from .discovery import status as discovery_status
from .learning import LearningError
from .learning import status as learning_status
from .paths import PathSafetyError, relative_posix, resolve_inside
from .policy import PROTECTED_PATHS, protected
from .readiness import ReadinessError
from .readiness import status as readiness_status
from .store import Project
from .todo import TodoError
from .todo import status as todo_status
from .toolchain import ToolError
from .toolchain import status as toolchain_status

DASHBOARD_NAME = "dashboard.html"


def _safe(call, fallback: Any) -> Any:
    try:
        return call()
    except (AuditError, DiscoveryError, LearningError, ReadinessError, TodoError, ToolError, OSError):
        return fallback


def _e(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def _badge(value: str, good: bool = False) -> str:
    cls = "good" if good else "muted"
    return f'<span class="badge {cls}">{_e(value)}</span>'


def _section(title: str, body: str) -> str:
    return f'<section><h2>{_e(title)}</h2>{body}</section>'


def _table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{_e(item)}</th>" for item in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{_e(cell)}</td>" for cell in row) + "</tr>" for row in rows
    )
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def render(project: Project) -> str:
    tasks = project.tasks()
    todo = _safe(lambda: todo_status(project), {"tasks": []})
    discovery = _safe(lambda: discovery_status(project), None)
    learning = _safe(lambda: learning_status(project), None)
    readiness = _safe(lambda: readiness_status(project), None)
    tools = _safe(lambda: toolchain_status(project), {"tools": [], "count": 0})
    audit = _safe(lambda: audit_latest(project), None)
    name = _safe(lambda: str(project._read_state_json(project.state / "project.json").get("name") or project.root.name), project.root.name)
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")

    cards = [
        ("Tasks", str(len(tasks)), "queue"),
        ("Todo", f"{sum(1 for t in todo.get('tasks', []) if t.get('status') == 'accepted')}/{len(todo.get('tasks', []))}", "accepted"),
        ("Discovery", "ready" if discovery and discovery.get("ready") else "not ready", "gate"),
        ("Learning", "ready" if learning and learning.get("ready") else "not ready", "gate"),
        ("Readiness", "ready" if readiness and readiness.get("ready") else "not ready", "gate"),
        ("Tools", str(tools.get("count", 0)), "declared"),
    ]
    cards_html = "".join(
        f'<div class="card"><div class="label">{_e(label)}</div>'
        f'<div class="value">{_e(value)}</div><div class="hint">{_e(hint)}</div></div>'
        for label, value, hint in cards
    )

    task_rows = [
        [task.id, task.title, task.status, task.plan_id or "-", task.run_id or "-"]
        for task in tasks
    ]
    todo_rows = [
        [item.get("id", ""), item.get("title", ""), item.get("status", ""), item.get("deliverable", "")]
        for item in todo.get("tasks", [])
    ]
    tool_rows = [
        [item.get("name", ""), item.get("kind", ""), item.get("scope", ""), "installed" if item.get("installed_at") else "declared"]
        for item in tools.get("tools", [])
    ]
    events = []
    for row in project._read_jsonl(project.state / "events.jsonl")[-12:]:
        events.append([row.get("at", ""), row.get("event", "")])

    audit_html = "<p class=\"muted\">No audit ledger.</p>"
    if audit:
        audit_html = (
            f"<p>Verdict: {_badge(str(audit.get('verdict', 'unknown')), audit.get('verdict') == 'ready')} "
            f"Coverage: {_e(audit.get('coverage', 'unknown'))}</p>"
        )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(name)} · Aperio</title>
<style>
:root {{ color-scheme: light dark; --bg:#f6f7f9; --fg:#111827; --muted:#6b7280; --card:#ffffff; --line:#e5e7eb; --accent:#2563eb; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#0b1020; --fg:#e5e7eb; --muted:#9ca3af; --card:#111827; --line:#1f2937; --accent:#60a5fa; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:15px/1.5 ui-sans-serif,system-ui,-apple-system,sans-serif; }}
main {{ max-width:1100px; margin:0 auto; padding:40px 20px 64px; }}
header {{ display:flex; justify-content:space-between; gap:24px; align-items:flex-end; flex-wrap:wrap; margin-bottom:28px; }}
h1 {{ margin:0; font-size:28px; letter-spacing:-.02em; }}
h2 {{ margin:0 0 12px; font-size:16px; letter-spacing:.02em; text-transform:uppercase; color:var(--muted); }}
p {{ margin:0 0 8px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; margin-bottom:28px; }}
.card, section {{ background:var(--card); border:1px solid var(--line); border-radius:14px; }}
.card {{ padding:16px; }}
.label {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.08em; }}
.value {{ font-size:24px; font-weight:700; margin:6px 0 2px; }}
.hint {{ color:var(--muted); font-size:12px; }}
section {{ padding:20px; margin:0 0 16px; }}
.badge {{ display:inline-block; border:1px solid var(--line); border-radius:999px; padding:2px 9px; font-size:12px; }}
.badge.good {{ color:var(--accent); border-color:var(--accent); }}
.muted {{ color:var(--muted); }}
.table-wrap {{ overflow-x:auto; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th, td {{ text-align:left; padding:9px 10px; border-bottom:1px solid var(--line); vertical-align:top; }}
th {{ color:var(--muted); font-weight:600; }}
tr:last-child td {{ border-bottom:0; }}
code {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12px; }}
footer {{ color:var(--muted); font-size:12px; margin-top:24px; }}
</style>
</head>
<body>
<main>
<header>
  <div><h1>{_e(name)}</h1><p class="muted">Read-only Aperio status from the project state files.</p></div>
  <div class="muted">Generated {_e(generated)}</div>
</header>
<div class="grid">{cards_html}</div>
{_section("Tasks", _table(["ID", "Title", "Status", "Plan", "Run"], task_rows) if task_rows else '<p class="muted">No tasks.</p>')}
{_section("Todo ledger", _table(["ID", "Title", "Status", "Deliverable"], todo_rows) if todo_rows else '<p class="muted">No todo tasks.</p>')}
{_section("Toolchain", _table(["Name", "Kind", "Scope", "State"], tool_rows) if tool_rows else '<p class="muted">No declared tools.</p>')}
{_section("Audit", audit_html)}
{_section("Recent events", _table(["At", "Event"], events) if events else '<p class="muted">No events.</p>')}
<footer>Generated by <code>aperio dashboard</code>. This page has no scripts and makes no network requests.</footer>
</main>
</body>
</html>
"""


def write(project: Project, output: str = "", *, force: bool = False) -> str:
    if output:
        # --output must stay inside the project and outside the control plane:
        # this path is owner-facing HTML, never a state file.
        try:
            path = resolve_inside(project.root, output)
        except PathSafetyError as exc:
            raise PathSafetyError(f"dashboard output escapes the project: {output}") from exc
        rel = relative_posix(project.root, path)
        if protected(rel, list(PROTECTED_PATHS)):
            raise PathSafetyError(
                f"dashboard output would overwrite project state: {rel}"
            )
        if path.exists() and not force:
            # D1: a tracked source file must never be silently replaced by HTML
            raise ValueError(f"dashboard output already exists: {path}; pass --force to overwrite")
    else:
        path = project.state / DASHBOARD_NAME
    if path.exists() and path.is_dir():
        raise ValueError(f"dashboard output is a directory: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(project), encoding="utf-8")
    project.append_event("dashboard.written", {"path": str(path)})
    return str(path)
