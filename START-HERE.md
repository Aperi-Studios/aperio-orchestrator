# START HERE

This repository is Aperio v2, a clean rebuild. The old repository is preserved separately and is not the source of truth.

## If you are the owner

1. Install: `./install.sh`
2. Create a project: `aperio init . --name "Project"`
3. Record what you want: `aperio ask "..." --source owner`
4. Review the plan file. Approve it only if it is correct:
   `aperio approve <plan-id> --by owner --confirm "I approve this plan"`
5. Run, verify, review, and hand off with the commands in `README.md`.

Do not approve a plan you have not read. The approval phrase is deliberately explicit.

## If you are an agent

Read these first, in order:

1. `docs/STATUS.md` for measured current state.
2. `docs/AGENTS.md` for roles and task boundaries.
3. `docs/PRD.md` for required behavior.
4. `docs/ARCHITECTURE.md` for the implementation map.
5. `docs/TESTING.md` for the verification commands.

Then run:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Rules that are not optional:

- Do not run an unapproved plan.
- Do not write outside the plan's allowed paths.
- Do not review your own work as the only reviewer.
- Do not call a task done without passing acceptance checks and a confirmed review.
- Do not claim a host, CMS, deployment, or public release works unless you ran it.
- Do not put credentials or client data in the repository.

## Current state

The core loop and installer are tested. Host dispatch, mesh chat, CMS, SEO, and deployment are roadmap items. See `docs/STATUS.md` for the exact evidence.
