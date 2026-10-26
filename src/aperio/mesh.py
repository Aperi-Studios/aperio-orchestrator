"""Local message store and mediator disposition.

This is a durable local mailbox, not a distributed transport. It gives hosts a
shared record on one machine and survives restarts. A live two-host exchange
still has to be proven separately.
"""

from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from .model import utc_now
from .store import Project


class MeshError(RuntimeError):
    """The message store is invalid or the operation is not allowed."""


SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL,
    sender TEXT NOT NULL,
    recipient TEXT NOT NULL,
    task_id TEXT,
    kind TEXT NOT NULL DEFAULT 'note',
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    read_at TEXT,
    ack_at TEXT,
    reply_to INTEGER
);
CREATE INDEX IF NOT EXISTS messages_recipient ON messages(recipient, id);
CREATE INDEX IF NOT EXISTS messages_thread ON messages(thread_id, id);
CREATE INDEX IF NOT EXISTS messages_task ON messages(task_id, id);
"""


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


class MeshStore:
    def __init__(self, project: Project):
        self.project = project
        self.path = project.state / "mesh" / "messages.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.path))
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def send(
        self,
        sender: str,
        recipient: str,
        body: str,
        *,
        task_id: str | None = None,
        kind: str = "note",
        thread_id: str | None = None,
        reply_to: int | None = None,
    ) -> dict[str, Any]:
        if not sender.strip() or not recipient.strip():
            raise MeshError("sender and recipient are required")
        if not body.strip():
            raise MeshError("message body must not be empty")
        if len(body) > 100_000:
            raise MeshError("message body is too large")
        if kind not in {"note", "task", "reply", "review", "status"}:
            raise MeshError(f"unsupported message kind: {kind}")
        thread = thread_id or f"thread-{uuid.uuid4().hex[:10]}"
        cursor = self.connection.execute(
            "INSERT INTO messages(thread_id, sender, recipient, task_id, kind, body, created_at, reply_to) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (thread, sender.strip(), recipient.strip(), task_id, kind, body, utc_now(), reply_to),
        )
        self.connection.commit()
        row = self.connection.execute("SELECT * FROM messages WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return _row(row)

    def read(
        self,
        *,
        recipient: str | None = None,
        task_id: str | None = None,
        thread_id: str | None = None,
        since_id: int = 0,
        limit: int = 100,
        mark_read: bool = False,
    ) -> list[dict[str, Any]]:
        clauses = ["id > ?"]
        values: list[Any] = [since_id]
        if recipient:
            clauses.append("recipient = ?")
            values.append(recipient)
        if task_id:
            clauses.append("task_id = ?")
            values.append(task_id)
        if thread_id:
            clauses.append("thread_id = ?")
            values.append(thread_id)
        values.append(max(1, min(limit, 500)))
        rows = self.connection.execute(
            f"SELECT * FROM messages WHERE {' AND '.join(clauses)} ORDER BY id LIMIT ?",
            values,
        ).fetchall()
        if mark_read and rows:
            ids = [row["id"] for row in rows]
            now = utc_now()
            self.connection.executemany(
                "UPDATE messages SET read_at = COALESCE(read_at, ?) WHERE id = ?",
                [(now, message_id) for message_id in ids],
            )
            self.connection.commit()
            # Return the rows we selected with the same read_at value. The old
            # implementation re-selected after committing, which left a window
            # where a concurrent reader could observe a different result.
            rows = [
                dict(row) if row["read_at"] is not None else {**dict(row), "read_at": now}
                for row in rows
            ]
        return [_row(row) for row in rows]

    def ack(self, message_id: int, actor: str) -> dict[str, Any]:
        if not isinstance(actor, str) or not actor.strip():
            raise MeshError("acknowledging requires an actor")
        row = self.connection.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
        if row is None:
            raise MeshError(f"unknown message: {message_id}")
        now = utc_now()
        self.connection.execute(
            "UPDATE messages SET ack_at = ?, read_at = COALESCE(read_at, ?) WHERE id = ?",
            (now, now, message_id),
        )
        self.connection.commit()
        row = self.connection.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
        return _row(row)

    def reply(self, message_id: int, sender: str, body: str) -> dict[str, Any]:
        parent = self.connection.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
        if parent is None:
            raise MeshError(f"unknown message: {message_id}")
        return self.send(
            sender,
            parent["sender"],
            body,
            task_id=parent["task_id"],
            kind="reply",
            thread_id=parent["thread_id"],
            reply_to=message_id,
        )

    def stats(self) -> dict[str, int]:
        total = self.connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        unread = self.connection.execute("SELECT COUNT(*) FROM messages WHERE read_at IS NULL").fetchone()[0]
        unacked = self.connection.execute("SELECT COUNT(*) FROM messages WHERE ack_at IS NULL").fetchone()[0]
        return {"messages": total, "unread": unread, "unacked": unacked}
