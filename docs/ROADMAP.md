# Roadmap

The order is deliberate. Do not build a large feature surface on an unproven loop.

## M0: Core loop (implemented)

- Project state, asks, plans, approval, bounded apply, verification, review, finish, rollback, handoff.
- Installer with dry run, idempotent reinstall, and uninstall.
- Unit, CLI, and installer tests.
- Demo plan that creates and verifies a static page.

**Exit criteria:** all tests pass; install, initialize, run, verify, review, and handoff work from a clean temporary home.

## M1: Host adapter and real work dispatch

- Add a host capability record: binary, version, models, permissions, cost status, health.
- Add one adapter that accepts a plan and returns a bounded patch or a command result.
- Keep approval and execution in the core. The adapter does not get its own write path.
- Record host, model, prompt, output digest, and failure reason.
- Prove one real task on a disposable project, with a different reviewer.

**Exit criteria:** one host completes one bounded task through the same plan and evidence path; no self-review; no credential in logs.

## M2: Independent review and mesh

- Add a second host or reviewer path.
- Add a message store with send, read, reply, acknowledgment, and restart persistence.
- Add a mediator command that compares builder and reviewer evidence and records a disposition.
- Prove two real hosts exchange a task and a reply.

**Exit criteria:** bidirectional message test, restart test, and a recorded mediator decision.

## M3: CMS and delivery slice

- Add a target-project adapter for one approved stack.
- Build one public section and its admin controls together.
- Prove edit, save, publish, permission denial, and rollback.
- Run SEO and accessibility checks against built output.
- Generate a client handoff with setup, content, and recovery steps.

**Exit criteria:** a real target project runs, a real content change persists and renders, and the acceptance evidence is reproducible.

## M4: Installer and portability

- Add PowerShell parity or explicitly mark Windows unsupported.
- Add update and recovery behavior.
- Test fresh clone, different home, spaces in paths, read-only prefix failure, and interrupted install.
- Remove any hard-coded home, checkout, or model path.

**Exit criteria:** documented pass, fail, or unsupported status per platform. No destructive test on the owner's machine.

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
