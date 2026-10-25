"""Path safety helpers shared by the store, runner, and installer-facing tools."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
import hashlib
import os


class PathSafetyError(ValueError):
    """A path escaped the project, used a symlink, or was otherwise unsafe."""


def normalize_rel(value: str) -> str:
    """Normalize a project-relative POSIX path and reject escapes."""
    if not isinstance(value, str) or not value.strip():
        raise PathSafetyError("path must be a non-empty string")
    if "\x00" in value:
        raise PathSafetyError("path contains a NUL byte")
    if value.startswith(("/", "\\")):
        raise PathSafetyError(f"absolute path is not allowed: {value}")
    if len(value) >= 2 and value[1] == ":":
        raise PathSafetyError(f"drive-qualified path is not allowed: {value}")
    raw = value.replace("\\", "/")
    parts = [p for p in PurePosixPath(raw).parts if p not in ("", ".")]
    if not parts:
        raise PathSafetyError("path resolves to the project root")
    if any(p == ".." for p in parts):
        raise PathSafetyError(f"parent traversal is not allowed: {value}")
    return "/".join(parts)


def resolve_inside(root: Path, rel: str, *, create_parents: bool = False, allow_root: bool = False) -> Path:
    """Resolve a relative path and prove it stays inside root.

    Symlinked components are rejected. This is a path policy, not an OS sandbox;
    commands that choose their own paths can still escape unless the runner
    detects the resulting file changes.
    """
    root = root.resolve()
    if allow_root and rel in ("", "."):
        return root
    normalized = normalize_rel(rel)
    candidate = (root / normalized).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PathSafetyError(f"path escapes project: {rel}") from exc

    current = root
    for part in normalized.split("/"):
        current = current / part
        if current.exists() and current.is_symlink():
            raise PathSafetyError(f"symlink component is not allowed: {rel}")
    if create_parents:
        (root / normalized).parent.mkdir(parents=True, exist_ok=True)
    return candidate


def is_inside(root: Path, path: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve())
        return True
    except ValueError:
        return False


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_posix(root: Path, path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise PathSafetyError(f"path is outside project: {path}") from exc


def replace_text_atomic(path: Path, text: str, *, newline: str = "\n") -> None:
    """Write text through a temporary file in the same directory, then replace."""
    path = path.resolve(strict=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile_in_dir(path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline=newline) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def tempfile_in_dir(directory: Path) -> tuple[int, str]:
    import tempfile

    fd, name = tempfile.mkstemp(prefix=".aperio-tmp-", dir=str(directory))
    return fd, name
