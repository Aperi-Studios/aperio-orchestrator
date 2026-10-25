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

The current test count is 55. The code and tests were changed after the audit;
a second external pass is still required.
