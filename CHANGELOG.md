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

- Shell steps are not OS-sandboxed.
- Host dispatch is not implemented.
- Mesh chat, CMS, SEO, and deployment are not implemented.
- Windows installer parity is not implemented.
