# Rebuild Report: 2026-10-26

## What was requested

The owner asked for the documentation to be cleaned up before further work, and for Aperio-Orchestrator to be rebuilt from the beginning rather than patched further.

## Decision

The rebuild is a fresh public repository with a new history:

`https://github.com/Aperio-Studios-Private/Aperio-Orchestrator`

The old repository is preserved as a private archive. It is not the product, and it was not force-pushed or made public. Its history contained client identifiers, and old Git objects can remain reachable on a remote even after a history rewrite.

## What was archived

- `~/Desktop/Aperio-Orchestrator-pre-v2-20261026/docs-and-reports.tar.gz` (1.8 MB)
- `~/Desktop/Aperio-Orchestrator-pre-v2-20261026/repository.bundle` (9.6 MB)
- `SHA256SUMS` beside both files

The archive is described in `docs/ARCHIVE.md`. Keep it private.

## What was built

A small standard-library core:

- project initialization and append-only asks;
- plan creation, explicit owner approval, bounded writes, and shell steps;
- host dispatch through a disposable project copy for Claude and Goose; Claude proven end to end, Goose's command path tested but its local bridge returned HTTP 500;
- path traversal, absolute path, symlink, and protected-path refusal;
- change detection for writes outside the declared plan;
- acceptance checks and evidence records;
- independent review enforcement;
- finish only after verified work and a confirmed review;
- rollback from pre-run snapshots;
- handoff generated from actual state;
- deterministic documentation drift checks for links and inline paths;
- installer with dry run, idempotent reinstall, skill, `/aperio` command, and uninstall;
- read-only host detection.

The v2 documentation set is `README.md`, `START-HERE.md`, and the files in `docs/`. There are 14 Markdown files, not 1,241.

## Verification

Run on the final public tree:

| Check | Result |
|---|---|
| `PYTHONPATH=src python3 -m unittest discover -s tests -v` | 40 tests pass |
| `ruff check src tests` | pass |
| `shellcheck install.sh` | pass |
| GitHub Actions, Python 3.10 / 3.12 / 3.14 | pass |
| Fresh public clone, `./install.sh`, `aperio --version`, demo plan | pass |
| Real-home install | binary, skill, and command present |
| Real Claude host dispatch | file written, acceptance passed, review confirmed, done |
| Real Claude fresh-context review | brief-only reviewer confirmed a verified task |
| `aperio drift` | clean: docs links and inline paths resolve |

The demo was run through the full loop: unapproved run refused, approved run applied, acceptance passed, review confirmed, task done.

## What is not built

- Dispatch to hosts beyond the Claude and Goose adapters.
- Mesh chat and mediator message comparison.
- CMS, media, SEO, and Astro/Lumos delivery.
- Web dashboard.
- OS sandbox for host or shell steps.
- Remote deployment.
- Windows installer parity.

The README and `docs/STATUS.md` say this plainly. Do not describe the repository as feature-complete.

## Handover from the previous agent

Claude acknowledged the mediator handover, reported the history rewrite complete, and stopped taking new work. Its key findings:

- the rewrite changed every commit hash on seven local branches;
- a fresh clone had no client identifiers;
- nothing was pushed;
- old local-only checkpoint refs still contain identifiers but cannot reach a clone;
- the old public flip remains blocked on network access and owner approval.

The old repository was not force-pushed. The public product is the new repository, not the rewritten old one.

## Next task

M1: one real host adapter that accepts a plan and returns a bounded patch or command result, followed by a different reviewer. It must use the same approval, evidence, and review path. No adapter gets its own write path.

## Owner action

Review the public repository and decide whether the old private repository should be retained as an archive or retired. No credential, client data, or old history was copied into the public tree.
