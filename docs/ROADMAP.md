# Roadmap

The order is deliberate. Do not build a large feature surface on an unproven loop.

## M0: Core loop (implemented)

- Project state, asks, plans, approval, bounded apply, verification, review, finish, rollback, handoff.
- Installer with dry run, idempotent reinstall, and uninstall.
- Unit, CLI, and installer tests.
- Demo plan that creates and verifies a static page.

**Exit criteria:** all tests pass; install, initialize, run, verify, review, and handoff work from a clean temporary home.

## M1: Host adapter and real work dispatch (implemented for Claude; Goose partial)

- Host step in the plan schema: host, prompt, declared writes, timeout, budget.
- The host works in a disposable project copy; changes outside declared paths are rejected before they reach the real project.
- Claude adapter proven end to end on a disposable project: file written, acceptance passed, review confirmed, done.
- Goose adapter command path tested with a fake binary. A live Goose call returned HTTP 500 from its local bridge, so it is not claimed as working.
- Evidence records host, command, prompt digest, exit code, duration, stdout/stderr, changes, and violations.

**Exit criteria:** one host completes one bounded task through the same plan and evidence path; no self-review; no credential in logs.

**Status:** Claude met the criterion. Goose did not, because of an external bridge failure. Other hosts are not connected.

## M2: Independent review and mesh (review implemented; mesh not)

- Fresh-context host review implemented: `aperio review <task> --host claude` builds a brief-only workspace with the plan, changed files, acceptance, and evidence; the reviewer has no builder conversation and cannot edit.
- A real Claude reviewer confirmed a verified task. A self-review by the builder host is refused.
- A local durable message store is implemented: send, read, reply, ack, filters, and restart persistence.
- A mediator command records `CONFIRMED`, `REFUTED`, or `BLOCKED` from run, verify, and review evidence.
- Add a distributed transport and prove two real hosts exchange a task and a reply.

**Exit criteria:** a real fresh-context review is recorded, a bidirectional message test passes, restart persistence passes, and the mediator records a disposition.

**Status:** fresh-context review, local messaging, restart persistence, and mediator disposition met. Real Claude and Codex processes each used the store in separate exchanges. A direct two-host thread over a distributed transport is not built.

## M3: CMS and delivery slice

See `docs/CMS-ROADMAP.md` for the stack-neutral design, deployment decision
tree, phases, and exit proof. The framework is selected after discovery, not
before.

- Add a target-project adapter for one approved stack.
- Build one public section and its admin controls together.
- Prove edit, save, publish, permission denial, and rollback.
- Run SEO and accessibility checks against built output.
- Generate a client handoff with setup, content, and recovery steps.

**Exit criteria:** a real target project runs, a real content change persists and renders, and the acceptance evidence is reproducible.

## M4: Installer and portability

- PowerShell installer is implemented and tested under `pwsh` on macOS; native Windows `.cmd` execution is not tested.
- Bash and PowerShell update/recovery: `--check`, `--update` with a bounded library backup, and `--rollback` are implemented and tested under `pwsh`/bash on macOS.
- Test fresh clone, different home, spaces in paths, read-only prefix failure, and interrupted install.
- Remove any hard-coded home, checkout, or model path.

**Exit criteria:** documented pass, fail, or unsupported status per platform. No destructive test on the owner's machine.

**Status:** Bash installer verified; PowerShell install, launcher version, and uninstall verified under `pwsh` 7.6.7 on macOS. Update/recovery and native Windows execution are not built.

## M5: Public beta

- Privacy scan of the worktree, tracked files, history, branches, and artifacts.
- Secret scan with no unresolved finding.
- Public README, license, support boundary, and known limits.
- Release notes that match measured behavior.
- Owner approval for the visibility change.

**Exit criteria:** a new user can install, run the demo, read the evidence, and understand exactly what is not built.

## Not planned yet

- Multi-tenant SaaS.
- Automatic deployment.
- Autonomous spending.
- A universal design system forced on every project.
- A CMS for projects that do not need one.
