# Status

**Measured:** 2026-10-26, on the v2 rebuild tree.
**Rule:** this page reports what was run. It is not a roadmap and not a promise.

## Verified

| Item | Result | Evidence |
|---|---|---|
| Core unit tests | 17 passed | `PYTHONPATH=src python3 -m unittest discover -s tests -v` |
| Installer tests | 3 passed | same command; `tests/test_installer.py` |
| Total test suite | 20 passed | same command |
| CLI end-to-end | passed | `tests/test_cli.py::test_full_cli_flow` |
| Demo project | applied, verified, reviewed, done | `examples/demo-site-plan.json` through the CLI |
| Rollback | restores modified files and removes created files | `tests/test_core.py::test_rollback_restores_modified_and_removes_created` |
| Path traversal and symlink escape | refused | `tests/test_core.py` |
| Undeclared shell write | detected and failed | `tests/test_core.py::test_command_outside_write_is_detected` |
| Installer dry run | no files written | `tests/test_installer.py::test_dry_run_writes_nothing` |
| Installer idempotency | second run leaves one skill | `tests/test_installer.py::test_install_is_idempotent_and_uninstalls` |
| Installer uninstall | removes binary, library, and skill | same test |
| Host detection | reads installed host names and versions | `aperio hosts`; presence is not permission |

## Not built

- Dispatch to a coding host.
- Live mesh chat and mediator comparison.
- CMS, media, SEO, or Astro/Lumos delivery.
- Web dashboard.
- OS sandbox for shell steps.
- Remote deployment.
- Windows installer parity.

## Known limits

- Shell steps are not jailed. Changes outside the plan are detected after execution.
- Snapshot limits are 5,000 files and 50 MB.
- The project lock is best-effort and a no-op where `fcntl` is unavailable.
- Host detection reports presence and version, not authentication or model access.
- The demo site is a build fixture, not a design or CMS proof.

## Next measured milestone

M1: one real host adapter that accepts a plan and returns a bounded patch, followed by a different reviewer. Completion requires a recorded evidence file and a reproducible command, not a status paragraph.
