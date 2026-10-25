# Host proofs

These are commands that were run on this machine on 2026-10-26, with the output
that matters. They are local evidence, not a hosted benchmark.

## Host versions

| Host | Version | Result |
|---|---|---|
| Claude Code | `2.1.310` | Build and review worked |
| Codex CLI | `codex-cli 0.163.0-alpha.11.2` | Build and review worked |
| Goose | `1.55.0` | Command path exists; live run returned HTTP 500 from the local bridge |

## Proof A: Codex builds, Claude reviews

Fresh temporary project. Plan declared one host step and one write:
`site/index.html`.

```text
task-116b1d078e  plan-bc1537a9fe  planned
run-d86056766a  applied
changed: site/index.html
verify-8191b4901e  passed
  check: ok (exit 0)
task-116b1d078e  review confirmed by claude
task-116b1d078e  done
```

Evidence:

- Run: `run-d86056766a`, host `codex`, exit 0, one create, 15,172 bytes.
- File sha256: `0c973bba6218cea05fe60f7b195c3980d2c8e0c24f3c3b7f66b3deaecfe50618`.
- Review: `review-5fcf72b5e9`, reviewer `claude`, verdict `confirmed`, no findings.
- The reviewer saw the brief and tree/site/index.html only.
- The handoff recorded the host step, the acceptance check, the changed file, and
  the reviewer.

The first attempt failed honestly with
`violation: host is not installed on PATH: codex`; the adapter was changed to
resolve the bundled Codex application path, and the successful run above
followed.

## Proof B: Claude and Codex use the local message store

A real Claude process was given a task message in the local store. It ran the
installed Aperio command, read the message, and sent a reply.

```text
owner -> claude-builder: Please acknowledge this message ...
1  thread-2994ec87ec  owner -> claude-builder: Please acknowledge ...
claude-builder -> owner: ACK from claude-builder
```

The reply was stored as message `2`, with `reply_to: 1` and the same task id.

A separate real Codex process did the same in another project:

```text
1  thread-82dd870518  owner -> codex-builder: Please acknowledge ...
codex-builder -> owner: ACK from codex-builder
```

The Codex reply was stored as message `2` in that project, with `reply_to: 1`.
The owner inbox query returned it.

This proves two host products can use the durable local store in separate
exchanges. It does not prove a direct two-host thread or a distributed
transport.

## Proof C: Claude builds through the same bounded path

An earlier real Claude host run produced `site/index.html`, passed acceptance,
was reviewed by a fresh Claude process, and finished with `done`. The run id
recorded in the project docs is `run-2d57f0f091`.

## Proof D: Codex reviews a verified task

A one-file task was applied and verified through the normal path, then reviewed
by a fresh Codex process with a read-only sandbox and only the brief plus the
changed file.

```text
task-1b8dcd0ca2  review confirmed by codex
task-1b8dcd0ca2  done
```

Evidence: review `review-138f0f9a9f`, verdict `confirmed`, findings `[]`. The
reviewer saw `tree/site/index.html` and the brief; it did not see a builder
conversation.

## What these proofs do not cover

- No OS sandbox. Host changes outside the plan are detected after execution,
  not prevented at the kernel level.
- No native Windows execution.
- No live Goose run; the local bridge failed.
- No distributed or two-product live host exchange over the message store.
- No CMS, SEO, or Astro/Lumos delivery.
