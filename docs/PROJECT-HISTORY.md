# Project history: where Aperio came from, and how today was reached

> **For the next agent.** Read `START-HERE.md` first, then this page for the full
> arc. Every claim links to a file or command in this repository. There is also
> `HANDOFF.md` (current working state) and `docs/REBUILD-REPORT-20261026.md`
> (the rebuild-day snapshot, historical).

## 1. Where Aperio came from

Aperio exists to make agentic coding work *for the owner* instead of around
them: agents write code, but plans are explicit, approval is a visible owner
decision, changes are bounded to declared paths, verification is real, an
independent review is required, and the handoff describes actual state — not
claims. The full owner-request ledger is transcribed in
`docs/OWNER-REQUESTS.md`; the product requirements grew from it
(`docs/PRD.md`, FR-1…FR-42).

## 2. The v1 repository and why it was archived

The previous repository (same GitHub org; now preserved as
**Aperio-Orchestrator-Archive**, private) was **not** rebuilt away because it
was broken — the owner decided the documentation and code had been patched
past the point of a clean foundation, and asked for a rebuild from the
beginning rather than more repair. The full reasoning is recorded in
`docs/REBUILD-REPORT-20261026.md` ("What was requested", "Decision").

Two facts mattered for how the archive was handled:

- The old history contained **client identifiers**. Old Git objects can remain
  reachable on a remote even after a history rewrite, so the archive was kept
  private and the new repository started with a fresh history.
- The old tree mixed project state (the `.sps/` directory), generated reports,
  and tool metadata. That boundary is why v2 uses `.aperio/` with schema-gated
  state files (ADR-002 in `docs/DECISIONS.md`).

The archive itself was preserved before anything was discarded:
`~/Desktop/Aperio-Orchestrator-pre-v2-20261026/` holds a docs-and-reports
tar.gz (1.8 MB), a repository bundle (9.6 MB), and `SHA256SUMS` — described in
`docs/ARCHIVE.md`. It is **kept private** on purpose.

## 3. The rebuild (2026-10-26)

The rebuild is the public repository this file lives in, with a fresh history
starting at `a43f909` ("feat: Aperio v2 clean core loop with tests and docs").
Core decisions are written as ADRs: standard-library-only core (ADR-001),
`.aperio/` state (ADR-002), the explicit approval phrase (ADR-003), policy
first with an optional OS sandbox (ADR-004).

What exists today is documented in `docs/STATUS.md` (results table with
per-suite counts) and `docs/ARCHITECTURE.md`. In one sentence: a bounded
plan → approve → run → verify → review → finish → handoff loop over
versioned `.aperio/` state, with a learning dossier, readiness records, a todo
ledger, project-scoped skill scaffolding, an approval-gated toolchain, a local
security scan, a read-only dashboard, and run resume — every gate backed by a
named test listed in `docs/STATUS.md`.

## 4. The verification layer: monitor, builder, auditor

From the first feature commit onward, work ran as a three-role loop. This is
how the repository was actually built today, and it is the pattern to keep:

- **Builder** implements one approved slice at a time and pushes. Pushes are
  announced in the builder-auditor thread.
- **Monitor/auditor** (report-only, enforced by a pre-commit hook in
  `.git/hooks/pre-commit` — the `aperio-auditor` profile cannot create
  commits) re-measures every claim: suite counts, ruff, drift, CI runs, live
  probes of the real binaries. Findings are worded with the repository's
  vocabulary: *Verified fixed* requires a discriminating test;
  *Implemented* means the code exists but the test does not discriminate.
- **Owner** decides products, credentials, visibility, and destructive actions.

Ten-plus audit cycles ran on 2026-10-26 alone (`docs/AUDIT.md`,
`audit-reports/` in the auditor workspace, and the PRD appendix table
`docs/PRD.md` around line 850). Notable confirmed-and-fixed items, each with a
committed test: the kilocode adapter flag (rejected before verification),
queue recovery journal and run checkpoints, install.ps1/sh restore failures
that could leave no library, dashboard `--output` that could clobber the
control plane, a secret-scan regex blind to `DB_PASSWORD`-style names, the
learning/readiness/todo gates (plan, approve, run, done, handoff), and the
`recover --project` flag. Two hard-won lessons are worth recording: a test that
passes against the old code is not evidence (the A/B rule), and a fix is not
done until its own suite run, ruff, drift, and — for pushed code — CI agree.

## 5. Hard rules the next agent must keep

1. One builder at a time; re-read files immediately before patching — a
   sibling or previous agent may have edited seconds earlier.
2. The auditor is report-only. Never bypass the pre-commit hook.
3. "Verified fixed" needs an A/B-discriminating test; prefer exact exit-code
   and set-based assertions over loose ones.
4. Bump doc test counts in the same commit that adds tests
   (`docs/TESTING.md`, `docs/STATUS.md`, `docs/PRD.md`).
5. Claims about hosts need live evidence in `docs/HOST-PROOFS.md`;
   `review --host` supports only claude, codex, dsh, goose — the other four
   adapters are dispatch-only for `run`.
6. Pushes are announced in the builder-auditor thread; CI must be green on
   pushed heads before the next feature.

## 6. Open items at the time of writing

- **Owner decisions (do not decide yourself):** repository visibility — the
  repo is public today while the slug says "-Private"; and the final
  disposition of the third-party ZCode audit artifact (kept out of the
  repository; the PRD records it as archived outside).
- **Carried engineering items:** a test seam to exercise the PowerShell
  restore-failure branches (ps1 inner restore is only code-reviewed); a
  readiness digest bound into plans (run currently re-validates preflight but
  does not pin its content); sandbox host-wide reads are comment-only
  disclosure; the toolchain approval gate is advisory by design; drift is not
  yet a CI job; `aperio doctor` does not yet surface learning/readiness state.

## 7. Where things stand right now

Suite: 236/236 tests OK. Ruff clean. Drift clean. CI green on pushed `main`.
The exact numbers, per-suite rows, and known limits live in `docs/STATUS.md`
and `docs/TESTING.md` — re-measure before trusting this page.
