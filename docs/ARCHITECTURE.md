# Architecture

## Shape

Aperio v2 is a Python 3.10+ standard-library package with a small shell installer. There is no database, web service, or required external dependency.

```
install.sh
src/aperio/
  cli.py        command line and exit codes
  model.py      typed plan, task, ask, review records
  store.py      project state, atomic JSON, append-only events
  paths.py      relative-path validation and symlink checks
  policy.py     allowed paths, protected paths, review separation
  adapter.py    disposable-workspace host dispatch and change validation
  drift.py      deterministic documentation link and path checks
  mesh.py       local durable message store
  mediator.py   evidence-based task disposition
  runner.py     apply, detect changes, verify, review, finish, rollback
  handoff.py    owner-facing markdown from actual state
  hosts.py      read-only host detection
skill/aperio/   host skill instructions
examples/       runnable demo plan
tests/          unit, CLI, and installer tests
```

## State

A project initializes `.aperio/`:

```
.aperio/
  project.json      schema, id, name, policy
  asks.jsonl        append-only owner asks
  queue.json        tasks and statuses
  events.jsonl      append-only events
  plans/<id>.json   approved or draft plans
  evidence/<task>/  run, verification, and review records
  runs/<id>/        run manifest
  dispatch/<id>/    disposable host workspace and host evidence
  reviews/<id>/     brief-only host review workspace
  mesh/             local message store (SQLite)
  mediations/       mediator disposition records
  backups/<id>/     file snapshots for rollback
  handoff.md        most recent handoff
  lock              best-effort exclusive lock
```

State files are written to a temporary file in the same directory, flushed, and atomically replaced. The queue is one JSON document; asks and events are append-only JSONL.

## The loop

1. `init` creates the state directory and refuses to reinitialize it.
2. `ask` appends the owner's words. It does not rewrite earlier asks.
3. `plan` validates a JSON plan and creates a task in `planned`.
4. `approve` records the owner's identity and the explicit approval phrase. The task moves to `approved`.
5. `run`:
   - refuses an unapproved plan;
   - validates every declared path;
   - snapshots files that may change;
   - applies `write` steps and runs `run` steps with a timeout;
   - for a `host` step, copies the project into a disposable workspace, runs the host there, rejects changes outside the declared paths, and only then applies text changes to the real project;
   - hashes the project before and after;
   - records changed files and any change outside the declared writes;
   - saves evidence and moves the task to `applied` or `failed`.
6. `verify` runs the plan's acceptance commands and records pass or fail.
7. `review` records a named reviewer's `confirmed` or `refuted` verdict. With `--host`, it builds a brief-only workspace containing the plan, changed files, acceptance results, and handoff; the fresh host reviewer has no builder conversation and cannot edit. The reviewer must differ from the builder.
8. `done` requires a verified task and a confirmed review.
9. `handoff` writes a markdown report from the actual task, plan, evidence, and review.
10. `rollback` restores files captured before a run and removes files the run created.
11. `message` stores local durable messages with threads, recipient filters, read state, acks, and replies.
12. `mediate` records `CONFIRMED`, `REFUTED`, or `BLOCKED` from the run, verification, and review evidence. It does not replace a live host-to-host exchange.

## Task states

```
planned -> approved -> applied -> verified -> reviewed -> done
                  \-> failed
                  \-> rolled_back
```

A failed run can be inspected, rolled back, or replaced by a new plan. A failed verification cannot be reviewed or marked done.

## Path policy

- Paths are project-relative POSIX strings.
- Absolute paths, drive-qualified paths, NUL bytes, and `..` are rejected.
- Every existing component is checked for symlinks.
- `.git` and `.aperio` are protected by default.
- A plan must name at least one allowed path.
- A write must be inside an allowed path and outside protected paths.
- A `run` step must declare every expected write. Undeclared changes are violations.

This is a policy layer, not an OS sandbox. A shell command can write before detection. The evidence records the violation and the task is not verified.

## Evidence

Run evidence includes:

- task, plan, run, actor, start and finish time;
- each step's path or command, exit code, duration, stdout, stderr, and truncation flags;
- changed files and violations;
- backup manifest and limits.

Verification evidence includes every acceptance command, expected and actual exit code, stdout condition, pass or fail, and duration.

Review evidence includes reviewer, verdict, notes, and time.

## Host adapter

A `host` step names a host, a prompt, and the paths the host may change. The adapter:

1. copies the project into `.aperio/dispatch/<run-id>/workspace`, excluding `.git`, `.aperio`, dependency and cache directories;
2. runs the host in that copy with a bounded timeout and budget;
3. compares the copy before and after;
4. rejects any change outside the plan's allowed paths, binary files, or files over 1 MB;
5. applies only the accepted text changes to the real project, through the same snapshot and evidence path as other steps.

Supported adapters are `claude` (print mode, accept-edits, budget cap) and `goose` (`goose run --no-session --max-turns 8 --quiet`). Tests can point `APERIO_HOST_CLAUDE` or `APERIO_HOST_GOOSE` at a fake binary. The adapter does not get its own write path.

## Extension points

- **Host adapters:** add a read-only detector first, then a dispatcher that receives a plan and returns a patch or command result. Do not let an adapter bypass plan approval.
- **Plan producers:** a host can generate plan JSON. It still goes through the same approval and runner path.
- **Verification plugins:** add checks as acceptance commands, or add a typed check kind with its own evidence schema.
- **Storage:** the JSON layout is intentionally simple. If it moves to SQLite, keep atomic writes, append-only asks and events, and exportable evidence.

## Limits

- Host steps and shell steps are not confined by the operating system. Host prompts ask the host to stay in the workspace and avoid network access, but this is instruction-level, not a sandbox.
- The host runs with its own authentication and can read accessible files outside the workspace. Use a disposable project and a host account with the least privilege available.
- The change detector hashes project files and excludes `.git`, `.aperio`, dependency directories, and cache directories.
- Snapshot limits are 5,000 files and 50 MB. A larger plan must narrow its scope.
- Host dispatch is text-only. Binary changes are rejected.
- The lock is best-effort on Unix and a no-op where `fcntl` is unavailable.
- Host detection reports presence and version, not authentication, permission, or model access.
