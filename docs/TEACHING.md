# Teaching: the craft of working inside Aperio

> **For agents.** This page teaches the three skills the loop demands: writing
> a plan that can be approved, writing acceptance checks that cannot lie, and
> reviewing honestly. Rules are anchored to traceable sources — some to real
> incidents from this repository's history (F1, F2, F4, Z-D6), some to the
> rebuild's design decisions — and the reference points to the ledger row or
> test that proves it. Read `aperio explain <topic>` for the live per-gate version of
> this page.

## 1. Writing a plan

A plan is a contract with three parts: what may change (`allowed_paths`), what
will change (`steps` with their `writes`), and how we will know it worked
(`acceptance`). The approval phrase binds all three by hash — anything edited
after approval invalidates the plan (Z-D binding tests; `tests/test_discovery.py::test_plan_body_tamper_after_approval_is_refused`).

### 1.1 Declare writes at the narrowest true scope

- Name exact files when you know them: `writes: ["src/cli.py"]`.
- Use a directory when the step legitimately creates files: `writes: ["dist/"]`.
  A directory target accepts files the step creates (fixed in `27dcfb7` after
  Z-D1: directory targets used to reject new files).
- Use a glob only when the set is genuinely dynamic: `writes: ["out/*.html"]`.
  Globs match one segment per `*` — `out/*.html` does **not** reach
  `out/sub/x.html`; recursion needs `**` (Z-D6, found by a live host review).
- A shell step that writes outside its declared `writes` fails the run when
  the path is outside the plan's `allowed_paths`
  (`tests/test_core.py::test_command_outside_write_is_detected`); for host
  steps the stricter per-step boundary is enforced before apply
  (`tests/test_adapter.py::test_host_change_outside_step_writes_is_rejected`).

**The craft:** `allowed_paths` is the fence; the union of step `writes` is
the set of doors (the post-run check is plan-wide; host steps are held to
their own step's writes). An agent that opens the whole fence
("allowed_paths: [\"*\"]") to avoid thinking about doors is announcing that
it does not know what its own commands do. Narrow both, and the run's
post-check becomes a real detector instead of a formality.

### 1.2 One step, one effect

A step that builds, tests, and deploys in one `run` cannot be verified,
rolled back, or reviewed separately. Split it. The runner snapshots declared
targets before the run and restores them when a step raises or a host step
escapes its workspace; a failed *command exit* leaves the changes in place
for explicit `aperio rollback` instead (`apply_plan` in
`src/aperio/runner.py`; rollback test
`test_rollback_restores_modified_and_removes_created`).

### 1.3 Read-only work is a `read` step

Exploration, inspection, and audit commands declare `kind: read` and must not
mutate the project — the runner diffs the scanned tree around the step and
fails the run on any change it can see
(`tests/test_core.py::test_read_step_cannot_change_the_project`; excluded
directories and outside-project writes are documented limits). A `read`
step cannot even declare writes (schema refusal in `model.py::Step.validate`).

## 2. Writing acceptance checks that cannot lie

The acceptance section is the plan's conscience. The recurring failure in this
repo's history is the check that technically passes but proves nothing.

- **No-ops are refused at plan time** — `true`, `exit 0`, `/bin/true`
  (`model.py::Acceptance.validate`; incident F4 in `docs/AUDIT-CLAUDE-20261026.md`).
- **A check that mutates the project fails verification** — the runner diffs
  the tree around the checks and deletes stray files
  (`test_acceptance_check_cannot_mutate_the_project`).
- **A timeout cannot pass** — a check that hangs is a failure, not a pass
  (`test_verification_timeout_cannot_pass`).
- **Presence is not behavior.** `test -f index.html` proves the file exists;
  it does not prove the form sends or the page renders. The existing Plan
  quality section says this; the craft is to pair one existence check with
  one behavior check per must-have (assert output content, run the built
  artifact, exercise the endpoint).
- **Prefer exact assertions.** Compare full output or a hash, not "contains
  the word OK". The house A/B rule: a test that passes against the old code
  is not evidence; the same rule applies to acceptance checks.

**The craft:** before writing the plan, write the acceptance checks first —
if you cannot say how the work will be proven, you do not yet know what the
work is.

## 3. Reviewing honestly

The reviewer is the loop's second pair of eyes, and the rules exist because
each was once missing:

- **The builder cannot review their own work** — refused by label match
  (`policy.py::assert_reviewer`; incident F2: reviewer identity was once a
  free-text label one process could self-assert. The self-approval no-op was
  incident F1, the approval gate's motivation).
  Host review goes further: a separate process, a brief-only workspace, no
  builder conversation.
- **A reviewer's changes are detected and the review is refused** — the
  runner fingerprints the tree before and after the host process; a change
  raises and the verdict is discarded. The process is not sandboxed and no
  automatic restore runs, so its edits remain and need separate cleanup;
  `aperio rollback` covers only the files in the run's backup manifest
  (`tests/test_adapter.py::test_reviewer_cannot_change_the_project`).
- **A reviewer verdict must engage with the brief.** The goldfish reviewer
  sees only the brief, the changed files, and the evidence. Confirming
  without reading is the reviewer's version of the no-op acceptance check.
- **Findings need evidence and a location.** "This looks wrong" is not a
  finding; "this function drops the error at src/x.py:42, here is the
  failing input" is. The audit ledger enforces exactly this shape for its
  own findings (`docs/AUDIT-CLAUDE-20261026.md`; `needs_validation` cannot
  carry severity) — host review verdicts are validated for verdict and
  reviewer identity, not finding structure, so read returned findings
  rather than trusting them.

**The craft:** the reviewer's job is to *refute the work*, not to approve it.
Confirmation is earned only when the refutation attempts fail.

## 4. The gates, in one table

| Gate | Refuses when | Because |
|---|---|---|
| Discovery | questions unanswered at `plan` | plans built on guesses rework later; waivers are explicit and dated |
| Learning | dossier missing/unproven at `plan`/`approve`/`run` | imported proof text is ignored; only a locally run command proves the stack |
| Todo | ledger empty or ≠1 in progress at `plan`; linked todo unsettled at `run` | one slice at a time keeps review and rollback meaningful |
| Readiness | preflight incomplete at `plan`; full record incomplete at `done`/`handoff` | deployment facts and threat model are owner decisions, not agent guesses |
| Approval | phrase mismatch, plan edited, approver == actor | the phrase binds the plan hash; self-approval was incident F1 |
| Writes | outside declared paths, protected paths, control state | Z-02; `tests/test_discovery.py::test_run_cannot_rewrite_discovery_control_state`; `tests/test_core.py::test_command_outside_write_is_detected` |
| Review | builder as reviewer, tampering, missing evidence | F2 (reviewer identity), tamper tests |

## 5. Working the loop with `aperio next`

`aperio next` computes the single next legal action from state, with the exact
command and the gate that requires it. Its routing mirrors the CLI's refusal
conditions per command — it was review-driven to match the CLI over 16 host
review rounds (`review-a8def7727b`). When a refusal surprises you, run
`aperio next` before guessing: the refusal text and the advisor name the same
gate.

## 6. Evidence tables: what claim requires what proof

Every gate's acceptance is a claim. A claim is only as good as its freshest
evidence — a previous run, a screenshot from yesterday, or "should pass" is
not evidence. This is the claim→evidence table for the loop; the named tests
are the proofs that the enforcement exists.

| Claim | Required fresh evidence | Enforced by |
|---|---|---|
| "The plan is approved" | the exact phrase `--confirm "I approve this plan"` + a SHA-256 of the plan body recorded at approval | `cli.py::cmd_approve`; tamper test |
| "The run stayed in bounds" | the post-run diff against the union of declared writes, on the scanned tree | `runner.apply_plan`; `test_command_outside_write_is_detected` |
| "The acceptance checks pass" | fresh check executions recorded with exit codes in the verify evidence — never a prior run | `runner.verify`; `test_noop_acceptance_is_refused` |
| "An independent reviewer confirmed" | review evidence from a reviewer who is not the builder, matched to the current verification | `policy.assert_reviewer`; `test_reviewer_cannot_change_the_project` |
| "The host stayed in its workspace" | the sandbox record + the workspace diff, against the step's writes | `adapter.run_host_step`; sandbox tests |
| "The handoff describes reality" | the handoff built from the recorded evidence, written after `done` | `handoff.write_handoff` |

## 7. Rationalization tables: the excuses, pre-rebutted

These are not hypothetical. Each row is an excuse class observed in this
repository's own review loops and audits (F1–F5, Z-D1–Z-D7, and the host
review rounds recorded in `docs/STATUS.md`).

| Excuse | Rebuttal |
|---|---|
| "The check passed last time; no need to re-run." | Verification evidence must be fresh. A prior run proves a prior state, not this one. |
| "It's just a small change; skipping review is fine." | Review is not sized by the diff. F2 existed because one process could self-assert review. |
| "I'm confident the fix works; the test would be redundant." | A test that fails without the fix and passes with it is the proof. Confidence is not evidence. |
| "The plan changed slightly after approval; it's basically the same." | The approval binds the plan's hash. Any edit invalidates it — re-plan and re-approve. |
| "The acceptance check is technically passing, that's what matters." | A check that passes while proving nothing (no-op, presence-only) is refused at plan time (F4). |
| "I'll widen allowed_paths just in case." | The fence exists to make the post-run check a real detector. Widen only to what the steps need. |
| "The reviewer is nitpicking; these findings are noise." | Findings are classified, not dismissed: contract misread, valid+actionable, valid trade-off (documented), noise. The first two require action. |
| "Skipping the sandbox for this one host run is pragmatic." | The sandbox is opt-in but fail-closed: requested and unavailable means the run fails. Pragmatism is a plan-level decision, made before approval. |

## 8. Multi-agent builds

When several agents build together, the roles run as a gated pipeline —
define before code, verify before audit, audit without the builder's claim,
a bounded fix loop, and a ship gate with a rollback plan. The Aperio-specific
contract is in `docs/AGENTS.md` ("Ship-ready workflow").

## 9. Motion and video work

When the owner asks for a product video, motion graphic, or animated demo,
follow the motion doctrine in `docs/MOTION.md`: the shot sheet is the plan
(approved before any animation code), the determinism contract makes the
output reviewable frame-by-frame, and lint/validate gates stand in for the
acceptance checks.

## 10. Where the incidents live

- `docs/PRD.md` — the Z-D / Z-P defect and proposal ledger with dispositions.
- `docs/AUDIT-CLAUDE-20261026.md`, `docs/AUDIT-CODEX-20261026.md` — the
  independent audits that produced F1–F5 and the P-rows.
- `docs/PROJECT-HISTORY.md` — the builder/monitor/owner loop that produced
  this discipline, and the hard rules it enforces.
- `tests/` — the *enforced* rules above have named tests (the refusal
  conditions the CLI checks); `docs/STATUS.md` maps rows to tests. The craft
  recommendations that go beyond enforcement — pairing presence checks with
  behavior checks, writing acceptance checks first — are advice, not
  tested gates.
