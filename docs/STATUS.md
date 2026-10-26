# Status

**Measured:** 2026-10-26, on the v2 rebuild tree.
**Rule:** this page reports what was run. It is not a roadmap and not a promise.
**Context:** `docs/REBUILD-REPORT-20261026.md` explains the rebuild and the archive.

## Verified

| Item | Result | Evidence |
|---|---|---|
| Core unit tests | 30 passed | `PYTHONPATH=src python3 -m unittest discover -s tests -v` |
| Adapter tests | 16 passed | same command; `tests/test_adapter.py` |
| Drift tests | 5 passed | same command; `tests/test_drift.py` |
| Mesh tests | 5 passed | same command; `tests/test_mesh.py` |
| Mediator tests | 5 passed | same command; `tests/test_mediator.py` |
| CLI tests | 4 passed | same command; `tests/test_cli.py` |
| Installer tests | 10 passed | same command; `tests/test_installer.py` |
| PowerShell installer | install, launcher version, and uninstall pass under `pwsh` 7.6.7 on macOS | `tests/test_installer.py::test_powershell_installer` |
| Total test suite | 75 passed | same command |
| CLI end-to-end | passed | `tests/test_cli.py::test_full_cli_flow` |
| Demo project | applied, verified, reviewed, done | `examples/demo-site-plan.json` through the CLI |
| Rollback | restores modified files and removes created files | `tests/test_core.py::test_rollback_restores_modified_and_removes_created` |
| Path traversal and symlink escape | refused, including dangling symlink components | `tests/test_core.py` |
| Project state symlink | opening a project whose `.aperio` is a symlink is refused | `tests/test_core.py::test_state_symlink_is_refused` |
| State file symlink | a symlinked queue file is refused and the external file is untouched | `tests/test_core.py::test_state_file_symlink_is_refused` |
| Review tamper | a reviewer that changes the project is refused | `tests/test_adapter.py::test_reviewer_cannot_change_the_project` |
| Control-state change | a step that alters project, queue, plan, or evidence fails | `_hash_control_state`; `tests/test_core.py` |
| Protected-path glob | matching a protected path fails even through a glob | `tests/test_core.py::test_glob_cannot_reach_a_protected_path` |
| Task ID traversal | persisted task ids cannot contain path separators | `tests/test_core.py::test_task_id_traversal_is_refused` |
| Installer prefix canonicalization | `/..` resolves to `/` and is refused | `tests/test_installer.py::test_prefix_that_resolves_to_root_is_refused` |
| Host deletion | host deletions are rejected | `tests/test_adapter.py::test_host_deletion_is_rejected` |
| Undeclared shell write | detected and failed | `tests/test_core.py::test_command_outside_write_is_detected` |
| Verification timeout | cannot pass, even with `expected_exit: 124` | `tests/test_core.py::test_verification_timeout_cannot_pass` |
| Artifact binding | review and done refuse if the project changes after verification | `tests/test_core.py::test_review_refuses_a_project_changed_after_verification`; `test_finish_refuses...` |
| Review evidence | done refuses if the review evidence file is missing | `tests/test_core.py::test_finish_requires_review_evidence` |
| Installer dry-run uninstall | reports would-remove and keeps files | `tests/test_installer.py::test_dry_run_uninstall_removes_nothing` |
| Installer user-file preservation | uninstall leaves unrelated files in the skill directory | `tests/test_installer.py::test_uninstall_preserves_user_files_in_the_skill_directory` |
| Self-approval | the approver cannot also be the run actor | `tests/test_core.py::test_approver_cannot_be_the_run_actor` |
| No-op acceptance | `true` and `exit 0` are refused as acceptance checks | `tests/test_core.py::test_noop_acceptance_is_refused` |
| Acceptance mutation | a check that changes a project file fails verification | `tests/test_core.py::test_acceptance_check_cannot_mutate_the_project` |
| Installer dry run | no files written | `tests/test_installer.py::test_dry_run_writes_nothing` |
| Installer idempotency | second run leaves one skill | `tests/test_installer.py::test_install_is_idempotent_and_uninstalls` |
| Installer paths with spaces | install and launcher version pass | `tests/test_installer.py::test_prefix_with_spaces` |
| Installer uninstall | removes binary, library, and skill | same test |
| Host detection | reads installed host names and versions | `aperio hosts`; presence is not permission |
| Claude host adapter | real host produced `site/index.html` in a disposable copy; acceptance passed; review and done completed on current code | task `task-17fd7a83a6`, run `run-d8e491aeb4`, review `review-5cb1b3585d`; earlier run `run-2d57f0f091` |
| Goose host adapter | command path tested with a fake binary; live Goose call failed with HTTP 500 from the local bridge | `tests/test_adapter.py::test_goose_adapter_builds_a_run_command`; live probe output |
| dsh host adapter | command path tested with a fake binary; live dsh blocked by missing `RIVER_API_KEY` | `tests/test_adapter.py::test_dsh_adapter_builds_a_headless_command`; live probe output |
| Host change outside the plan | rejected before it reached the real project | `tests/test_adapter.py::test_host_change_outside_plan_is_rejected` |
| Host change outside step writes | rejected before it reached the real project | `tests/test_adapter.py::test_host_change_outside_step_writes_is_rejected` |
| Host symlink | rejected; no target content is read or copied | `tests/test_adapter.py::test_host_symlink_is_rejected` |
| Codex host adapter | real Codex built `site/index.html`; fresh Claude review confirmed; task done | task `task-116b1d078e`, run `run-d86056766a`, review `review-5fcf72b5e9` |
| Codex host review | real Codex reviewer confirmed a verified task with no findings | review `review-138f0f9a9f`, task `task-1b8dcd0ca2` |
| Fresh-context host review | real Claude reviewer saw only the brief, changed files, acceptance, and evidence; verdict confirmed | review `review-973d3a5fb8` in the temporary goldfish project |
| Self-review refusal | a host cannot review its own build | `tests/test_adapter.py::test_host_cannot_review_its_own_build` |
| Documentation drift | Docs links and inline paths resolve; repo check clean | `aperio drift`; `tests/test_drift.py` |
| Local message store | send, read, reply, ack, filters, restart persistence; real Claude and Codex processes each used it | `tests/test_mesh.py`; `docs/HOST-PROOFS.md` |
| Mediator disposition | records CONFIRMED, REFUTED, or BLOCKED from the current task state and latest evidence | `tests/test_mediator.py`; `aperio mediate` |
| `/aperio` command file | installed by the installer | `~/.claude/commands/aperio.md`; host load not verified |
| Skill file | installed by the installer | `~/.claude/skills/aperio/SKILL.md`; host load not verified |
| Real-home install | binary, skill, and command present; CLI runs | `bash install.sh`; `aperio --version`; `aperio doctor` |
| Static checks | ruff and shellcheck pass | `ruff check src tests`; `shellcheck install.sh` |
| Public repository | public at `https://github.com/Aperio-Studios-Private/Aperio-Orchestrator` | `gh repo view Aperio-Studios-Private/Aperio-Orchestrator --json visibility,url` |
| GitHub Actions | tests pass on Python 3.10, 3.12, and 3.14 | [tests workflow](https://github.com/Aperio-Studios-Private/Aperio-Orchestrator/actions/workflows/tests.yml) |

## Not built

- Dispatch to hosts beyond the Claude, Codex, dsh, and Goose adapters.
- A distributed or live two-host mesh; the current message store is local and persistent.
- A real host-to-host exchange over that store.
- CMS, media, SEO, and Astro/Lumos delivery.
- Web dashboard.
- OS sandbox for host or shell steps.
- Remote deployment.
- Native Windows execution of `aperio.cmd`; the PowerShell installer passes under `pwsh` on macOS.

## Known limits

- Seven external Codex passes and one Claude audit found and narrowed the boundary issues; the remaining limits are documented in `SECURITY.md`. The 74-test suite is not a whole-repository audit. Claude's F1, F3, F4, and F5 are fixed; F2 (reviewer identity is a label) remains documented, not solved. See `docs/AUDIT-CODEX-20261026.md` and `docs/AUDIT-CLAUDE-20261026.md`.
- Host steps and shell steps are not jailed. Changes outside the plan are detected after execution.
- Claude dispatch used a budget of 1.50 USD; a smaller budget was rejected by the host.
- Snapshot limits are 5,000 files and 50 MB.
- The project lock is best-effort and a no-op where `fcntl` is unavailable.
- Host detection reports presence and version, not authentication or model access.
- The demo site is a build fixture, not a design or CMS proof.

## Next measured milestone

M2: independent multi-host review. One host builds, a different host reviews from a fresh context, and the mediator records `confirmed`, `refuted`, or `not reproduced` with evidence. Completion requires a recorded evidence file and a reproducible command, not a status paragraph.
