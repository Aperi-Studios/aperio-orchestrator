# Aperio Orchestrator v2

Aperio turns an owner request into a bounded, approved plan, applies it, runs acceptance checks, requires an independent review, and writes evidence and a handoff.

**Status: early rebuild.** The core loop and installer work. Host dispatch, mesh chat, CMS delivery, and SEO delivery are not built yet. Do not describe this as feature-complete.

## Why this rebuild exists

The previous repository accumulated a large layer of reports, audits, generated PRDs, and status documents that did not reliably match the code. This repository starts with a small canonical documentation set and a tested core.

## Quick start

```bash
git clone https://github.com/Aperi-Studios/aperio-orchestrator.git
cd aperio-orchestrator
./install.sh
aperio --version
```

The installer copies the package to `~/.local/share/aperio`, creates `~/.local/bin/aperio`, and installs the skill under `~/.claude/skills/aperio`. It does not edit host settings, use sudo, or download anything.

To test without installing:

```bash
PYTHONPATH=src python3 -m aperio --help
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## The loop

```bash
aperio init . --name "My project"
aperio ask "Build a one-page site with a working contact form" --source owner
aperio plan plan.json
aperio approve <plan-id> --by owner --confirm "I approve this plan"
aperio run <task-id> --actor builder
aperio verify <task-id>
aperio review <task-id> --reviewer qa --verdict confirmed
aperio done <task-id>
aperio handoff <task-id> --print
```

A plan is JSON. It declares allowed paths, exact write steps, bounded run steps, and acceptance checks.

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

## What works now

- Project initialization and append-only owner asks.
- Plan creation, explicit approval, bounded writes, and shell steps with timeouts.
- Change detection for writes outside the declared plan.
- Acceptance checks and recorded evidence.
- Independent review enforcement by reviewer name.
- Rollback of files captured before a run.
- Handoff generation from actual state.
- Installer, idempotent reinstall, dry run, and uninstall.
- Read-only host detection.

## What is not built

- Dispatch to Claude, Codex, Goose, or other hosts.
- Live mesh messaging.
- CMS, media, SEO, and Astro/Lumos delivery.
- A web dashboard.
- OS-level sandboxing. Shell steps are detected, not jailed.
- Remote deployment.
- Automatic public release.

## Safety model

Aperio is deliberately conservative:

- no run without an approved plan;
- writes must stay inside the plan's allowed paths;
- protected paths such as `.git` and `.aperio` are refused;
- symlink components and parent traversal are refused;
- shell changes outside declared writes are recorded as violations;
- a builder cannot be the only reviewer;
- a task is `done` only after acceptance checks pass and a review is confirmed.

The shell limitation is real. A command can change a file before Aperio detects it. Do not treat path checks as an OS sandbox.

## Documentation

- `docs/PRD.md`: full product requirements and acceptance scenarios.
- `docs/ARCHITECTURE.md`: components, state layout, and safety boundaries.
- `docs/ROADMAP.md`: rebuild order.
- `docs/STATUS.md`: what was measured, not what is claimed.
- `docs/TESTING.md`: how to reproduce the tests.
- `docs/AGENTS.md`: roles and task handover.
- `docs/DECISIONS.md`: decisions that shaped v2.
- `docs/ARCHIVE.md`: where the old repository and documents live.

## License

MIT. See `LICENSE`.
