# Roadmap

This is the current roadmap, not the original rebuild wish list. The source of
measured status is `docs/STATUS.md`; the handoff entry is `HANDOFF.md`.

## M0: Core loop — done

- Project state, asks, plans, explicit approval, bounded apply, verification,
  independent review, finish, rollback, and handoff.
- Installer with dry run, idempotent reinstall, `/aperio` skill, and uninstall.
- Unit, CLI, and installer tests.
- Demo plan that creates and verifies a static page.

**Exit:** all tests pass; install, initialize, plan, approve, run, verify, review,
and handoff work from a clean temporary home.

## M1: Host dispatch — done for the used hosts; others deferred

- Host step in the plan schema: host, prompt, declared writes, timeout, budget.
- The host works in a disposable project copy; changes outside declared paths are
  rejected before they reach the real project.
- Claude and Codex are live-proven on current or recorded code; see
  `docs/HOST-PROOFS.md` for the date and limits.
- Goose and dsh adapters are command-shape tested; live calls were blocked by a
  local bridge HTTP 500 and a missing `RIVER_API_KEY`, respectively.
- OpenCode, KiloCode, Cline, and agy are command-shape tested. Live proofs are
  deferred until those hosts are actually used.

**Exit:** one host completes one bounded task through the same plan and evidence
path; no self-review; no credential in logs. Met for Claude/Codex.

## M2: Independent review and local coordination — done

- Fresh-context host review builds a brief-only workspace with the plan, changed
  files, acceptance, and evidence; the reviewer has no builder conversation.
- A self-review by the builder label is refused.
- Local durable message store: send, read, reply, ack, filters, restart
  persistence.
- Mediator records `CONFIRMED`, `REFUTED`, or `BLOCKED` from run, verify, and
  review evidence.
- Distributed transport and a direct two-host thread are not built.

**Exit:** a real fresh-context review is recorded, a bidirectional local message
test passes, restart persistence passes, and the mediator records a disposition.
Met locally; the distributed transport remains deferred.

## M3: Owner gates and execution safety — done

- Persistent discovery with explicit owner waivers and review dates.
- Learning dossier and real local proof gate; plan records the digest.
- Ordered todo ledger with evidence-backed acceptance and one-task-at-a-time rule.
- Readiness record for pre-flight, deployment data, after-sales, design, and
  security; full readiness is required for done/handoff.
- Non-overridable `.git`/`.aperio` protected paths.
- Read-only plan steps.
- Versioned `.aperio` state, queue recovery from the event journal, run
  checkpoints, and safe `resume` from the pre-run snapshot.
- Optional OS sandbox for shell/read steps; fail closed when unavailable.
- Toolchain/MCP manifest installation with owner approval for risky tools.
- Bounded local secret scan.
- Generated read-only status dashboard.

**Exit:** each item has a test and a `docs/STATUS.md` row. Met; the deferred host
and platform proofs are not part of this milestone.

## M4: Installer and portability — done for macOS; Windows deferred

- Bash installer and PowerShell installer with `--check`, `--update` backup, and
  `--rollback`.
- Fresh clone, spaces in paths, read-only prefix failure, and interrupted install
  are tested where available.
- Native Windows `.cmd` execution is deferred; PowerShell is tested under
  `pwsh` 7.6.7 on macOS.
- Linux `bwrap` is implemented but not live-tested here.

**Exit:** documented pass, fail, or unsupported status per platform. Met for
macOS; Windows/Linux live proof deferred.

## M5: Public handoff — this document set

- `HANDOFF.md` is the incoming-agent entry point.
- `docs/OWNER-REQUESTS.md` records the owner's substantive requests and where each
  is addressed.
- `docs/STATUS.md` records measured results and known limits.
- `docs/PRD.md` records requirements and scope decisions.
- `docs/AGENTS.md`, `docs/ARCHITECTURE.md`, and `docs/TESTING.md` explain roles,
  modules, and verification.
- Privacy/secret scan exists; an external penetration test is optional and not
  claimed.

**Exit:** a new agent can start from the repository alone, run the baseline, and
find every owner decision and boundary. Met at handoff.

## Out of scope for Aperio

- CMS, media, editorial workflow, visual editor, and SEO delivery.
- Deployment execution, provider credentials, and hosting operations.
- Automatic public release, force-push, or history rewrite.
- Multi-tenant SaaS and autonomous spending.

## Deferred work

These are optional environment proofs, not release blockers:

- live OpenCode/KiloCode/Cline/agy dispatch;
- live Goose/dsh dispatch;
- native Windows `.cmd` and Linux `bwrap`;
- live host skill loading and a teacher UI;
- dependency-history scanning and external penetration testing.

Do not start a deferred item unless the owner asks for that environment or the
task explicitly requires it. Do not describe it as done before it is run.
