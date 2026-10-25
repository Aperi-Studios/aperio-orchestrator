# Status

**Measured:** 2026-10-26, on the v2 rebuild tree.
**Rule:** this page reports what was run. It is not a roadmap and not a promise.
**Context:** `docs/REBUILD-REPORT-20261026.md` explains the rebuild and the archive.

## Verified

| Item | Result | Evidence |
|---|---|---|
| Core unit tests | 17 passed | `PYTHONPATH=src python3 -m unittest discover -s tests -v` |
| Adapter tests | 6 passed | same command; `tests/test_adapter.py` |
| CLI tests | 4 passed | same command; `tests/test_cli.py` |
| Installer tests | 4 passed | same command; `tests/test_installer.py` |
| Total test suite | 31 passed | same command |
| CLI end-to-end | passed | `tests/test_cli.py::test_full_cli_flow` |
| Demo project | applied, verified, reviewed, done | `examples/demo-site-plan.json` through the CLI |
| Rollback | restores modified files and removes created files | `tests/test_core.py::test_rollback_restores_modified_and_removes_created` |
| Path traversal and symlink escape | refused | `tests/test_core.py` |
| Undeclared shell write | detected and failed | `tests/test_core.py::test_command_outside_write_is_detected` |
| Installer dry run | no files written | `tests/test_installer.py::test_dry_run_writes_nothing` |
| Installer idempotency | second run leaves one skill | `tests/test_installer.py::test_install_is_idempotent_and_uninstalls` |
| Installer uninstall | removes binary, library, and skill | same test |
| Host detection | reads installed host names and versions | `aperio hosts`; presence is not permission |
| Claude host adapter | real host produced `site/index.html` in a disposable copy; acceptance passed; review and done completed | real-host proof 3, `run-2d57f0f091`; evidence held in the temporary project |
| Goose host adapter | command path tested with a fake binary; live Goose call failed with HTTP 500 from the local bridge | `tests/test_adapter.py::test_goose_adapter_builds_a_run_command`; live probe output |
| Host change outside the plan | rejected before it reached the real project | `tests/test_adapter.py::test_host_change_outside_plan_is_rejected` |
| `/aperio` command file | installed by the installer | `~/.claude/commands/aperio.md`; host load not verified |
| Skill file | installed by the installer | `~/.claude/skills/aperio/SKILL.md`; host load not verified |
| Real-home install | binary, skill, and command present; CLI runs | `bash install.sh`; `aperio --version`; `aperio doctor` |
| Static checks | ruff and shellcheck pass | `ruff check src tests`; `shellcheck install.sh` |
| Public repository | public at `https://github.com/Aperi-Studios/aperio-orchestrator` | `gh repo view Aperi-Studios/aperio-orchestrator --json visibility,url` |
| GitHub Actions | tests pass on Python 3.10, 3.12, and 3.14 | [tests workflow](https://github.com/Aperi-Studios/aperio-orchestrator/actions/workflows/tests.yml) |

## Not built

- Dispatch to hosts beyond the Claude and Goose adapters.
- Live mesh chat and multi-host mediator comparison.
- CMS, media, SEO, or Astro/Lumos delivery.
- Web dashboard.
- OS sandbox for host or shell steps.
- Remote deployment.
- Windows installer parity.

## Known limits

- An external audit by another host is pending. The 31-test suite is the builder's verification, not an independent review of the whole repository.
- Host steps and shell steps are not jailed. Changes outside the plan are detected after execution.
- Claude dispatch used a budget of 1.50 USD; a smaller budget was rejected by the host.
- Snapshot limits are 5,000 files and 50 MB.
- The project lock is best-effort and a no-op where `fcntl` is unavailable.
- Host detection reports presence and version, not authentication or model access.
- The demo site is a build fixture, not a design or CMS proof.

## Next measured milestone

M2: independent multi-host review. One host builds, a different host reviews from a fresh context, and the mediator records `confirmed`, `refuted`, or `not reproduced` with evidence. Completion requires a recorded evidence file and a reproducible command, not a status paragraph.
