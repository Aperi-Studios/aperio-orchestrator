# Status

**Measured:** 2026-10-26, on the v2 rebuild tree.
**Rule:** this page reports what was run. It is not a roadmap and not a promise.
**Context:** `docs/REBUILD-REPORT-20261026.md` explains the rebuild and the archive.

## Verified

| Item | Result | Evidence |
|---|---|---|
| Core unit tests | 49 passed | `PYTHONPATH=src python3 -m unittest discover -s tests -v` |
| Adapter tests | 17 passed | same command; `tests/test_adapter.py` |
| Drift tests | 5 passed | same command; `tests/test_drift.py` |
| Mesh tests | 5 passed | same command; `tests/test_mesh.py` |
| Mediator tests | 6 passed | same command; `tests/test_mediator.py` |
| CLI tests | 14 passed | same command; `tests/test_cli.py` |
| Learning tests | 10 passed | same command; `tests/test_learning.py` |
| Skill tests | 8 passed | same command; `tests/test_skillgen.py` |
| Toolchain tests | 8 passed | same command; `tests/test_toolchain.py` |
| Dashboard tests | 4 passed | same command; `tests/test_dashboard.py` |
| Todo tests | 6 passed | same command; `tests/test_todo.py` |
| Readiness tests | 5 passed | same command; `tests/test_readiness.py` |
| Discovery tests | 25 passed | same command; `tests/test_discovery.py` |
| Inspection tests | 14 passed | same command; `tests/test_inspect.py` |
| Evidence tests | 6 passed | same command; `tests/test_evidence.py` |
| Audit tests | 16 passed | same command; `tests/test_audit.py` |
| Repo tests | 4 passed | same command; `tests/test_repo.py` |
| Installer tests | 23 passed | same command; `tests/test_installer.py` |
| PowerShell installer | install, launcher version, uninstall, check, update with backup, and rollback pass under `pwsh` 7.6.7 on macOS | `tests/test_installer.py::test_powershell_installer`, `test_powershell_update_check_and_rollback` |
| Total test suite | 225 passed | same command |
| CLI end-to-end | passed | `tests/test_cli.py::test_full_cli_flow` |
| Discovery core | 10 universal + 10 conditional questions persist; evidence, research requests, explicit owner waivers with review dates, and readiness survive restart | `tests/test_discovery.py`; `aperio discover status` |
| Discovery plan gate | a valid plan is refused until discovery is ready; an explicit owner waiver allows it with a warning; a plan is invalidated if discovery changes before approval or run; plan body and discovery digest are checked again at run | `tests/test_cli.py::test_plan_without_discovery_is_refused`; `tests/test_discovery.py::test_plan_is_invalidated_by_discovery_change`, `test_plan_body_tamper_after_approval_is_refused` |
| Learning plan gate | `plan`, `approve`, and `run` refuse until the dossier is ready; imported proof text is ignored and `aperio learn proof` must run a local command; stack, official source, skill/MCP, teach-back, and competency are validated; the plan records the dossier digest and refuses approval/run after it changes | `src/aperio/learning.py`; `src/aperio/model.py`; `tests/test_learning.py`; `tests/test_cli.py::test_plan_without_learning_is_refused` |
| Todo and approval gate | `plan` refuses an empty todo list and requires exactly one in-progress task, recording its `todo_id`; `run` revalidates that the linked task is in progress or accepted; a task cannot start until its predecessor is accepted or deferred; acceptance requires an approver, evidence, and the exact confirmation phrase | `src/aperio/todo.py`; `src/aperio/model.py`; `tests/test_todo.py`; `tests/test_cli.py::test_plan_without_todo_is_refused` |
| Project readiness record | Pre-flight is a hard plan gate; deployment, after-sales, design, and security facts are required for `done` and `handoff`; high/critical unresolved security risk blocks full readiness | `src/aperio/readiness.py`; `tests/test_readiness.py`; `tests/test_cli.py::test_plan_without_preflight_is_refused` |
| Plan approval binding | approval records a SHA-256 of the plan body; changing steps or allowed paths after approval is refused | `src/aperio/model.py::plan_body_digest`; `tests/test_discovery.py` |
| Read-only inspection | folder stack, tests, docs, CI, deployment, env names; URL title, meta, H1, safe canonical, security headers; private URLs, credential URLs, and symlinked inputs refused; redirects revalidated; query and fragment values redacted | `tests/test_inspect.py`; `aperio inspect` |
| Evidence manifest | file path, size, and SHA-256 recorded; contents not copied; outside paths, symlinks, hard links, secret-bearing names, and real `.env` files refused | `tests/test_evidence.py`; `aperio evidence list` |
| Security audit ledger | bounded coverage units; host brief and atomic bulk ingest; confirmed findings need boundary, severity, source line, and anchored evidence; a separate verifier records confirmed/refuted/not-reproduced evidence; `needs_validation` cannot carry severity; invalid ledgers are refused; report marks open, truncated, changed-source, unverified, contradicted, or unresolved findings incomplete | `tests/test_audit.py`; `aperio audit start`; `docs/AUDIT.md` |
| Demo project | applied, verified, reviewed, done | `examples/demo-site-plan.json` through the CLI |
| Rollback | restores modified files and removes created files | `tests/test_core.py::test_rollback_restores_modified_and_removes_created` |
| Path traversal and symlink escape | refused, including dangling symlink components | `tests/test_core.py` |
| Project state symlink | opening a project whose `.aperio` is a symlink is refused | `tests/test_core.py::test_state_symlink_is_refused` |
| State file symlink | a symlinked queue file is refused and the external file is untouched | `tests/test_core.py::test_state_file_symlink_is_refused` |
| Review tamper | a reviewer that changes the project is refused | `tests/test_adapter.py::test_reviewer_cannot_change_the_project` |
| Control-state change | a step that alters project, queue, plan, evidence, discovery, or inspection fails | `_hash_control_state`; `tests/test_discovery.py::test_run_cannot_rewrite_discovery_control_state`; `tests/test_core.py` |
| Protected-path glob | matching a protected path fails even through a glob | `tests/test_core.py::test_glob_cannot_reach_a_protected_path` |
| Non-overridable protected paths | `.git` and `.aperio` remain protected even when a policy passes an empty or custom protected-path list | `src/aperio/policy.py::PROTECTED_PATHS`; `tests/test_core.py::test_protected_paths_cannot_be_removed_by_policy` |
| Read-only step | `kind: read` runs a command and fails if the project changes; it cannot declare writes | `src/aperio/runner.py`; refusal at `src/aperio/model.py::Step.validate`; `tests/test_core.py::test_read_step_records_output_without_changes`, `test_read_step_cannot_change_the_project`, `test_read_step_shape_is_rejected_by_the_model` |
| Versioned state | every `.aperio` JSON state file carries `schema`; a missing schema is migrated on read, an unknown future schema is refused | `src/aperio/store.py::_read_state_json`; `tests/test_core.py::test_legacy_queue_schema_is_migrated`, `test_future_queue_schema_is_refused`, `test_future_project_schema_is_refused` |
| Run revalidates readiness | `run` refuses if pre-flight readiness vanished or changed after approval | `src/aperio/cli.py::cmd_run`; `tests/test_cli.py::test_run_rejects_readiness_that_vanished_after_approval` |
| Skill frontmatter integrity | generated skill descriptions are JSON-quoted and validation checks name, scope, version, and purpose against the registry | `src/aperio/skillgen.py`; `tests/test_skillgen.py::test_frontmatter_survives_quotes_and_newlines_in_purpose` |
| Queue recovery journal | every queue save is appended as a `queue.saved` event; `aperio recover` restores a missing/corrupt queue and refuses a future schema | `src/aperio/store.py::recover_queue`; `tests/test_core.py::test_queue_recovers_from_event_journal`, `test_queue_recovery_refuses_future_schema` |
| Toolchain installer | manifests declare source, version, license, scope, permissions, risk flags, cost, install argv, and verify argv; risky tools require exact owner confirmation; failed verification never records an install | `src/aperio/toolchain.py`; `tests/test_toolchain.py` |
| Resume interrupted run | `aperio resume` restores the pre-run snapshot, clears stale verification/review, and reruns the same approved plan; it refuses when no run is interrupted | `src/aperio/runner.py::resume_plan`; `tests/test_core.py::test_resume_restores_the_interrupted_snapshot_before_rerunning`, `test_resume_refuses_when_no_run_is_interrupted` |
| Optional OS sandbox | `plan.sandbox: true` wraps shell/read commands with `sandbox-exec` (macOS) or `bwrap` (Linux); a missing backend fails closed; evidence records whether isolation was active | `src/aperio/sandbox.py`; `tests/test_core.py::test_sandboxed_run_records_active_isolation`, `test_sandbox_blocks_a_write_outside_the_project`, `test_sandbox_request_without_a_backend_fails_closed` |
| Run checkpoint | every run writes a checkpoint file under `.aperio/runs/` before steps and after completion; it is outside the control-state hash | `src/aperio/runner.py::_write_checkpoint`; `tests/test_core.py::test_run_writes_a_step_checkpoint` |
| Task ID traversal | persisted task ids cannot contain path separators | `tests/test_core.py::test_task_id_traversal_is_refused` |
| Installer prefix canonicalization | `/..` resolves to `/` and is refused | `tests/test_installer.py::test_prefix_that_resolves_to_root_is_refused` |
| Host deletion | host deletions are rejected | `tests/test_adapter.py::test_host_deletion_is_rejected` |
| Undeclared shell write | detected and failed | `tests/test_core.py::test_command_outside_write_is_detected` |
| Verification timeout | cannot pass, even with `expected_exit: 124` | `tests/test_core.py::test_verification_timeout_cannot_pass` |
| Artifact binding | review and done refuse if the project changes after verification | `tests/test_core.py::test_review_refuses_a_project_changed_after_verification`; `test_finish_refuses...` |
| Review evidence | done refuses if the review evidence file is missing | `tests/test_core.py::test_finish_requires_review_evidence` |
| Installer dry-run uninstall | reports would-remove and keeps files | `tests/test_installer.py::test_dry_run_uninstall_removes_nothing` |
| Installer user-file preservation | uninstall leaves unrelated files in the skill directory | `tests/test_installer.py::test_uninstall_preserves_user_files_in_the_skill_directory` |
| Installer update/recovery | `--check`, `--update` with a bounded library backup, and `--rollback` restore; Bash and PowerShell both covered | `tests/test_installer.py::test_check_reports_version_without_writing`, `test_update_backs_up_and_rolls_back`, `test_powershell_update_check_and_rollback` |
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
| OpenCode, KiloCode, Cline, agy adapters | command shapes tested with a fake binary; live runs not yet proven | `tests/test_adapter.py::test_extra_host_adapters_build_commands` |
| Host change outside the plan | rejected before it reached the real project | `tests/test_adapter.py::test_host_change_outside_plan_is_rejected` |
| Host change outside step writes | rejected before it reached the real project | `tests/test_adapter.py::test_host_change_outside_step_writes_is_rejected` |
| Host symlink | rejected; no target content is read or copied | `tests/test_adapter.py::test_host_symlink_is_rejected` |
| Codex host adapter | real Codex built `site/index.html`; fresh Claude review confirmed; task done | task `task-116b1d078e`, run `run-d86056766a`, review `review-5fcf72b5e9` |
| Codex host review | real Codex reviewer confirmed a verified task with no findings | review `review-138f0f9a9f`, task `task-1b8dcd0ca2` |
| Fresh-context host review | real Claude reviewer saw only the brief, changed files, acceptance, and evidence; verdict confirmed | review `review-973d3a5fb8` in the temporary goldfish project |
| Self-review refusal | a host cannot review its own build | `tests/test_adapter.py::test_host_cannot_review_its_own_build` |
| Documentation drift | Docs links and inline paths resolve; repo check clean | `aperio drift`; `tests/test_drift.py` |
| Git facts | branch, short commit, dirty state, changed count, and credential-stripped origin are read-only and shown in status/handoff | `tests/test_repo.py`; `aperio status` |
| Local message store | send, read, reply, ack, filters, restart persistence; real Claude and Codex processes each used it | `tests/test_mesh.py`; `docs/HOST-PROOFS.md` |
| Mediator disposition | records CONFIRMED, REFUTED, or BLOCKED from the current task state and latest evidence | `tests/test_mediator.py`; `aperio mediate` |
| `/aperio` entry point | supplied by the installed skill | `~/.claude/skills/aperio/SKILL.md`; no duplicate command file; host load not verified |
| Skill file | installed by the installer | `~/.claude/skills/aperio/SKILL.md`; host load not verified |
| Real-home install | binary and skill present; legacy command removed; CLI runs | `bash install.sh`; `aperio --version`; `aperio doctor` |
| Static checks | ruff and shellcheck pass | `ruff check src tests`; `shellcheck install.sh` |
| Public repository | public at `https://github.com/Aperio-Studios-Private/Aperio-Orchestrator` | `gh repo view Aperio-Studios-Private/Aperio-Orchestrator --json visibility,url` |
| GitHub Actions | tests pass on Python 3.10, 3.12, and 3.14 | [tests workflow](https://github.com/Aperio-Studios-Private/Aperio-Orchestrator/actions/workflows/tests.yml) |

## Not built

- An automated vulnerability scanner or exploit runner. `aperio audit` records a bounded source review and its evidence; it does not execute target code or prove exploitability.
- Live host dispatch for OpenCode, KiloCode, Cline, and agy; their command shapes are tested, but live runs are not yet proven.
- A distributed or live two-host mesh; the current message store is local and persistent.
- A real host-to-host exchange over that store.
- CMS, media, SEO, and Astro/Lumos delivery.
- OS sandbox for host steps; shell/read steps are optionally sandboxed.
- Remote deployment.
- Native Windows execution of `aperio.cmd`; the PowerShell installer and update/rollback pass under `pwsh` on macOS.
- Full 138-field discovery module catalog and expanded read-only inspectors; the `discover` command records 10 universal and 10 conditional questions, evidence references, research requests, explicit owner waivers with review dates, readiness, and blocks `plan` until discovery is ready. The full domain catalog is not loaded.

## Known limits

- Independent Claude and adversarial subagent audits found and narrowed the boundary issues; the remaining limits are documented in `SECURITY.md`. The 225-test suite is not a whole-repository audit. Reviewer identity is a label, not a cryptographic identity. Discovery answers are recorded by the agent on the owner's behalf; owner identity is not cryptographically verified. See `docs/AUDIT-CODEX-20261026.md` and `docs/AUDIT-CLAUDE-20261026.md`.
- Host steps and shell steps are not jailed. Changes outside the plan are detected after execution.
- URL inspection rejects private and credential URLs and revalidates redirects, but DNS rebinding during host resolution is not fully prevented.
- Claude dispatch used a budget of 1.50 USD; a smaller budget was rejected by the host.
- Snapshot limits are 5,000 files and 50 MB.
- The project lock is best-effort. POSIX uses `fcntl`; Windows uses an `msvcrt` byte-lock fallback that is implemented but unverified natively.
- `aperio learn proof` executes the supplied command in the project root without an OS sandbox; use a non-destructive proof command and inspect it first.
- The learning dossier validates structure, not whether an external documentation page actually supports the claim; a human or independent reviewer must check source quality.
- The learning gate is enforced by `plan`, `approve`, and `run`; direct `apply_plan` library callers bypass it unless they check `learning.status` themselves.
- The todo gate is enforced at `plan` and `run`; `plan` records the active `todo_id`, and `run` revalidates that the linked task is in progress or accepted.
- The readiness record's pre-flight section is a hard `plan` gate, and full readiness is required by `done` and `handoff`. `run` itself does not require the deployment/after-sales sections; deployment remains a separate owner-approved action.
- Automated MCP/package installation is implemented only for declared argv manifests with verification; there is no registry discovery, GUI, or automatic trust decision.
- Host detection reports presence and version, not authentication or model access.
- The demo site is a build fixture, not a design or CMS proof.

## Next measured milestone

M2: independent multi-host review. One host builds, a different host reviews from a fresh context, and the mediator records `confirmed`, `refuted`, or `not reproduced` with evidence. Completion requires a recorded evidence file and a reproducible command, not a status paragraph.
