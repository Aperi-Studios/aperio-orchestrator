"""Core data model for Aperio v2.

Everything persisted here is plain JSON so a project can be inspected, backed up,
and resumed without a database or a proprietary service.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


class ModelError(ValueError):
    """Raised when persisted or supplied data does not match the contract."""


@dataclass
class Ask:
    id: str
    text: str
    source: str = "manual"
    created_at: str = field(default_factory=utc_now)
    status: str = "recorded"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Ask:
        return cls(
            id=str(data["id"]),
            text=str(data["text"]),
            source=str(data.get("source", "manual")),
            created_at=str(data.get("created_at", utc_now())),
            status=str(data.get("status", "recorded")),
        )


@dataclass
class Step:
    """One bounded operation in an approved plan.

    kind="write" writes exact content. kind="run" executes a command and declares
    which paths it may change. kind="host" asks an installed coding host to work
    in a disposable copy of the project and returns only changes inside the
    declared paths. There is no fourth kind that silently edits files.
    """

    id: str
    kind: str
    description: str = ""
    path: str | None = None
    content: str | None = None
    command: str | None = None
    host: str | None = None
    prompt: str | None = None
    cwd: str = "."
    timeout_s: int = 120
    max_budget_usd: float = 1.00
    writes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Step:
        kind = str(data.get("kind", "")).strip()
        if kind not in {"write", "run", "host"}:
            raise ModelError(f"step {data.get('id', '?')}: kind must be write, run, or host")
        timeout = int(data.get("timeout_s", 120))
        if timeout < 1 or timeout > 3600:
            raise ModelError(f"step {data.get('id', '?')}: timeout_s must be 1..3600")
        writes = data.get("writes", [])
        if not isinstance(writes, list) or not all(isinstance(w, str) for w in writes):
            raise ModelError(f"step {data.get('id', '?')}: writes must be a list of strings")
        budget = float(data.get("max_budget_usd", 1.00))
        if budget < 0 or budget > 10:
            raise ModelError(f"step {data.get('id', '?')}: max_budget_usd must be 0..10")
        return cls(
            id=str(data["id"]),
            kind=kind,
            description=str(data.get("description", "")),
            path=data.get("path"),
            content=data.get("content"),
            command=data.get("command"),
            host=data.get("host"),
            prompt=data.get("prompt"),
            cwd=str(data.get("cwd", ".")),
            timeout_s=timeout,
            max_budget_usd=budget,
            writes=list(writes),
        )

    def validate(self) -> None:
        if not self.id or not self.id.replace("-", "").replace("_", "").isalnum():
            raise ModelError(f"invalid step id: {self.id!r}")
        if self.kind == "write":
            if not self.path or self.content is None:
                raise ModelError(f"step {self.id}: write needs path and content")
            if self.command or self.host or self.prompt:
                raise ModelError(f"step {self.id}: write cannot also have a command, host, or prompt")
        elif self.kind == "run":
            if not self.command:
                raise ModelError(f"step {self.id}: run needs a command")
            if self.path or self.content is not None or self.host or self.prompt:
                raise ModelError(f"step {self.id}: run cannot also write fixed content or use a host")
        elif self.kind == "host":
            if not self.host or not self.prompt:
                raise ModelError(f"step {self.id}: host needs host and prompt")
            if not self.writes:
                raise ModelError(f"step {self.id}: host needs at least one declared write")
            if self.path or self.content is not None or self.command:
                raise ModelError(f"step {self.id}: host cannot also write fixed content or run a command")


@dataclass
class Acceptance:
    id: str
    command: str
    expected_exit: int = 0
    stdout_contains: str | None = None
    timeout_s: int = 120

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Acceptance:
        timeout = int(data.get("timeout_s", 120))
        if timeout < 1 or timeout > 3600:
            raise ModelError(f"acceptance {data.get('id', '?')}: invalid timeout")
        return cls(
            id=str(data["id"]),
            command=str(data["command"]),
            expected_exit=int(data.get("expected_exit", 0)),
            stdout_contains=data.get("stdout_contains"),
            timeout_s=timeout,
        )

    def validate(self) -> None:
        if not self.id or not self.command.strip():
            raise ModelError("acceptance checks need an id and a command")
        normalized = " ".join(self.command.split())
        if normalized in {"true", ":", "exit 0", "/bin/true", "/usr/bin/true"}:
            raise ModelError(f"acceptance {self.id}: a no-op command cannot prove the work")


@dataclass
class Approval:
    approved_by: str
    approved_at: str = field(default_factory=utc_now)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Approval:
        return cls(
            approved_by=str(data["approved_by"]),
            approved_at=str(data.get("approved_at", utc_now())),
            note=str(data.get("note", "")),
        )


@dataclass
class Review:
    reviewer: str
    verdict: str
    notes: str = ""
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Review:
        verdict = str(data.get("verdict", "")).lower()
        if verdict not in {"confirmed", "refuted"}:
            raise ModelError("review verdict must be confirmed or refuted")
        return cls(
            reviewer=str(data["reviewer"]),
            verdict=verdict,
            notes=str(data.get("notes", "")),
            created_at=str(data.get("created_at", utc_now())),
        )


@dataclass
class Plan:
    id: str
    task_id: str
    title: str
    request: str
    allowed_paths: list[str]
    steps: list[Step]
    acceptance: list[Acceptance]
    created_at: str = field(default_factory=utc_now)
    approval: Approval | None = None
    builder: str = "agent"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["steps"] = [s.to_dict() for s in self.steps]
        data["acceptance"] = [a.to_dict() for a in self.acceptance]
        data["approval"] = self.approval.to_dict() if self.approval else None
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Plan:
        steps = [Step.from_dict(s) for s in data.get("steps", [])]
        acceptance = [Acceptance.from_dict(a) for a in data.get("acceptance", [])]
        approval_data = data.get("approval")
        plan = cls(
            id=str(data["id"]),
            task_id=str(data["task_id"]),
            title=str(data["title"]),
            request=str(data["request"]),
            allowed_paths=[str(p) for p in data.get("allowed_paths", [])],
            steps=steps,
            acceptance=acceptance,
            created_at=str(data.get("created_at", utc_now())),
            approval=Approval.from_dict(approval_data) if approval_data else None,
            builder=str(data.get("builder", "agent")),
        )
        plan.validate()
        return plan

    def validate(self) -> None:
        if not self.id or not self.task_id:
            raise ModelError("plan needs an id and a task_id")
        if not self.title.strip():
            raise ModelError("plan needs a title")
        if not self.allowed_paths:
            raise ModelError("plan needs at least one allowed path")
        if not self.steps:
            raise ModelError("plan needs at least one step")
        seen: set[str] = set()
        for step in self.steps:
            step.validate()
            if step.id in seen:
                raise ModelError(f"duplicate step id: {step.id}")
            seen.add(step.id)
        for check in self.acceptance:
            check.validate()


@dataclass
class Task:
    id: str
    title: str
    request: str
    status: str = "planned"
    plan_id: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    run_id: str | None = None
    review: Review | None = None
    evidence: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    verify_id: str | None = None

    ALLOWED: ClassVar[set[str]] = {
        "planned",
        "approved",
        "applied",
        "verified",
        "reviewed",
        "done",
        "failed",
        "blocked",
        "rolled_back",
    }

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["review"] = self.review.to_dict() if self.review else None
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        review_data = data.get("review")
        task_id = str(data["id"])
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,80}", task_id):
            raise ModelError(f"invalid task id: {task_id!r}")
        task = cls(
            id=task_id,
            title=str(data["title"]),
            request=str(data["request"]),
            status=str(data.get("status", "planned")),
            plan_id=data.get("plan_id"),
            created_at=str(data.get("created_at", utc_now())),
            updated_at=str(data.get("updated_at", utc_now())),
            run_id=data.get("run_id"),
            review=Review.from_dict(review_data) if review_data else None,
            evidence=[str(e) for e in data.get("evidence", [])],
            notes=[str(n) for n in data.get("notes", [])],
            verify_id=data.get("verify_id"),
        )
        if task.status not in cls.ALLOWED:
            raise ModelError(f"task {task.id}: unknown status {task.status!r}")
        return task

    def touch(self) -> None:
        self.updated_at = utc_now()
