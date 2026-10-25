"""Bounded plan execution, verification, review, and rollback."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import os
import shutil
import subprocess
import time
import uuid

from .model import Plan, Step, utc_now
from .paths import PathSafetyError, relative_posix, replace_text_atomic, sha256_file, sha256_text
from .policy import (
    PolicyError,
    assert_command,
    assert_reviewer,
    assert_writable,
    path_allowed,
    resolve_command_cwd,
    validate_plan_paths,
)
from .store import Project, StoreError


class RunError(RuntimeError):
    """Execution or verification could not proceed safely."""


EXCLUDED_DIRS = {".git", ".aperio", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache"}
MAX_CAPTURE = 200_000
MAX_SNAPSHOT_FILES = 5_000
MAX_SNAPSHOT_BYTES = 50 * 1024 * 1024


def _is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_DIRS for part in path.parts)


def _iter_project_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        for name in filenames:
            path = Path(dirpath) / name
            if path.is_symlink() or _is_excluded(path.relative_to(root)):
                continue
            files.append(path)
    return files


def _expand_targets(project: Project, plan: Plan) -> list[str]:
    targets: set[str] = set()
    for step in plan.steps:
        if step.kind == "write" and step.path:
            targets.add(assert_writable(step.path, plan))
        elif step.kind == "run":
            for item in step.writes:
                normalized = assert_writable(item, plan)
                candidate = project.root / normalized
                if any(char in normalized for char in "*?["):
                    for path in project.root.glob(normalized):
                        if path.is_file() and not path.is_symlink():
                            targets.add(relative_posix(project.root, path))
                elif candidate.is_dir():
                    for path in candidate.rglob("*"):
                        if path.is_file() and not path.is_symlink() and not _is_excluded(path.relative_to(project.root)):
                            targets.add(relative_posix(project.root, path))
                else:
                    targets.add(normalized)
    return sorted(targets)


def _snapshot(project: Project, run_id: str, targets: list[str]) -> dict[str, Any]:
    backup_root = project.state / "backups" / run_id / "files"
    backup_root.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {}
    total_bytes = 0
    for rel in targets:
        path = project.resolve_project_path(rel)
        if path.is_dir():
            continue
        if not path.exists():
            manifest[rel] = {"existed": False, "sha256": None}
            continue
        size = path.stat().st_size
        total_bytes += size
        if len(manifest) >= MAX_SNAPSHOT_FILES or total_bytes > MAX_SNAPSHOT_BYTES:
            raise RunError("snapshot limit exceeded; narrow the plan's allowed paths")
        destination = backup_root / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        manifest[rel] = {"existed": True, "sha256": sha256_file(path), "size": size}
    (project.state / "backups" / run_id / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def _restore(project: Project, run_id: str) -> list[str]:
    backup_dir = project.state / "backups" / run_id
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.is_file():
        raise RunError(f"no backup manifest for run: {run_id}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    restored: list[str] = []
    for rel, record in manifest.items():
        target = project.resolve_project_path(rel, create_parents=True)
        if target.is_dir():
            # A directory target is represented by the files inside it. Those
            # file entries are restored or removed separately.
            continue
        if record.get("existed"):
            source = backup_dir / "files" / rel
            if not source.is_file():
                raise RunError(f"backup file missing: {rel}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        elif target.exists():
            target.unlink()
        restored.append(rel)
    return restored


def _changed_files(project: Project, before: dict[str, str]) -> list[str]:
    changed: set[str] = set()
    current: dict[str, str] = {}
    for path in _iter_project_files(project.root):
        rel = relative_posix(project.root, path)
        try:
            current[rel] = sha256_file(path)
        except OSError:
            continue
        if before.get(rel) != current[rel]:
            changed.add(rel)
    for rel in before:
        if rel not in current:
            changed.add(rel)
    return sorted(changed)


def _hash_project(project: Project) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in _iter_project_files(project.root):
        try:
            result[relative_posix(project.root, path)] = sha256_file(path)
        except OSError:
            continue
    return result


def _run_command(project: Project, plan: Plan, step: Step, run_id: str) -> dict[str, Any]:
    assert_command(step.command or "", step)
    cwd = resolve_command_cwd(project.root, step.cwd)
    if not cwd.is_dir():
        raise RunError(f"step {step.id}: cwd does not exist: {step.cwd}")
    env = os.environ.copy()
    env.update(
        {
            "APERIO_TASK_ID": plan.task_id,
            "APERIO_PLAN_ID": plan.id,
            "APERIO_RUN_ID": run_id,
            "APERIO_PROJECT_ROOT": str(project.root),
        }
    )
    started = time.monotonic()
    try:
        completed = subprocess.run(
            step.command or "",
            shell=True,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=step.timeout_s,
        )
        exit_code = completed.returncode
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        exit_code = 124
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        timed_out = True
    duration = round(time.monotonic() - started, 3)
    return {
        "step_id": step.id,
        "kind": "run",
        "command": step.command,
        "cwd": step.cwd,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_s": duration,
        "stdout": stdout[-MAX_CAPTURE:],
        "stderr": stderr[-MAX_CAPTURE:],
        "stdout_truncated": len(stdout) > MAX_CAPTURE,
        "stderr_truncated": len(stderr) > MAX_CAPTURE,
    }


def apply_plan(project: Project, plan: Plan, actor: str = "agent") -> dict[str, Any]:
    """Apply an approved plan. Returns the evidence record."""
    if not plan.approval:
        raise RunError("plan is not approved")
    if plan.approval.approved_by.strip().lower() == actor.strip().lower():
        # An owner may also be the actor in a tiny project; record it rather than
        # pretending it is independent review. Verification still needs a reviewer.
        pass
    try:
        validate_plan_paths(plan, project.metadata.get("policy", {}).get("protected_paths"))
    except PolicyError as exc:
        raise RunError(str(exc)) from exc

    run_id = f"run-{uuid.uuid4().hex[:10]}"
    targets = _expand_targets(project, plan)
    before_hashes = _hash_project(project)
    manifest = _snapshot(project, run_id, targets)
    run_dir = project.state / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    evidence: dict[str, Any] = {
        "run_id": run_id,
        "task_id": plan.task_id,
        "plan_id": plan.id,
        "actor": actor,
        "started_at": utc_now(),
        "status": "running",
        "steps": [],
        "changed_files": [],
        "violations": [],
        "snapshot": {"files": len(manifest), "limited_to": targets[:50]},
        "limits": "Shell steps are not OS-sandboxed. Writes outside the plan are detected after they happen.",
    }
    project.append_event("run.started", {"run_id": run_id, "task_id": plan.task_id, "actor": actor})

    failed = False
    try:
        for step in plan.steps:
            if step.kind == "write":
                rel = assert_writable(step.path or "", plan)
                target = project.resolve_project_path(rel, create_parents=True)
                replace_text_atomic(target, step.content or "")
                evidence["steps"].append(
                    {
                        "step_id": step.id,
                        "kind": "write",
                        "path": rel,
                        "sha256": sha256_text(step.content or ""),
                        "bytes": len((step.content or "").encode("utf-8")),
                    }
                )
            elif step.kind == "run":
                result = _run_command(project, plan, step, run_id)
                evidence["steps"].append(result)
                if result["exit_code"] != 0:
                    failed = True
                    evidence["violations"].append(f"step {step.id} exited {result['exit_code']}")
                    break
            else:
                raise RunError(f"unsupported step kind: {step.kind}")
    except (OSError, PathSafetyError, PolicyError, RunError) as exc:
        failed = True
        evidence["violations"].append(str(exc))
        # Restore only files captured before execution. Commands may have made
        # changes that were not declared; the report lists them instead of hiding them.
        try:
            _restore(project, run_id)
            evidence["restored"] = True
        except (OSError, RunError) as restore_exc:
            evidence["restored"] = False
            evidence["restore_error"] = str(restore_exc)

    changed = _changed_files(project, before_hashes)
    evidence["changed_files"] = changed
    allowed = set(targets)
    outside = [
        rel
        for rel in changed
        if not any(rel == target or rel.startswith(target.rstrip("/") + "/") for target in allowed)
    ]
    if outside:
        failed = True
        evidence["violations"].extend(f"changed outside declared writes: {rel}" for rel in outside)

    # Record files that did not exist before this run so rollback can remove them.
    manifest_path = project.state / "backups" / run_id / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for rel in changed:
            if rel not in manifest and rel not in before_hashes:
                manifest[rel] = {"existed": False, "sha256": None}
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    evidence["status"] = "failed" if failed else "applied"
    evidence["finished_at"] = utc_now()
    evidence_path = project.save_evidence(plan.task_id, run_id, evidence)
    (run_dir / "manifest.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    task = project.get_task(plan.task_id)
    task.run_id = run_id
    task.status = "failed" if failed else "applied"
    task.evidence.append(str(evidence_path))
    if failed:
        task.notes.append(f"run {run_id} failed: " + "; ".join(evidence["violations"][:3]))
    project.put_task(task)
    project.append_event(
        "run.finished",
        {"run_id": run_id, "status": evidence["status"], "violations": len(evidence["violations"])},
    )
    return evidence


def verify(project: Project, task_id: str) -> dict[str, Any]:
    task = project.get_task(task_id)
    if not task.plan_id:
        raise RunError("task has no plan")
    plan = project.get_plan(task.plan_id)
    if task.status not in {"applied", "verified", "reviewed", "failed"}:
        raise RunError(f"task is {task.status}; run the plan before verifying")
    if task.run_id:
        run_records = [row for row in project.evidence(task_id) if row.get("run_id") == task.run_id]
        if not run_records or run_records[-1].get("status") != "applied":
            raise RunError("the last run did not apply cleanly; fix the violation and rerun the plan")
    check_id = f"verify-{uuid.uuid4().hex[:10]}"
    evidence: dict[str, Any] = {
        "check_id": check_id,
        "task_id": task_id,
        "plan_id": plan.id,
        "started_at": utc_now(),
        "checks": [],
        "status": "running",
    }
    all_ok = True
    for check in plan.acceptance:
        started = time.monotonic()
        try:
            completed = subprocess.run(
                check.command,
                shell=True,
                cwd=str(project.root),
                capture_output=True,
                text=True,
                errors="replace",
                timeout=check.timeout_s,
            )
            exit_code = completed.returncode
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
        except subprocess.TimeoutExpired as exc:
            exit_code = 124
            stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
            stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        ok = exit_code == check.expected_exit
        if check.stdout_contains is not None and check.stdout_contains not in stdout:
            ok = False
        all_ok = all_ok and ok
        evidence["checks"].append(
            {
                "check_id": check.id,
                "command": check.command,
                "exit_code": exit_code,
                "expected_exit": check.expected_exit,
                "stdout_contains": check.stdout_contains,
                "ok": ok,
                "duration_s": round(time.monotonic() - started, 3),
                "stdout": stdout[-MAX_CAPTURE:],
                "stderr": stderr[-MAX_CAPTURE:],
            }
        )
    evidence["status"] = "passed" if all_ok else "failed"
    evidence["finished_at"] = utc_now()
    path = project.save_evidence(task_id, check_id, evidence)
    task.evidence.append(str(path))
    task.status = "verified" if all_ok else "failed"
    if not all_ok:
        task.notes.append(f"verification {check_id} failed")
    project.put_task(task)
    project.append_event("verify.finished", {"task_id": task_id, "status": evidence["status"]})
    return evidence


def review(project: Project, task_id: str, reviewer: str, verdict: str, notes: str = "") -> dict[str, Any]:
    task = project.get_task(task_id)
    if task.status not in {"verified", "reviewed"}:
        raise RunError(f"task is {task.status}; verification must pass before review")
    if not task.plan_id:
        raise RunError("task has no plan")
    plan = project.get_plan(task.plan_id)
    try:
        assert_reviewer(plan.builder, reviewer)
    except PolicyError as exc:
        raise RunError(str(exc)) from exc
    if verdict not in {"confirmed", "refuted"}:
        raise RunError("verdict must be confirmed or refuted")
    from .model import Review

    task.review = Review(reviewer=reviewer.strip(), verdict=verdict, notes=notes)
    task.status = "reviewed" if verdict == "confirmed" else "failed"
    path = project.save_evidence(
        task_id,
        f"review-{uuid.uuid4().hex[:10]}",
        {
            "task_id": task_id,
            "reviewer": task.review.reviewer,
            "verdict": verdict,
            "notes": notes,
            "at": task.review.created_at,
        },
    )
    task.evidence.append(str(path))
    project.put_task(task)
    project.append_event("review.recorded", {"task_id": task_id, "reviewer": reviewer, "verdict": verdict})
    return task.review.to_dict()


def finish(project: Project, task_id: str) -> dict[str, Any]:
    task = project.get_task(task_id)
    if task.status != "reviewed":
        raise RunError(f"task is {task.status}; a confirmed independent review is required")
    if not task.review or task.review.verdict != "confirmed":
        raise RunError("review is not confirmed")
    if not task.plan_id:
        raise RunError("task has no plan")
    plan = project.get_plan(task.plan_id)
    if not plan.acceptance:
        raise RunError("task has no acceptance checks")
    task.status = "done"
    project.put_task(task)
    project.append_event("task.done", {"task_id": task_id})
    return task.to_dict()


def rollback(project: Project, task_id: str) -> list[str]:
    task = project.get_task(task_id)
    if not task.run_id:
        raise RunError("task has no run to roll back")
    restored = _restore(project, task.run_id)
    task.status = "rolled_back"
    task.notes.append(f"rolled back run {task.run_id}")
    project.put_task(task)
    project.append_event("run.rolled_back", {"task_id": task_id, "run_id": task.run_id, "files": len(restored)})
    return restored
