# EGM Assessment: Elephant-Goldfish Model

**Researched:** 2026-10-26  
**Repository:** `google/elephant-goldfish-model`  
**License:** Apache-2.0  
**Status of upstream:** active, early, no tagged release at the time of review

## What it actually is

EGM is not a trained model and not a runtime library. It is an open-source **plugin and skill set for spec-driven development** with coding agents. The repository contains Markdown skills, reviewer personas, document standards, host manifests, and Python test tooling.

The metaphor:

- **Elephant:** a deep-context session that holds system history, architecture, user journeys, and design intent. It drafts a specification. It does not write code.
- **Goldfish:** a fresh, zero-context reviewer that receives only the draft spec and the live source. It does not inherit the builder's conversation or assumptions.
- **Human:** owns the decisions, trade-offs, and final approval.

The workflow is: brainstorm, draft a design document under `docs/designs/`, run a multi-stage Goldfish review, resolve findings, merge the specification, implement against it, and run a drift report later.

## Repository facts

| Item | Value |
|---|---|
| Stars | about 947 |
| Forks | about 85 |
| Created | 2026-09-13 |
| Latest pushed commit | 2026-10-25 |
| Default branch head reviewed | `3d0b34821ce88ad328b0c9bf0e06d7eb5f1cd669` |
| Files | 125 |
| Markdown files | 62 |
| Releases | none at review time |
| Plugin version | `0.1.0` |
| License | Apache-2.0 |
| Supported hosts in manifests | Claude Code, Codex, Antigravity, Claude Cowork, ChatGPT Work |
| Official Google product | No, explicitly stated as not officially supported |

It has tests, including an opt-in Claude integration test that checks whether a reviewer child receives parent context. That is a serious test for a methodology plugin.

## What is strong

1. **Fresh-context review is the core idea.** A reviewer that does not inherit the builder's conversation is a better adversarial check than a reviewer in the same thread.
2. **Artifact-first.** Specs, decisions, and review reports are files, not chat dumps. This matches Aperio's handoff and evidence direction.
3. **Human-owned gates.** The workflow does not auto-chain every skill. Humans decide at the gaps.
4. **Drift detection.** The idea that checked-in design docs must be compared with the live code is directly useful.
5. **Reviewer personas and rubrics.** Separate lenses (comprehension, design critique, implementation readiness, zoom-out) reduce the "one reviewer agrees with everything" problem.
6. **Skill tests.** The repository treats skill descriptions as triggers to be evaluated, not just prose.

## What it is not

- Not a task queue, state machine, evidence store, host router, or write-policy engine.
- Not a replacement for Aperio's approval and evidence path.
- Not filesystem isolation. Its own Codex documentation says fresh context does not isolate the filesystem, memory services, or project instructions. A reviewer can still read accessible files.
- Not a stable dependency. It is early (`0.1.0`), has no releases, and is explicitly not an officially supported Google product.
- Not a small addition. Installing it adds a second design/review workflow with its own commands and artifacts.

## Fit with Aperio

Aperio already has the stronger runtime pieces: plan approval, allowed paths, snapshots, evidence, review gate, install, and a public repository. EGM has the stronger **review protocol**: a genuinely fresh-context reviewer with only the spec, source, and evidence.

The overlap is real. Installing the full EGM plugin would create two competing workflows: `/egm-*` and `/aperio`. That would confuse hosts and users, and it would duplicate the PRD/plan/review lifecycle.

## Recommendation

**Adopt the protocol, not the plugin.**

1. **Add a fresh-context review mode to Aperio.** `aperio review <task> --host claude` should send only the plan, changed files, acceptance results, and evidence to a new host session. The reviewer must not receive the builder's chat, and must return structured findings. This is the single highest-value idea in EGM.
2. **Add a deterministic drift check.** `aperio drift` should verify that paths, commands, and claims referenced by `docs/PRD.md`, `docs/STATUS.md`, and `docs/ARCHITECTURE.md` still exist and that cited tests exist. This is a code-level version of EGM's drift report and does not need an LLM.
3. **Keep Aperio's plan small.** EGM's own FAQ warns that documentation can become a review bottleneck. Aperio should use a design dossier for consequential work and a short plan for small fixes, not a seven-skill pipeline for every task.
4. **Do not install the EGM plugin into the Aperio workflow.** If the owner wants to trial it, install it in a separate profile and a disposable project. Never make it a dependency of Aperio or a required host plugin.
5. **Do not copy its skill text without the Apache-2.0 notice.** The ideas are usable; wholesale copying is a licensing and maintenance liability.

## Concrete next additions

| Addition | Why | Cost |
|---|---|---|
| `aperio review --host <host>` with fresh context | Independent review that is actually independent | **Implemented and proven with Claude on 2026-10-26** |
| `aperio drift` | Detect docs that point at missing code or tests | Low |
| Reviewer prompt schema | Makes verdicts parseable and auditable | **Implemented: JSON verdict and findings** |
| Skill trigger tests for `/aperio` | Proves the skill activates on the right requests | Low |
| Optional EGM trial in a separate profile | Evaluate the full method without contaminating Aperio | Later |

## Verdict

EGM is useful as a **design and review discipline**, especially the Goldfish idea. It is not the orchestration layer Aperio needs, and it should not be installed as a dependency. Aperio should borrow the fresh-context review and drift-check concepts while keeping its own approval, evidence, and write boundaries.
