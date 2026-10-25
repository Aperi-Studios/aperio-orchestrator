"""Bounded plan execution, verification, review, and rollback."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from .adapter import HostError, run_host_step
from .model import Plan, Step, Task, utc_now
from .paths import (
    PathSafetyError,
    relative_posix,
    replace_bytes_atomic,
    replace_text_atomic,
    sha256_file,
    sha256_text,
)
from .policy import (
    PolicyError,
    assert_command,
    assert_reviewer,
    assert_writable,
    resolve_command_cwd,
    validate_plan_paths,
)
from .store import Project


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


def _iter_project_symlinks(root: Path) -> list[Path]:
    links: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        for name in list(dirnames) + list(filenames):
            path = Path(dirpath) / name
            if path.is_symlink():
                links.append(path)
    return links


def _expand_targets(project: Project, plan: Plan) -> list[str]:
    targets: set[str] = set()
    for step in plan.steps:
        if step.kind == "write" and step.path:
            targets.add(assert_writable(step.path, plan))
        elif step.kind in {"run", "host"}:
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


def _current_hashes(project: Project) -> dict[str, str]:
    current: dict[str, str] = {}
    for path in _iter_project_files(project.root):
        try:
            current[relative_posix(project.root, path)] = sha256_file(path)
        except OSError:
            continue
    for path in _iter_project_symlinks(project.root):
        try:
            current[path.relative_to(project.root).as_posix()] = "symlink:" + os.readlink(path)
        except OSError:
            continue
    return current


def _changed_files(project: Project, before: dict[str, str]) -> list[str]:
    changed: set[str] = set()
    current = _current_hashes(project)
    for rel, digest in current.items():
        if before.get(rel) != digest:
            changed.add(rel)
    for rel in before:
        if rel not in current:
            changed.add(rel)
    return sorted(changed)


def _hash_project(project: Project) -> dict[str, str]:
    return _current_hashes(project)


def _hash_control_state(project: Project) -> dict[str, str]:
    """Hash the files that define the approved plan and evidence."""
    paths: list[Path] = [
        project.state / "project.json",
        project.state / "queue.json",
        project.state / "asks.jsonl",
        project.state / "events.jsonl",
    ]
    for directory in (project.state / "plans", project.state / "evidence"):
        if directory.is_dir():
            paths.extend(path for path in directory.rglob("*") if path.is_file())
    result: dict[str, str] = {}
    for path in sorted(paths):
        if not path.is_file():
            continue
        try:
            result[path.relative_to(project.state).as_posix()] = sha256_file(path)
        except OSError:
            continue
    return result


def _artifact_digest(project: Project) -> str:
    return sha256_text(json.dumps(sorted(_hash_project(project).items()), separators=(",", ":")))


def _plan_digest(plan: Plan) -> str:
    return sha256_text(json.dumps(plan.to_dict(), sort_keys=True, separators=(",", ":")))


def _current_verification(project: Project, task: Task) -> dict[str, Any]:
    if not task.verify_id:
        raise RunError("task has no current verification")
    rows = [row for row in project.evidence(task.id) if row.get("check_id") == task.verify_id]
    if not rows:
        raise RunError("current verification evidence is missing")
    record = rows[-1]
    if record.get("status") != "passed":
        raise RunError("current verification did not pass")
    if task.plan_id:
        plan = project.get_plan(task.plan_id)
        if record.get("plan_digest") != _plan_digest(plan):
            raise RunError("plan changed after verification; verify again")
    if record.get("artifact_digest") != _artifact_digest(project):
        raise RunError("project changed after verification; verify again")
    return record


def _run_shell_command(
    command: str,
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: int,
) -> tuple[int, str, str, bool]:
    kwargs: dict[str, Any] = {
        "shell": True,
        "cwd": str(cwd),
        "env": env,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "errors": "replace",
    }
    if os.name != "nt":
        kwargs["start_new_session"] = True
    process = subprocess.Popen(command, **kwargs)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return int(process.returncode), stdout or "", stderr or "", False
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
        return 124, stdout or "", stderr or "", True


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
    exit_code, stdout, stderr, timed_out = _run_shell_command(
        step.command or "",
        cwd=cwd,
        env=env,
        timeout=step.timeout_s,
    )
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
    task = project.get_task(plan.task_id)
    if task.status not in {"approved", "applied", "failed"}:
        raise RunError(f"task is {task.status}; create or approve a runnable plan before running")
    if task.review is not None:
        task.review = None
        task.notes.append("previous review cleared by a new run")
    task.verify_id = None
    project.put_task(task)
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
    control_before = _hash_control_state(project)

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
            elif step.kind == "host":
                host_before = _hash_project(project)
                host_result = run_host_step(project, plan, step, run_id)
                host_evidence = host_result.evidence()
                host_evidence["step_id"] = step.id
                host_evidence["kind"] = "host"
                evidence["steps"].append(host_evidence)
                host_delta = _changed_files(project, host_before)
                if host_delta:
                    failed = True
                    evidence["violations"].append(
                        "host changed the real project outside its disposable workspace: "
                        + ", ".join(host_delta)
                    )
                    try:
                        _restore(project, run_id)
                        evidence["restored"] = True
                    except (OSError, RunError) as restore_exc:
                        evidence["restored"] = False
                        evidence["restore_error"] = str(restore_exc)
                    break
                if host_result.status != "ok":
                    failed = True
                    evidence["violations"].append(
                        f"step {step.id}: {host_result.error or 'host dispatch failed'}"
                    )
                    evidence["violations"].extend(host_result.violations)
                    break
                for change in host_result.changes:
                    target = project.resolve_project_path(change.path, create_parents=True)
                    if change.op == "delete":
                        if target.exists():
                            target.unlink()
                    else:
                        replace_bytes_atomic(target, change.content or b"")
            else:
                raise RunError(f"unsupported step kind: {step.kind}")
    except (OSError, PathSafetyError, PolicyError, HostError, RunError) as exc:
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
    if _hash_control_state(project) != control_before:
        failed = True
        evidence["violations"].append("a step changed Aperio's control state (project, queue, plan, or evidence)")
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
    if task.review is not None:
        task.review = None
        task.notes.append("previous review cleared by a new verification")
    task.verify_id = None
    project.put_task(task)
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
    before_hashes = _hash_project(project)
    control_before = _hash_control_state(project)
    for check in plan.acceptance:
        started = time.monotonic()
        timed_out = False
        exit_code, stdout, stderr, timed_out = _run_shell_command(
            check.command,
            cwd=project.root,
            env=os.environ.copy(),
            timeout=check.timeout_s,
        )
        ok = not timed_out and exit_code == check.expected_exit
        if check.stdout_contains is not None and check.stdout_contains not in stdout:
            ok = False
        all_ok = all_ok and ok
        evidence["checks"].append(
            {
                "check_id": check.id,
                "command": check.command,
                "exit_code": exit_code,
                "expected_exit": check.expected_exit,
                "timed_out": timed_out,
                "stdout_contains": check.stdout_contains,
                "ok": ok,
                "duration_s": round(time.monotonic() - started, 3),
                "stdout": stdout[-MAX_CAPTURE:],
                "stderr": stderr[-MAX_CAPTURE:],
            }
        )
    mutated = _changed_files(project, before_hashes)
    if mutated:
        all_ok = False
        evidence["mutated_files"] = mutated
        cleaned: list[str] = []
        for rel in mutated:
            if rel in before_hashes:
                continue
            try:
                target = project.resolve_project_path(rel)
            except (PathSafetyError, OSError):
                continue
            if target.is_file():
                try:
                    target.unlink()
                    cleaned.append(rel)
                except OSError:
                    pass
        evidence["cleaned_files"] = cleaned
    if _hash_control_state(project) != control_before:
        all_ok = False
        evidence["state_mutated"] = True
    evidence["artifact_digest"] = _artifact_digest(project)
    evidence["plan_digest"] = _plan_digest(plan)
    evidence["status"] = "passed" if all_ok else "failed"
    evidence["finished_at"] = utc_now()
    path = project.save_evidence(task_id, check_id, evidence)
    task.evidence.append(str(path))
    task.verify_id = check_id
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
    _current_verification(project, task)
    from .model import Review

    task.review = Review(reviewer=reviewer.strip(), verdict=verdict, notes=notes)
    task.status = "reviewed" if verdict == "confirmed" else "failed"
    review_id = f"review-{uuid.uuid4().hex[:10]}"
    path = project.save_evidence(
        task_id,
        review_id,
        {
            "review_id": review_id,
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
    _current_verification(project, task)
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
