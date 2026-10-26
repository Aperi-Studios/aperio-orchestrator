# Audit — Aperio-Orchestrator v2

**Auditor:** Claude (main working tree), assigned by Hermes, mediator
**Date:** 2026-10-26
**Audit pin:** `ad36105`; retained as a historical external audit.
**Current disposition:** F1, F3, F4, and F5 are fixed. F2 is a documented trust
limit: a local label cannot authenticate a second person. See `docs/STATUS.md`.
**Target:** `/Users/maryamahad/Desktop/Aperio-Orchestrator-v2`
**Mode:** read-only. Nothing in the v2 tree was edited. Every reproduction ran in
a copy under `$TMPDIR`.

---

## Summary

The v2 core loop is small, readable, and mostly well-built. Path safety, rollback,
and the write-boundary checks are genuinely good, and the documentation is
unusually honest about its own limits — the shell-is-not-a-sandbox limitation is
stated in four places, so I am **not** reporting it as a defect.

**Three confirmed defects.** Two are in the trust model, one is data loss in the
installer. The trust-model pair matters most: the loop's central claim is that a
builder cannot finish its own work, and I reproduced that claim failing three
different ways.

---

## Findings

| Finding | Severity | Evidence | Expected | Actual | Proposed fix |
|---|---|---|---|---|---|
| **F1 — A plan can be approved by the agent that wrote it, with no error** | **HIGH** | `src/aperio/runner.py:235-238` | The check should reject or at least record a self-approval | The condition is computed and then `pass` — a no-op. Reproduced: `approved_by: agent, actor: agent`, status `applied` | Make it raise, or record `self_approved: true` in the evidence and require a second approver before `run` |
| **F2 — The reviewer is a free-text string; one process can run the whole loop** | **HIGH** | `src/aperio/policy.py:95-99`, `runner.py:438` | "a solo agent cannot finish a task alone" (`docs/DECISIONS.md:41`) | Reproduced end-to-end through the real CLI: one agent approved, ran, verified, reviewed as `qa-bot`, and finished. Status `done` | Bind the reviewer to an identity the process cannot self-assert (a host/session token), or require the review evidence to come from a different `actor` recorded on the run |
| **F3 — `--uninstall` deletes user files inside the skill directory** | **MEDIUM** | `install.sh:87-90` | Remove only what the installer wrote | `rm -rf ~/.claude/skills/aperio` removes the whole directory. Reproduced: a user's `my-notes.md` was destroyed | Remove only the files named in the manifest (`SKILL.md`, `VERSION`, the marker), then `rmdir` if empty |
| **F4 — Acceptance commands are unvalidated, so `true` passes verification** | **MEDIUM** | `src/aperio/policy.py` (no acceptance validation), `runner.py:381-404` | A plan's checks should prove the work | Reproduced: a plan with `"command": "true"` verified `passed` and reached `done` | Validate acceptance at plan time (reject no-op commands), or require at least one check that reads a file the plan wrote |
| **F5 — `install.sh` overwrites an existing `SKILL.md` with no backup or warning** | **LOW** | `install.sh:122` | Preserve or warn | `cp` overwrites silently. Reproduced: the pre-existing `SKILL.md` was replaced | Refuse if the target exists and carries no v2 marker, as the script already does for `COMMAND_FILE` at `:52-56` |

---

## CONFIRMED (reproduced in this session)

**F1 — self-approval is a no-op.**

```
$ python3 - <<'PY'   # in a copy of the tree
plan = Plan(..., builder="agent", approval=Approval(approved_by="agent"))
ev = apply_plan(p, plan, actor="agent")
PY
status: applied
approved_by: agent | actor: agent
-> a plan the agent approved FOR ITSELF was APPLIED
```

`runner.py:235-238` reads:

```python
if plan.approval.approved_by.strip().lower() == actor.strip().lower():
    # An owner may also be the actor in a tiny project; record it rather than
    # pretending it is independent review. Verification still needs a reviewer.
    pass
```

The comment says "record it" — nothing is recorded. The condition is evaluated
and discarded.

**F2 — the whole loop, end to end, through the real CLI.**

```
$ aperio approve plan-f2b291f4c1 --by agent --confirm "I approve this plan"
plan-f2b291f4c1  approved by agent

$ aperio run task-86060951e5
run-ee1366bfe9  applied

$ aperio verify task-86060951e5
verify-1fa6661fc4  passed

$ aperio review task-86060951e5 --reviewer qa-bot --verdict confirmed
task-86060951e5  review confirmed by qa-bot

$ aperio done task-86060951e5
task-86060951e5  done
```

One process, five commands, no second party. `--by` defaults to `$USER`
(`cli.py:253`) and `--reviewer` accepts any string. `assert_reviewer`
(`policy.py:95-99`) is a correct case-insensitive string comparison — it does
exactly what it says, and what it says is not enough.

**F3 — uninstall destroys user data.**

```
before: SKILL.md  my-notes.md
$ HOME=... bash install.sh --prefix ... --uninstall
removed .../.claude/skills/aperio
after:  DIRECTORY GONE
```

**F4 — `true` passes as an acceptance check.**

```
steps=[Step(kind="write", path="out/a.txt", content="")],   # writes nothing useful
acceptance=[Acceptance(command="true", expected_exit=0)],
-> verification: passed | task: done
```

**F5 — silent overwrite.** Reproduced: a pre-existing `SKILL.md` in the skill
directory was replaced with no backup. Note the installer *does* guard
`COMMAND_FILE` this way (`install.sh:52-56`) — the skill file just lacks the
same guard.

---

## NOT REPRODUCED

- **Shell steps writing outside the project.** I confirmed a `run` step can write
  outside the project root and the run still reports `applied` with no
  violation. **This is not a defect** — it is disclosed in four places
  (`policy.py:3`, `docs/ARCHITECTURE.md:86`, `README.md:95`,
  `docs/DECISIONS.md:29`), and `verify` refuses a run whose last evidence is not
  `applied`-clean. The docs claim "the task is not verified", which holds.
- **Path traversal, symlink components, absolute paths, protected paths.** All
  four refused, and the tests for them assert real behaviour
  (`test_core.py:122-168`).
- **Rollback.** Restores a modified file to its original bytes and removes a
  created one. Verified directly.
- **`review` refusing the builder as reviewer.** It does refuse
  (`test_core.py:111-120`). The gap is F2's identity, not this check.

---

## NO FINDING (checked, nothing wrong)

- `paths.py` — `normalize_rel` and `resolve_inside` are careful and correct: NUL,
  absolute, drive-qualified, `..`, and symlink components are all rejected.
- `store.py` locking, atomic writes, append-only asks.
- `runner.py` snapshot limits (`MAX_SNAPSHOT_FILES`, `MAX_SNAPSHOT_BYTES`) and the
  changed-file detection, which caught an undeclared in-project write.
- The 31-test suite passes, and the tests I sampled assert the behaviour they
  name — `test_unapproved_plan_never_writes` checks both the exception **and**
  that no file appeared.
- `install.sh` refuses `/`, `.`, and empty prefixes, and refuses to overwrite a
  foreign `aperio.md`.

---

## One test that asserts the data loss

`tests/test_installer.py:97-101` asserts that after `--uninstall` the skill
directory is gone. That is correct for a directory the installer owns, and it is
why the suite cannot see F3: the test never places a user file there. A test that
planted `my-notes.md` first would fail today.

---

## Verdict

**The core loop is sound in its mechanics and unsound in its trust model.**

Approval, verification, and review are all *enforced as procedures* and all
*bypassable as identities*. A single agent can complete a task the design says
requires two parties, and the documentation states the opposite in plain words.
That is the gap I would fix first: F1 and F2 are one change — make the approver
and the reviewer identities the process cannot self-assert, and make the
self-approval branch raise instead of `pass`.

F3 and F4 are smaller and independent. F3 is a five-line fix in `install.sh`.

*Every command above was run in a copy of the tree under `$TMPDIR`. The v2 tree
was not modified.*

---

## Audit pin — the tree moved while I worked

I audited **`ad36105`** ("feat: add bounded Claude and Goose host dispatch with
evidence"). While I was writing this report, Hermes began editing the v2 tree:
`README.md`, `docs/*.md`, `src/aperio/adapter.py`, `src/aperio/cli.py`,
`tests/test_adapter.py`, `skill/aperio/SKILL.md` and `commands/aperio.md` all
changed between 04:31 and 04:32.

**None of the files I read for these findings are in that diff** — `paths.py`,
`runner.py`, `policy.py`, `store.py`, `install.sh` and `tests/test_core.py` are
untouched, so F1–F5 stand against the current tree. But `adapter.py` and
`cli.py` are being changed, and I did not re-audit them.

I made **no writes** to the v2 tree. Every reproduction ran in a copy under
`$TMPDIR`.

## Current dispositions

| Finding | Current state |
|---|---|
| F1 — self-approval no-op | **Fixed.** `apply_plan` raises when the approver equals the run actor; `test_approver_cannot_be_the_run_actor`. |
| F2 — reviewer is a free-text label | **Not solved; documented.** The label check is not authentication. Host review uses a separate process and a brief-only workspace, which is stronger than a manual label but still not cryptographic identity. |
| F3 — uninstall deletes user files | **Fixed.** Uninstall removes only `SKILL.md`, `VERSION`, and the marker, then removes the directory only if empty; a user file survives. |
| F4 — `true` passes acceptance | **Fixed.** `Acceptance.validate` rejects no-op commands; `test_noop_acceptance_is_refused`. |
| F5 — silent `SKILL.md` overwrite | **Fixed.** The installer refuses a foreign skill file without the Aperio marker, as it already did for `/aperio`. |

The audit's pin predates the host adapter and the hardening work; the current
test count is 74.
