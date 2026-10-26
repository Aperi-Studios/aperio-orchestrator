---
name: aperio
description: Use when a request needs Aperio's bounded project loop: record the ask, plan, approve, apply, verify, review, and hand off with evidence.
---

# Aperio v2

Aperio is a bounded project loop, not an autonomous shell. Every change goes
through an ask, an approved plan, a recorded run, acceptance checks, and an
independent review.

## Start of a session

If `/aperio` is invoked without a complete request, ask one question at a time
and stop after each answer. Start with the branch, then the outcome:

1. Is this a new build, a change or redesign of something existing, a repair, an audit, a migration, or SEO/growth work?
2. When this is finished, what should be different, and why does it matter now?
3. What exists today: a URL, a folder, a repository, screenshots, or nothing?
4. Who is the primary person this is for, and what one action must they be able to take?
5. What are the three must-haves for the first release, and what is explicitly not included?
6. How will you know it worked?
7. What is fixed: deadline, budget, brand, technology, hosting, legal or privacy rules, languages, or accessibility target?
8. Who owns the domain, hosting, repository, content, analytics, and final approval? What access exists, without sharing any secret value?
9. What evidence can you show: an existing URL, analytics or Search Console export, brand assets, examples, screenshots, or an error message?
10. What should the project be called?

Do not run host detection, initialize a project, write a plan, or touch files
until the ask is recorded. Do not present a host inventory as proof that a
reviewer is available; presence is not permission.

For an existing URL or repository, inspect it read-only before asking a
question it can answer. Do not plan until the outcome, current state,
must-haves, non-goals, success measure, and access owner are known. If the owner
cannot answer, record `unknown` with the risk; do not invent an answer. Never
ask for a password, API key, card number, or recovery code.

## Commands

Before running these, check `type aperio`. If it is a shell function, use `command aperio` or `$HOME/.local/bin/aperio`; a shell wrapper must not shadow the installed CLI.

```
aperio init . --name "Project name"
aperio ask "What the owner wants" --source owner
aperio plan plan.json
aperio approve <plan-id> --by owner --confirm "I approve this plan"
aperio run <task-id> --actor builder
aperio verify <task-id>
aperio review <task-id> --host claude
# manual fallback: aperio review <task-id> --reviewer <different-reviewer> --verdict confirmed
aperio done <task-id>
aperio rollback <task-id> --yes
aperio handoff <task-id> --print
aperio drift
aperio status --json
aperio message send --from builder --to reviewer --body "please review" --task <task-id>
aperio mediate <task-id>
aperio hosts
```

## Plan file

```json
{
  "title": "Short outcome",
  "request": "The owner's request, in their terms.",
  "builder": "builder-name",
  "allowed_paths": ["src/", "tests/"],
  "steps": [
    {"id": "write-file", "kind": "write", "path": "src/a.py", "content": "..."},
    {"id": "build", "kind": "run", "command": "python3 build.py", "cwd": ".", "writes": ["dist/"]}
  ],
  "acceptance": [
    {"id": "test", "command": "python3 -m pytest -q", "expected_exit": 0}
  ]
}
```

## Hard rules

1. Do not run an unapproved plan.
2. Do not edit outside `allowed_paths`.
3. Do not use the builder as the only reviewer.
4. Do not call a task done without passing acceptance checks and a confirmed review.
5. Do not put credentials, client identifiers, or private data in the plan, evidence, or handoff.
6. Do not claim a deployment, link, or screenshot that was not actually produced.
7. A shell step is not OS-sandboxed. Declare every expected write; undeclared changes are recorded as violations.
8. If a gate fails, stop and report the exact command, exit code, and result.

## Flow

1. Record the ask exactly.
2. Inspect the target before planning.
3. Write the smallest plan that satisfies the ask.
4. Ask the owner to approve. Do not self-approve.
5. Apply the plan and read the evidence.
6. Run the acceptance checks.
7. Ask a different host or reviewer for a verdict.
8. Finish only after a confirmed review.
9. Generate the handoff and state what remains unverified.
