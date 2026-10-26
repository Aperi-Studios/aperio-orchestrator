# Changelog

## 2.0.0.dev0 - 2026-10-26

Initial clean rebuild.

- Added a standard-library core for asks, plans, approval, bounded apply, verification, independent review, finish, rollback, and handoff.
- Added path safety for relative paths, parent traversal, and symlink components.
- Added declared-write enforcement for shell steps. Undeclared changes are recorded as violations.
- Added a JSON project state under `.aperio/` with atomic writes and append-only asks and events.
- Added a read-only host detector.
- Added a shell installer with dry run, idempotent reinstall, skill installation, and uninstall.
- Added unit, CLI, and installer tests.
- Added a runnable demo plan that creates and verifies a static page.
- Replaced the old documentation set with one PRD, one architecture document, one status page, one roadmap, one testing guide, one agent protocol, and one decision log.

### Known limits

- Shell steps are not OS-sandboxed; undeclared writes are detected after execution, not jailed.
- Host adapters are implemented for Claude, Codex, Goose, and dsh; Claude and Codex are live-proven, Goose/dsh live calls were blocked, and the extra adapters are command-shape tested only.
- The local message store and mediator are implemented; a distributed two-host transport is not built.
- CMS, SEO, and deployment are not implemented.
- The PowerShell installer is implemented and tested under `pwsh` on macOS; native Windows `.cmd` execution is not tested.
