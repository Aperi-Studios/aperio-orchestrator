# Aperio Orchestrator v2

Aperio turns an owner request into a bounded, approved plan, applies it, runs acceptance checks, requires an independent review, and writes evidence and a handoff.

**Status: early rebuild.** The core loop and installer work. Host dispatch, mesh chat, CMS delivery, and SEO delivery are not built yet. Do not describe this as feature-complete.

## Why this rebuild exists

The previous repository accumulated a large layer of reports, audits, generated PRDs, and status documents that did not reliably match the code. This repository starts with a small canonical documentation set and a tested core.

## Quick start

```bash
git clone https://github.com/Aperio-Studios-Private/Aperio-Orchestrator.git
cd aperio-orchestrator
./install.sh
aperio --version
```

PowerShell 7:

```sh
pwsh -File install.ps1
```

The installer copies the package to `~/.local/share/aperio`, creates `~/.local/bin/aperio`, and installs the skill under `~/.claude/skills/aperio`. The `/aperio` entry point is the skill; no duplicate slash-command file is installed. The installer does not edit host settings, use sudo, or download anything. The host's ability to load the skill is not yet independently verified.

To test without installing:

```bash
PYTHONPATH=src python3 -m aperio --help
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## The loop

```bash
aperio init . --name "My project"
aperio ask "Build a one-page site with a working contact form" --source owner
aperio inspect
aperio discover next
aperio discover answer <question-id> --choice 1,3 --text "..."
aperio discover status
aperio plan plan.json
aperio approve <plan-id> --by owner --confirm "I approve this plan"
aperio run <task-id> --actor builder
aperio verify <task-id>
aperio review <task-id> --host claude
aperio done <task-id>
aperio handoff <task-id> --print
aperio drift
aperio message send --from builder --to reviewer --body "please review" --task <task-id>
aperio mediate <task-id>
```

A plan is JSON. It declares allowed paths, exact write steps, bounded run steps, host steps, and acceptance checks. A host step is shown in `examples/host-plan.json`.

```json
{
  "title": "Build a page",
  "request": "The owner's request in their terms.",
  "builder": "builder",
  "allowed_paths": ["site/"],
  "steps": [
    {"id": "write", "kind": "write", "path": "site/index.html", "content": "..."}
  ],
  "acceptance": [
    {"id": "check", "command": "python3 -c \"from pathlib import Path; assert Path('site/index.html').is_file()\""}
  ]
}
```

## Proof

See [docs/HOST-PROOFS.md](docs/HOST-PROOFS.md) for the exact host commands and output recorded on 2026-10-26. The external audits and dispositions are in [docs/AUDIT-CODEX-20261026.md](docs/AUDIT-CODEX-20261026.md) and [docs/AUDIT-CLAUDE-20261026.md](docs/AUDIT-CLAUDE-20261026.md).

## What works now

- Project initialization and append-only owner asks.
- Plan creation, explicit approval, bounded writes, and shell steps with timeouts.
- Host dispatch through a disposable project copy for the Claude, Codex, dsh, and Goose adapters. Claude is proven on current code. dsh and Goose command paths are tested, but their live runs are blocked by a missing credential and an HTTP 500 bridge, respectively. Codex evidence is historical and is not the current trusted host set.
- Fresh-context host review. `aperio review <task> --host claude` gets only the plan, changed files, acceptance results, and evidence, with no builder conversation. Real Claude reviewers confirmed verified work on current code; earlier Codex review evidence is historical.
- Change detection for writes outside the declared plan.
- Acceptance checks and recorded evidence.
- Independent review enforcement by reviewer name.
- Rollback of files captured before a run.
- Handoff generation from actual state.
- Deterministic documentation drift checks: links and inline paths that do not exist fail `aperio drift`.
- Local durable message store with send, read, reply, ack, filters, and restart persistence. Real Claude and Codex processes both read and replied through it; Codex is historical evidence, not the current trusted host set.
- Mediator disposition from run, verify, and review evidence: `CONFIRMED`, `REFUTED`, or `BLOCKED`.
- Installer, idempotent reinstall, dry run, and uninstall.
- PowerShell installer tested under `pwsh` 7.6.7 on macOS; native Windows `.cmd` execution is not tested.
- Read-only host detection.

## What is not built

- Dispatch to hosts beyond the Claude, Codex, dsh, and Goose adapters.
- A distributed or live two-host mesh; the current store is local.
- CMS, media, SEO, and Astro/Lumos delivery.
- A web dashboard.
- OS-level sandboxing. Host steps and shell steps are detected, not jailed.
- Remote deployment.
- Native Windows execution of `aperio.cmd`; the PowerShell installer is tested under `pwsh` on macOS.
- Automatic public release.

## Safety model

Aperio is deliberately conservative:

- no run without an approved plan;
- writes must stay inside the plan's allowed paths;
- protected paths such as `.git` and `.aperio` are refused;
- symlink components and parent traversal are refused;
- shell changes inside the scanned project are recorded as violations; writes outside the project or under excluded directories are not observed;
- a builder label cannot be the only reviewer label; this is not authenticated identity, so use `review --host` when a separate process matters;
- a task is `done` only after acceptance checks pass, the verified artifact and plan still match, and matching review evidence is confirmed.

The shell limitation is real. A command can change a file before Aperio detects it, and a write outside the scanned project is not detected at all. Do not treat path checks as an OS sandbox.

## Documentation

- `docs/PRD.md`: full product requirements and acceptance scenarios.
- `docs/DISCOVERY.md`: discovery domains, first questionnaire, facet profiles, evidence model, and module gates.
- `docs/ARCHITECTURE.md`: components, state layout, and safety boundaries.
- `docs/ROADMAP.md`: rebuild order.
- `docs/STATUS.md`: what was measured, not what is claimed.
- `docs/TESTING.md`: how to reproduce the tests.
- `docs/AGENTS.md`: roles and task handover.
- `docs/DECISIONS.md`: decisions that shaped v2.
- `docs/ARCHIVE.md`: where the old repository and documents live.
- `docs/REBUILD-REPORT-20261026.md`: what changed in the rebuild and what remains.
- `docs/EGM-ASSESSMENT.md`: what the Elephant-Goldfish Model is and what Aperio should adopt from it.

## License

MIT. See `LICENSE`.
