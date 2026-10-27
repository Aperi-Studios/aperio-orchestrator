"""Project state: atomic JSON, append-only events, asks, plans, and evidence."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .model import Ask, ModelError, Plan, Task, utc_now
from .paths import PathSafetyError, normalize_rel, replace_text_atomic, resolve_inside

STATE_DIR = ".aperio"
SCHEMA_VERSION = 1


class StoreError(RuntimeError):
    """The project is missing, already initialized, or has invalid state."""


class Project:
    def __init__(self, root: Path):
        self.root = root.resolve()
        state = self.root / STATE_DIR
        if state.is_symlink():
            raise StoreError(f"project state must not be a symlink: {state}")
        if state.exists():
            try:
                state.resolve().relative_to(self.root)
            except ValueError as exc:
                raise StoreError(f"project state escapes the project: {state}") from exc
            for child in state.rglob("*"):
                rel = child.relative_to(state)
                if not child.is_symlink():
                    continue
                parts = rel.parts
                if parts and parts[0] in {"dispatch", "reviews"} and len(parts) > 1:
                    continue
                raise StoreError(f"project state contains a symlink: {child}")
        self.state = state

    @classmethod
    def init(cls, root: str | Path, name: str = "") -> Project:
        root_path = Path(root).expanduser().resolve()
        if root_path.exists() and not root_path.is_dir():
            raise StoreError(f"project root is not a directory: {root_path}")
        root_path.mkdir(parents=True, exist_ok=True)
        project = cls(root_path)
        if project.state.exists():
            raise StoreError(f"already initialized: {project.state}")
        project.state.mkdir(parents=True)
        for child in ("plans", "evidence", "runs", "backups", "logs"):
            (project.state / child).mkdir()
        project._write_json(
            project.state / "project.json",
            {
                "schema": SCHEMA_VERSION,
                "id": f"project-{os.urandom(5).hex()}",
                "name": name or root_path.name,
                "root": str(root_path),
                "created_at": utc_now(),
                "policy": {
                    "protected_paths": [".git", ".aperio"],
                    "allow_shell": True,
                    "require_independent_review": True,
                },
            },
        )
        project._write_json(
            project.state / "queue.json",
            {"schema": SCHEMA_VERSION, "tasks": [], "updated_at": utc_now()},
        )
        project.append_event("queue.saved", {"tasks": []})
        (project.state / "asks.jsonl").touch()
        (project.state / "events.jsonl").touch()
        project.append_event("project.initialized", {"name": name or root_path.name})
        return project

    @classmethod
    def open(cls, root: str | Path) -> Project:
        project = cls(Path(root).expanduser())
        if not (project.state / "project.json").is_file():
            raise StoreError(f"not an Aperio project: {project.root} (run aperio init)")
        project._read_state_json(project.state / "project.json")
        return project

    # ---- low-level JSON -------------------------------------------------

    def _read_state_json(self, path: Path, default: Any = None, *, persist_migration: bool = True) -> Any:
        """Read a versioned state file, migrating a missing schema on read.

        A state file written by a newer build is refused rather than guessed at.
        Existing v1 files predate the schema field, so they are migrated in place
        — EXCEPT for read-only callers, which pass persist_migration=False and
        get the migration in memory only: advising or explaining a legacy project
        must never write it (a host review caught explain migrating legacy state
        under a read-only contract).
        """
        data = self._read_json(path, default)
        if not isinstance(data, dict):
            raise StoreError(f"state file must contain an object: {path}")
        schema = data.get("schema")
        if schema is None:
            data["schema"] = SCHEMA_VERSION
            if persist_migration and path.is_file():
                try:
                    self._write_json(path, data)
                except OSError:
                    # read-only mount or permissions: keep the migrated schema
                    # in memory so pure reads still work; the next write persists it
                    pass
        elif schema != SCHEMA_VERSION:
            raise StoreError(
                f"unsupported state schema {schema} in {path}; this build supports {SCHEMA_VERSION}"
            )
        return data

    def _write_json(self, path: Path, data: Any) -> None:
        if path.is_symlink():
            raise StoreError(f"refusing to write through a state symlink: {path}")
        replace_text_atomic(path, json.dumps(data, indent=2, sort_keys=True) + "\n")

    def _read_json(self, path: Path, default: Any = None) -> Any:
        if path.is_symlink():
            raise StoreError(f"refusing to read a state symlink: {path}")
        if not path.is_file():
            if default is not None:
                return default
            raise StoreError(f"missing state file: {path}")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StoreError(f"unreadable state file: {path}: {exc}") from exc

    def _append_jsonl(self, path: Path, data: dict[str, Any]) -> None:
        if path.is_symlink():
            raise StoreError(f"refusing to append through a state symlink: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(data, sort_keys=True) + "\n"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())

    def _read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        if path.is_symlink():
            raise StoreError(f"refusing to read a state symlink: {path}")
        if not path.is_file():
            return []
        rows: list[dict[str, Any]] = []
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise StoreError(f"invalid JSONL at {path}:{number}") from exc
        return rows

    # ---- project metadata ----------------------------------------------

    @property
    def metadata(self) -> dict[str, Any]:
        return self._read_json(self.state / "project.json")

    @contextmanager
    def lock(self) -> Iterator[None]:
        """Best-effort exclusive lock for mutating commands."""
        lock_path = self.state / "lock"
        lock_path.touch(exist_ok=True)
        handle = lock_path.open("r+")
        try:
            try:
                import fcntl
            except ImportError:
                fcntl = None  # type: ignore[assignment]
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            else:
                # Windows has no fcntl. Lock one byte through msvcrt; native
                # Windows execution remains untested, so treat failures as
                # best-effort rather than claiming a guarantee.
                try:
                    import msvcrt

                    locking = getattr(msvcrt, "locking", None)
                    flag = getattr(msvcrt, "LK_LOCK", None)
                    if locking is not None and flag is not None:
                        handle.seek(0)
                        if not handle.read(1):
                            handle.write("\0")
                            handle.flush()
                        handle.seek(0)
                        locking(handle.fileno(), flag, 1)
                except (ImportError, OSError):
                    pass
            yield
        finally:
            try:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except ImportError:
                try:
                    import msvcrt

                    locking = getattr(msvcrt, "locking", None)
                    flag = getattr(msvcrt, "LK_UNLCK", None)
                    if locking is not None and flag is not None:
                        handle.seek(0)
                        locking(handle.fileno(), flag, 1)
                except (ImportError, OSError):
                    pass
            handle.close()

    def append_event(self, event: str, data: dict[str, Any] | None = None) -> None:
        self._append_jsonl(
            self.state / "events.jsonl",
            {"at": utc_now(), "event": event, "data": data or {}},
        )

    # ---- asks -----------------------------------------------------------

    def discovery(self) -> dict[str, Any] | None:
        path = self.state / "discovery.json"
        if not path.is_file():
            return None
        return self._read_state_json(path)

    def discovery_readonly(self) -> dict[str, Any] | None:
        """Read discovery without persisting a schema migration (read-only advisors)."""
        path = self.state / "discovery.json"
        if not path.is_file():
            return None
        return self._read_state_json(path, persist_migration=False)

    def save_discovery(self, data: dict[str, Any]) -> None:
        data = dict(data)
        data["schema"] = SCHEMA_VERSION
        self._write_json(self.state / "discovery.json", data)
        self.append_event("discovery.updated", {"answered": len(data.get("answers", {}))})

    def inspection(self) -> dict[str, Any] | None:
        path = self.state / "inspection.json"
        if not path.is_file():
            return None
        return self._read_state_json(path)

    def save_inspection(self, data: dict[str, Any]) -> None:
        data = dict(data)
        data["schema"] = SCHEMA_VERSION
        self._write_json(self.state / "inspection.json", data)
        self.append_event("inspection.updated", {"kind": data.get("kind", "unknown")})

    def add_ask(self, text: str, source: str = "manual") -> Ask:
        if not text or not text.strip():
            raise ModelError("ask text must not be empty")
        ask = Ask(id=f"ask-{int(time.time())}-{os.urandom(3).hex()}", text=text.strip(), source=source)
        self._append_jsonl(self.state / "asks.jsonl", ask.to_dict())
        self.append_event("ask.recorded", {"ask_id": ask.id, "source": source})
        return ask

    def asks(self) -> list[Ask]:
        return [Ask.from_dict(row) for row in self._read_jsonl(self.state / "asks.jsonl")]

    # ---- queue and tasks ------------------------------------------------

    def tasks(self) -> list[Task]:
        data = self._read_state_json(self.state / "queue.json", {"tasks": []})
        return [Task.from_dict(row) for row in data.get("tasks", [])]

    def tasks_readonly(self) -> list[Task]:
        """Read the queue without persisting a schema migration (read-only advisors)."""
        data = self._read_state_json(self.state / "queue.json", {"tasks": []}, persist_migration=False)
        return [Task.from_dict(row) for row in data.get("tasks", [])]

    def save_tasks(self, tasks: list[Task]) -> None:
        snapshot = [task.to_dict() for task in tasks]
        self._write_json(
            self.state / "queue.json",
            {
                "schema": SCHEMA_VERSION,
                "tasks": snapshot,
                "updated_at": utc_now(),
            },
        )
        self.append_event("queue.saved", {"tasks": snapshot})

    def recover_queue(self) -> list[Task] | None:
        """Restore a missing or corrupt queue from the append-only event journal.

        A queue written by a newer build is refused, not downgraded. This repairs
        the queue document only; it does not invent tasks that were never saved.
        """
        path = self.state / "queue.json"
        try:
            if path.is_file():
                data = self._read_state_json(path)
                return [Task.from_dict(row) for row in data.get("tasks", [])]
        except StoreError as exc:
            if "unsupported state schema" in str(exc):
                raise
        snapshot: list[dict[str, Any]] | None = None
        for row in self._read_jsonl(self.state / "events.jsonl"):
            if row.get("event") != "queue.saved":
                continue
            candidate = row.get("data", {}).get("tasks")
            if isinstance(candidate, list) and all(isinstance(item, dict) for item in candidate):
                snapshot = candidate
        if snapshot is None:
            return None
        self._write_json(
            path,
            {
                "schema": SCHEMA_VERSION,
                "tasks": snapshot,
                "updated_at": utc_now(),
                "recovered_at": utc_now(),
            },
        )
        self.append_event("queue.recovered", {"tasks": len(snapshot)})
        return [Task.from_dict(row) for row in snapshot]

    def get_task(self, task_id: str) -> Task:
        for task in self.tasks():
            if task.id == task_id:
                return task
        raise StoreError(f"unknown task: {task_id}")

    def get_task_readonly(self, task_id: str) -> Task:
        """Read one task without persisting a schema migration (read-only advisors)."""
        for task in self.tasks_readonly():
            if task.id == task_id:
                return task
        raise StoreError(f"unknown task: {task_id}")

    def put_task(self, task: Task) -> None:
        task.touch()
        tasks = self.tasks()
        for index, current in enumerate(tasks):
            if current.id == task.id:
                tasks[index] = task
                break
        else:
            tasks.append(task)
        self.save_tasks(tasks)

    # ---- plans ----------------------------------------------------------

    def plan_path(self, plan_id: str) -> Path:
        safe = normalize_rel(f"plans/{plan_id}.json")
        return resolve_inside(self.state, safe)

    def save_plan(self, plan: Plan) -> None:
        plan.validate()
        data = plan.to_dict()
        data["schema"] = SCHEMA_VERSION
        self._write_json(self.plan_path(plan.id), data)

    def get_plan(self, plan_id: str) -> Plan:
        path = self.plan_path(plan_id)
        if not path.is_file():
            raise StoreError(f"unknown plan: {plan_id}")
        try:
            return Plan.from_dict(self._read_state_json(path))
        except ModelError as exc:
            raise StoreError(f"invalid plan {plan_id}: {exc}") from exc

    def get_plan_readonly(self, plan_id: str) -> Plan:
        """Read one plan without persisting a schema migration (read-only advisors)."""
        path = self.plan_path(plan_id)
        if not path.is_file():
            raise StoreError(f"unknown plan: {plan_id}")
        try:
            return Plan.from_dict(self._read_state_json(path, persist_migration=False))
        except ModelError as exc:
            raise StoreError(f"invalid plan {plan_id}: {exc}") from exc

    def plans(self) -> list[Plan]:
        result: list[Plan] = []
        for path in sorted((self.state / "plans").glob("*.json")):
            try:
                result.append(Plan.from_dict(self._read_state_json(path)))
            except ModelError:
                continue
        return result

    def plans_readonly(self) -> list[Plan]:
        """Read plans without persisting schema migrations (read-only advisors)."""
        result: list[Plan] = []
        for path in sorted((self.state / "plans").glob("*.json")):
            try:
                result.append(Plan.from_dict(self._read_state_json(path, persist_migration=False)))
            except ModelError:
                continue
        return result

    # ---- evidence -------------------------------------------------------

    def evidence_dir(self, task_id: str) -> Path:
        return resolve_inside(self.state, f"evidence/{task_id}", create_parents=True)

    def save_evidence(self, task_id: str, run_id: str, evidence: dict[str, Any]) -> Path:
        directory = self.evidence_dir(task_id)
        path = resolve_inside(directory, f"{run_id}.json")
        payload = dict(evidence)
        payload.setdefault("schema", SCHEMA_VERSION)
        self._write_json(path, payload)
        return path

    def evidence(self, task_id: str) -> list[dict[str, Any]]:
        directory = self.state / "evidence" / task_id
        if not directory.is_dir():
            return []
        rows: list[dict[str, Any]] = []
        for path in sorted(directory.glob("*.json")):
            rows.append(self._read_state_json(path))
        return rows

    # ---- paths ----------------------------------------------------------

    def resolve_project_path(self, rel: str, *, create_parents: bool = False) -> Path:
        try:
            return resolve_inside(self.root, rel, create_parents=create_parents)
        except PathSafetyError as exc:
            raise StoreError(str(exc)) from exc
