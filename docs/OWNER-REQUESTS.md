# Owner request ledger

This is the reconstructed record of the owner's substantive requests for Aperio v2.
It exists so an incoming agent does not need the old chat. If this table and the
code disagree, the code and `docs/STATUS.md` win; update this table rather than
silently carrying a stale claim.

Status vocabulary: **DONE**, **PARTIAL**, **DEFERRED**, **OUT OF SCOPE**.

| # | Owner request or decision | Status | Where recorded / evidence | Boundary |
|---|---|---|---|---|
| 1 | Rebuild Aperio from scratch as a clean, public repository rather than patching the old tree. | DONE | `README.md`; `docs/REBUILD-REPORT-20261026.md`; remote `https://github.com/Aperio-Studios-Private/Aperio-Orchestrator` | Old repository remains private; do not force-push or publish its history. |
| 2 | Use the `Aperio-Studios-Private` organization, not the wrong organization. | DONE | Git remote and `README.md` | Check the remote before any push. |
| 3 | Do not believe documentation claims; report only what code and commands prove. | DONE | `docs/PRD.md` §0; `docs/STATUS.md`; this handoff | A document is not evidence. Re-run the command. |
| 4 | Keep the build honest: no stale, contradictory, or unsupported claims. | DONE | `docs/STATUS.md`; `aperio drift`; `HANDOFF.md` §3 | Any new claim needs a test, command, or artifact. |
| 5 | Ask before starting if a requirement or target is ambiguous. | DONE | `docs/AGENTS.md`; `HANDOFF.md` §11 | Do not invent a target, credential, or scope. |
| 6 | Commit locally as work is completed; push only verified work. | DONE | `CONTRIBUTING.md`; `docs/AGENTS.md` | Push is not automatic approval. |
| 7 | Use named hosts and subagents to speed up work; do not sleep or wait for them. | PARTIAL | `docs/AGENTS.md`; `docs/HOST-PROOFS.md` | Claude/Codex are live-proven. Extra host live proofs are deferred. |
| 8 | Self-approve technical checks; escalate product decisions, credentials, UI, and destructive actions. | DONE | `docs/AGENTS.md`; `HANDOFF.md` §8 | Technical checks are not owner approval. |
| 9 | Keep an independent auditor with separate memory; auditor reports findings but does not push fixes. | DONE | `docs/COORDINATION.md`; `docs/AUDIT.md`; auditor profile/report path is outside the public tree | Auditor identity is a label, not cryptographic proof. |
| 10 | Work one module at a time and prove each slice. | DONE | `docs/ROADMAP.md`; `docs/PRD.md` gates | Deferred items must stay deferred, not be claimed done. |
| 11 | Build a mandatory learning/stack dossier: official docs, versions, skills, MCP, local proof, fallback, unresolved questions. | DONE | `docs/PRD.md` FR-36; `src/aperio/learning.py`; `tests/test_learning.py` | Imported proof text is ignored; only a real local command makes it ready. |
| 12 | Record toolchain provenance and create project-scoped skills; require approval for global/paid/credentialed/elevated tools. | DONE | `docs/PRD.md` FR-37; `src/aperio/toolchain.py`, `src/aperio/skillgen.py`; `tests/test_toolchain.py`, `tests/test_skillgen.py` | No registry discovery; commands are declared argv, not guessed. |
| 13 | Gather pre-flight, deployment, after-sales, design, and security data before handoff. | DONE for data readiness | `docs/PRD.md` FR-38/FR-39/FR-40; `src/aperio/readiness.py`; `tests/test_readiness.py` | Deployment execution is out of scope; data is still required. |
| 14 | Teach design principles for the selected application class; no unsupported "award-winning" claim. | PARTIAL | `docs/PRD.md` FR-39; readiness design section | Independent visual critique and browser inspection remain deferred. |
| 15 | Enforce a security baseline and threat model; never claim "impenetrable." | PARTIAL | `docs/PRD.md` FR-40; `src/aperio/security.py`; `tests/test_security.py` | Local secret scan exists; dependency-history scan and external pentest are deferred. |
| 16 | Decompose work into minimal tasks, require per-task acceptance, and hand off only when the next agent can resume. | DONE | `docs/PRD.md` FR-41; `src/aperio/todo.py`; `tests/test_todo.py`; `HANDOFF.md` | Automatic acceptance evidence capture is deferred. |
| 17 | Teach back and record competency before an agent claims mastery. | DONE | `docs/PRD.md` FR-42; learning dossier; `tests/test_learning.py` | Separate teacher UI and host-session loading proof are deferred. |
| 18 | Add the ZCode audit findings and suggestions to the PRD; fix real findings and verify them. | DONE for P0/P1 fixed items | `docs/PRD.md` Appendix A; `docs/STATUS.md`; commits and tests | P2 observability/interop items remain planned/deferred. |
| 19 | Do not add a CMS, CMS demo, or CMS product to Aperio. CMS is a separate method for a target project. | OUT OF SCOPE for Aperio | `docs/PRD.md` "Scope decision"; `README.md` "Out of scope"; `docs/CMS-ROADMAP.md` labeled separate method | A target project may choose a CMS; Aperio does not ship one. |
| 20 | Aperio should not deploy projects; it is a tool. | OUT OF SCOPE for Aperio | `docs/PRD.md` "Scope decision"; `README.md` "Out of scope"; `docs/DECISIONS.md` ADR-007 | Aperio records readiness and hands off; deployment is an owner/project action. |
| 21 | Do not require live proof for every extra host, Windows, or Linux path if those environments are not in use. | DEFERRED | `README.md` "Not built"; `docs/STATUS.md`; `HANDOFF.md` §9 | Command-shape tests remain; live proof only when the environment is used. |
| 22 | Provide a status UI that can be checked without reading the CLI. | DONE for read-only dashboard | `src/aperio/dashboard.py`; `tests/test_dashboard.py`; `aperio dashboard` | A live server and interactive controls are not built. |
| 23 | Keep local state, caches, audit reports, and client data out of the public repository. | DONE | `.gitignore`; `HANDOFF.md` §10; `docs/STATUS.md` | `.aperio/` is local-only; archive local state outside the tree. |
| 24 | Produce a complete handoff so another agent can continue without chat context or prior memory. | DONE | `HANDOFF.md`; `docs/OWNER-REQUESTS.md`; `START-HERE.md`; `docs/AGENTS.md` | The repository is the source of truth; re-measure before relying on any count. |

## Requests that are behavioral, not product features

These are preserved as working rules rather than code:

- acknowledge terminal output as pass/fail when the owner sends it;
- do not claim a wait or use sleep as progress;
- do not use an AI host as proof of another host's claim;
- do not self-approve a product decision;
- do not push an auditor's fix; report it and let the owner/builder review.

## Open owner decisions

None are required to run the current local tool. The following remain owner or
target-project decisions:

- whether to commission an external penetration test;
- whether a target project needs a CMS, and if so which hosting/operations model;
- whether to deploy any target project and with which provider;
- whether to run the deferred host/Windows/Linux proofs.
