# External audit: Codex, 2026-10-26

A fresh Codex process with a read-only sandbox audited a clean clone of the
public repository. It was told not to trust the README, `docs/STATUS.md`, or
`docs/PRD.md`, and not to edit files. Its verdict was `confirmed`: the source
contained boundary and evidence-gate issues.

This file records the findings and what happened to each one. The audit is not a
substitute for the owner's approval.

## Findings and disposition

| Severity | Finding | Disposition |
|---|---|---|
| P1 | Host adapter followed symlinks when reading changed files, so a host could copy an external file through an allowed-path symlink. | **Fixed.** The adapter rejects a changed path if it was a symlink before or is a symlink after, and never reads it. Test: `test_host_symlink_is_rejected`. |
| P1 | Host changes outside a step's `writes` but inside the plan's allowed paths were applied before the post-run check, and the extra file could persist. | **Fixed.** The adapter requires each host change to match that step's declared writes; a mismatch fails before any change is applied. Test: `test_host_change_outside_step_writes_is_rejected`. |
| P1 | A timed-out acceptance check could pass when `expected_exit` was `124`. | **Fixed.** A timeout always fails the check and is recorded as `timed_out`. Test: `test_verification_timeout_cannot_pass`. |
| P1 | Acceptance commands could mutate project files while verification passed; shell steps can make side effects outside the scanned tree. | **Partly fixed and partly documented.** Verification now hashes the project before and after acceptance and fails on any mutation (`test_acceptance_check_cannot_mutate_the_project`). Shell steps are still not an OS sandbox; writes outside the scanned project or in excluded directories are not observed. This is stated in `SECURITY.md`. |
| P2 | Approver and reviewer identities are self-reported labels, not authenticated identities. | **Accepted and documented.** The builder/reviewer label check prevents an obvious self-review; it is not identity proof. |
| P2 | Security claims exceeded the implemented checks. | **Fixed.** `SECURITY.md` now separates lexical path checks, host change checks, acceptance mutation checks, and the limits of shell and identity checks. |

## What the audit did not test

- It did not run the tests or the installer.
- It did not reproduce an exploit.
- It did not test native Windows execution.

## What changed after the audit

- `src/aperio/adapter.py`: step-write matching and symlink rejection.
- `src/aperio/policy.py`: `step_allows`.
- `src/aperio/runner.py`: timeout cannot pass; acceptance mutation fails.
- `tests/test_adapter.py`, `tests/test_core.py`: four regression tests.
- `SECURITY.md`, `docs/ARCHITECTURE.md`: narrower, accurate boundaries.

## Second pass

A second fresh Codex audit on HEAD `b2c5bd4` returned **refuted** with no P0 and
these additional findings:

| Severity | Finding | Disposition |
|---|---|---|
| P1 | A dangling symlink passed the component check because it required `exists()` first. | **Fixed.** `resolve_inside` rejects a symlink component even when its target is missing; `test_dangling_symlink_component_is_refused`. |
| P1 | A project with a `.aperio` symlink could read and write state outside the project root. | **Fixed.** `Project` rejects a symlink state directory and verifies that existing state resolves inside the root; `test_state_symlink_is_refused`. |
| P1 | A host could bypass the per-step check by writing directly to the original project. | **Detected and failed.** The runner hashes the real project before and after the host step and fails on any delta. The OS still does not prevent the write; this remains a documented no-sandbox limit. |
| P1 | Shell commands or acceptance checks could alter Aperio state without detection. | **Fixed for control state.** Runs and verification hash the project metadata, queue, plans, and evidence; a change fails the step. Writes outside the project and excluded directories remain unscanned. |
| P2 | The mediator could select an older passing record by filename instead of the current task state. | **Fixed.** It uses `task.run_id`, requires the current run, and takes the latest evidence by timestamp; a later failed verification yields `REFUTED`. |
| P2 | Acceptance mutations were reported but not cleaned. | **Partly fixed.** Newly created files are removed; modified or deleted files are reported but not restored. |
| P2 | Security docs overstated mutation detection. | **Fixed.** `SECURITY.md` states the scanner's exclusions and the state limits. |

The current test count is 60. A third independent pass is still required after
these changes.

## Third pass

A third fresh Codex audit on HEAD `cd927b8` found no P0 and returned **refuted**
with these remaining issues:

| Severity | Finding | Disposition |
|---|---|---|
| P1 | State files such as the queue could be symlinks, and the atomic writer followed them. | **Fixed.** State reads, writes, and appends reject symlinks; `replace_bytes_atomic` refuses a symlink target. Test: `test_state_file_symlink_is_refused`. |
| P1 | A direct host write to the original project could remain after the failed run. | **Partly fixed.** The runner restores snapshot targets on a host delta; files outside the snapshot are still not restored. The no-sandbox limit remains. |
| P1 | A review host could change the project and still confirm it. | **Fixed for detection.** The review runner fingerprints the whole project before and after and refuses a verdict on any change. Goose still has no OS read-only sandbox; the change is detected, not prevented. Test: `test_reviewer_cannot_change_the_project`. |
| P1 | An old review could confirm a later run. | **Fixed.** A new run or a new verification clears the previous review before proceeding. |
| P2 | Control-state hashing omitted asks and events. | **Fixed.** Both are included. |
| P2 | Acceptance mutation cleanup was partial. | **Documented and partly fixed.** Newly created files are removed; modified or deleted files are reported but not restored. |
| P2 | A timed-out shell's descendants could outlive the timeout. | **Not fixed.** The runner does not manage a process group. This is a known limit. |

The fourth pass follows. The known limits are recorded in `SECURITY.md` and
`docs/STATUS.md`.

## Fourth pass

A fourth fresh Codex audit on HEAD `c15e39f` found no P0 and returned
**confirmed** for remaining paths to external writes, stale-evidence
completion, reviewer/host mutation, and overclaimed detection. It also found a
nested state-symlink path and a timeout descendant risk.

| Severity | Finding | Disposition |
|---|---|---|
| P1 | State subdirectories and files could be symlinks, redirecting backups, mesh, mediations, or handoffs. | **Fixed.** Opening a project rejects a symlink anywhere in state except the disposable `dispatch` and `reviews` workspaces; state reads, writes, and appends also reject symlinks. |
| P1 | A task could finish on stale verification or missing evidence. | **Fixed.** Verification records an artifact digest and `task.verify_id`; manual review and `done` refuse if the digest no longer matches. A new run or verification clears the old review. |
| P1 | A review host could change the project and the change remained. | **Detected, not restored.** The review runner fingerprints before/after and refuses the verdict; a detected edit remains. This is now stated as a limit. |
| P1 | Timeouts did not stop descendants. | **Fixed for process groups.** Shell steps run in a new session and a timeout kills the group; a process that detaches itself can still outlive the runner. |
| P1 | Shell writes outside the project are not detected. | **Documented, not fixed.** This is inherent without an OS sandbox and is now stated accurately in `src/aperio/policy.py` and `SECURITY.md`. |
| P2 | Control-state hashing omitted asks and events. | **Fixed.** Both are included. |
| P2 | Manual reviewer identity is self-reported. | **Documented.** The check prevents an equal label, not an impersonated person. |

The test count is 64. A fifth independent pass found the following.

## Fifth pass

A fifth fresh Codex audit on HEAD `04cb80f` found no P0 and returned **confirmed**
for these remaining P1s:

| Severity | Finding | Disposition |
|---|---|---|
| P1 | A changed plan could reuse a stale verification digest because the plan lives under `.aperio`. | **Fixed.** Verification records a plan digest; review and `done` compare the current plan. Test: `test_review_refuses_a_plan_changed_after_verification`. |
| P1 | The `dispatch` or `reviews` directory itself could be a symlink. | **Fixed.** Only symlinks *inside* those disposable workspaces are ignored; the directory entries themselves are rejected. |
| P1 | Changes under excluded project directories (`.git`, `node_modules`) evade the scan. | **Documented, not fixed.** `SECURITY.md` states that excluded directories are not observed. |
| P1 | Host and reviewer timeouts did not kill descendants. | **Fixed on POSIX** with a new process group. Windows still kills only the direct process; documented. |
| P2 | Control-state hashing omitted rollback/dispatch state. | **Partly fixed.** The critical control files are hashed; disposable workspace state is not. |

Remaining known limits: no OS sandbox, changes in excluded or outside-project
paths are not observed, a reviewer's detected edit is not restored, a modified
file changed by an acceptance check is not restored, and Windows process
cleanup is direct-process only.

## Sixth pass

A sixth fresh Codex audit on HEAD `465c0d7` found no P0 and these additional
issues:

| Severity | Finding | Disposition |
|---|---|---|
| P1 | A glob pattern could pass the protected-path text check and expand to `.git`. | **Fixed.** Every glob expansion is rechecked with `assert_writable`; test `test_glob_cannot_reach_a_protected_path`. |
| P1 | The Bash installer checked `/..` before resolving it to `/`. | **Fixed.** The prefix is canonicalized with `realpath` and checked again; test `test_prefix_that_resolves_to_root_is_refused`. |
| P2 | Host deletion was accepted even though the prompt says not to delete. | **Fixed.** Host deletions are rejected. |
| P2 | A crafted task id could traverse into evidence or mediation paths. | **Fixed.** Persisted task ids are validated; test `test_task_id_traversal_is_refused`. |
| P2 | Mediation did not compare the plan digest. | **Fixed.** It compares artifact and plan digests. |
| P2 | Host review could record a stale verification. | **Fixed.** It compares the current artifact and plan digests before running. |
| P2 | The PowerShell installer overwrote an existing command file. | **Fixed.** It now refuses unless the file is an Aperio v2 command. |

Test count: 70. A final static pass and the owner's approval are still required.

## Seventh pass

A seventh fresh Codex audit on HEAD `3b9b9f7` found no P0 and two P1s:

| Severity | Finding | Disposition |
|---|---|---|
| P1 | `done` could succeed after the review evidence file was deleted because it trusted the task's review fields. | **Fixed.** `done` now requires a matching review evidence record; test `test_finish_requires_review_evidence`. |
| P1 | Dry-run uninstall printed "removed" even though nothing was removed. | **Fixed in Bash and PowerShell.** Dry-run prints would-remove and leaves files; test `test_dry_run_uninstall_removes_nothing`. |

Test count: 70. The owner's approval and Claude's independent audit remain pending.


