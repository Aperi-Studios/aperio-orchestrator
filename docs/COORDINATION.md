# Builder/auditor coordination channel

The builder and the independent auditor use Aperio's durable local message
store as their shared record. It is not a chat UI and not a network transport;
it is a SQLite mailbox inside the project state, so messages survive restarts and
both sides can cite the same message id.

## Setup

The repository itself must be an initialized Aperio project:

```bash
cd /Users/maryamahad/Desktop/Aperio-Orchestrator-v2
PYTHONPATH=src python3 -m aperio --project . init . --name "Aperio Orchestrator"
```

The channel id is `builder-auditor`. The two roles are `builder` and `auditor`.

## Send

```bash
cd /Users/maryamahad/Desktop/Aperio-Orchestrator-v2
PYTHONPATH=src python3 -m aperio --project . message send \
  --from builder --to auditor --thread builder-auditor \
  --kind task --body "What to verify, with file/line evidence and the commit range."
```

Use `--kind review` for a reply to a reviewed delta and `--reply-to <id>` to keep
the thread traceable.

## Read and acknowledge

```bash
PYTHONPATH=src python3 -m aperio --project . message read \
  --to auditor --thread builder-auditor --json
PYTHONPATH=src python3 -m aperio --project . message ack <id> --by auditor
```

`ack` also records `read_at`. A message is not handled until it is acknowledged.

## Rules

- The builder sends a bounded delta: commit ids, exact files, the command that
  proves the claim, and what is still `needs_validation`.
- The auditor does not edit, commit, or push. It replies with `fixed`,
  `not fixed`, or `needs_validation` and file/line evidence.
- If they disagree, they resolve it in this thread before either side changes
  code.
- The watchdog includes the auditor's unread count in its output, so a new
  builder message wakes the auditor even when the Git tree is unchanged.
- The store is local and not cryptographically authenticated. Reviewer identity
  is a label, not proof of identity.
