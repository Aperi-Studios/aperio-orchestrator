---
name: aperio
description: Use when a request needs Aperio's bounded project loop: record the ask, plan, approve, apply, verify, review, and hand off with evidence.
---

# Aperio v2

Aperio is a bounded project loop, not an autonomous shell. Every change goes
through an ask, an approved plan, a recorded run, acceptance checks, and an
independent review.

## Start of a session

Ask one question at a time. Give numbered choices whenever the answer can be
enumerated. Always include a **not sure — research and recommend** choice and an
**other** choice. Use multi-select when more than one answer can apply.

Start with the outcome:

1. Which outcome matters most? Choose one or more:
   1. More customers, leads, or sales
   2. Save time or reduce manual work
   3. Fix a problem or reduce errors
   4. Launch a new product or service
   5. Improve search visibility
   6. Improve speed, accessibility, or usability
   7. Reduce risk, compliance, or cost
   8. Not sure — research and recommend
   9. Other — type it

Then continue, one at a time:

2. What exists today?
   1. Nothing
   2. A live URL
   3. A folder or repository
   4. A live site and a repository
   5. Screenshots or documents only
   6. Not sure — research and recommend
   7. Other — type it

3. Which labels apply? Choose all that apply:
   1. New build
   2. Change or extend
   3. Redesign
   4. Repair
   5. Audit
   6. Migration or replacement
   7. SEO or growth
   8. Performance or accessibility
   9. Other — type it

4. Who is the primary user?
   1. Consumers or the public
   2. Businesses or clients
   3. An internal team
   4. Members or a community
   5. Not sure — research and recommend
   6. Other — type it

5. What are the three must-haves for the first release, and what is explicitly not included?

6. How will you know it worked?
   1. More leads, sales, or bookings
   2. Less manual work or fewer errors
   3. A launch by a specific date
   4. Better search visibility
   5. Better speed, accessibility, or usability
   6. Not sure — research and recommend
   7. Other — type it

7. What is fixed? Choose all that apply:
   1. Deadline
   2. Budget
   3. Brand or design
   4. Existing technology or stack
   5. Hosting or domain
   6. Legal, privacy, or compliance
   7. Languages or localization
   8. Accessibility target
   9. Nothing is fixed
   10. Not sure — research and recommend

8. Who owns the domain, hosting, repository, content, analytics, and final approval?
   1. I own everything
   2. My team owns it
   3. A client owns it
   4. Not sure — research and recommend
   5. Other — type it

9. What evidence can you show? Choose all that apply:
   1. An existing URL
   2. A repository or folder
   3. Analytics or Search Console
   4. Brand assets or examples
   5. Screenshots, logs, or error messages
   6. Nothing yet
   7. Not sure — research and recommend

10. What should the project be called?

Do not force one project type. Record every applicable facet; a project can be
a redesign plus SEO plus CMS plus migration at the same time. Do not run host
detection, initialize a project, write a plan, or touch files until the ask is
recorded. Do not present a host inventory as proof that a reviewer is
available; presence is not permission.

For an existing URL or repository, inspect it read-only before asking a
question it can answer. Do not plan until the outcome, current state,
must-haves, non-goals, success measure, and access owner are known. If the owner
cannot answer, record `unknown` with the risk; do not invent an answer. Never
ask for a password, API key, card number, or recovery code.

### When the owner does not know

Do not repeat the question. Do bounded research:

1. Inspect available assets read-only.
2. Research two or three credible options, references, or competitors.
3. Compare them on fit, cost, time, risk, maintenance, and evidence.
4. Recommend one in plain language, with assumptions and trade-offs.
5. Ask the owner to accept, change, or defer the recommendation.
6. Record the decision and its evidence.

Never silently choose for the owner. If research needs a paid service, account,
or purchase, ask first. If there is no information at all, start with a small
discovery: examples, constraints, and what a bad outcome would look like.

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
