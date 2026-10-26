# Decisions

## ADR-001: Standard library core

**Decision:** the core uses Python 3.10+ and the standard library only.

**Why:** installation must work without a package manager, network, or a dependency tree. The first milestone is trust in the loop, not framework coverage.

**Consequence:** no YAML parser, no rich terminal UI, and no HTTP client in the core. Add dependencies only with a written reason, license, and portability check.

## ADR-002: `.aperio` project state

**Decision:** project state lives in `.aperio/`.

**Why:** the old `.sps` tree mixed project state, generated reports, and tool metadata. A new name makes the rebuild boundary visible and avoids silently reading stale state.

**Consequence:** the old `.sps` files are not read by v2. A migration tool may be added later; until then, import asks deliberately.

## ADR-003: Explicit approval phrase

**Decision:** `aperio approve` requires `--confirm "I approve this plan"`.

**Why:** a boolean flag is too easy to pass by habit. The phrase makes the owner's decision visible in shell history and evidence.

**Consequence:** automation cannot approve without intentionally supplying the phrase. That is the point.

## ADR-004: Detect, do not claim to jail

**Decision:** shell steps are allowed only inside an approved plan, with declared writes and a changed-file check. The documentation states that this is not an OS sandbox.

**Why:** claiming a path check is isolation would be false. A real sandbox is a later, separately reviewed feature.

**Consequence:** a malicious or careless shell command can change a file before detection. The run is marked failed and the evidence records the violation; rollback uses the snapshot.

## ADR-005: Independent review is a gate

**Decision:** `done` requires a verified task and a confirmed review from a reviewer whose name differs from the builder.

**Why:** the old project repeatedly treated self-assessment as verification.

**Consequence:** a completed task requires a confirmed review whose reviewer label differs from the builder label. This is a procedural gate and an audit trail, not authenticated separation: a local process can supply any label. Use `review --host` for a separate fresh-context process when actual host separation is required. A task without a confirmed review stays `NEEDS_REVIEW`, not done.

## ADR-006: Fresh public repository, old repository preserved

**Decision:** the v2 tree is published as a fresh repository with clean history. The old repository remains private and is archived outside the public tree.

**Why:** the old history contained client identifiers. A scrub reduced them in the current history, but old objects can remain reachable on the remote. A fresh public repository removes that exposure instead of relying on a remote garbage collection.

**Consequence:** the old URL is not the public product URL. The old repository is a private archive. Any later migration must not copy old history blindly.

## ADR-007: No automatic deployment

**Decision:** v2 records local evidence and writes a handoff. It does not deploy.

**Why:** deployment is a protected, environment-specific action. A local green test is not a deployment.

**Consequence:** deployment remains an explicit owner action or a separately approved adapter with its own credentials and verification.

## ADR-008: One canonical document set

**Decision:** the active documentation is the README, START-HERE, and the files in `docs/`. Historical reports, generated PRDs, and audits are not active state.

**Why:** 1,241 Markdown files and contradictory status pages made the old repository harder to trust.

**Consequence:** new evidence goes into `docs/STATUS.md` or a dated file linked from it. Do not create a second queue, a second PRD, or a second handoff.
