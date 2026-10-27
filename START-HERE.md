# START HERE

This is the entry point for Aperio Orchestrator v2. The repository is the source of
truth; do not rely on a previous chat or an agent's memory.

## Read in this order

1. **`HANDOFF.md`** — current state, commands, verification, boundaries, and the
   incoming-agent checklist.
2. **`docs/STATUS.md`** — measured implementation status and known limits.
3. **`docs/OWNER-REQUESTS.md`** — the owner's substantive requests and where each
   is recorded.
4. **`docs/PRD.md`** — product requirements and scope decisions.
5. **`docs/ARCHITECTURE.md`** — module map and state layout.
6. **`docs/AGENTS.md`** — roles, task format, and handover rules.
7. **`docs/TESTING.md`** — exact verification commands.

## If you are the owner

```bash
./install.sh
aperio init . --name "Project"
aperio ask "What you want" --source owner
```

Use `README.md` for the full command sequence. Do not approve a plan you have not
read. The approval phrase is deliberately explicit.

## If you are an agent

Run the baseline before changing anything:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
ruff check src tests
PYTHONPATH=src python3 -m aperio drift
git status --short --branch
```

Rules that are not optional:

- Do not run an unapproved plan.
- Do not write outside the plan's allowed paths.
- Do not review your own work as the only reviewer.
- Do not call a task done without passing acceptance checks and a confirmed review.
- Do not claim a host, CMS, deployment, or public release works unless you ran it.
- Do not put credentials, client data, or local `.aperio` state in the repository.

## Scope in one paragraph

Aperio is a local, stack-neutral orchestrator: ask, discover, learn, todo, plan,
approve, apply, verify, independent review, done, handoff. CMS/SEO delivery and
deployment execution belong to a target project, not Aperio. Optional shell
sandboxing, toolchain installation, secret scanning, a read-only dashboard, queue
recovery, checkpoints, and resume are implemented. See `HANDOFF.md` for the exact
verified baseline and the deferred/out-of-scope list.
