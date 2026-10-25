# Security

## Supported versions

This is a pre-release rebuild. Security fixes apply to the `main` branch only.

## Report a vulnerability

Do not open a public issue for a vulnerability, leaked credential, or client-data exposure. Report it privately to the repository owner, Shahid, through the contact method on the GitHub profile. Include the affected path, a reproduction, and the impact. Do not include a live secret in the report.

## Scope

Aperio v2 is a local project tool. It:

- does not run a network service;
- does not deploy;
- does not store credentials;
- does not claim an OS sandbox for shell steps.

A shell step in an approved plan can change files before the runner detects the change. Treat plans from untrusted sources as code. Review every plan before approval. An acceptance check is intended to inspect the result, not change it; if it changes a project file, verification fails.

## Known security boundaries

- Path checks refuse lexical traversal, absolute paths, and symlinked components for paths resolved through the project path helper, including dangling symlinks.
- A project whose `.aperio` state directory is a symlink is refused.
- Host changes are rejected if they are outside the plan, outside the host step's declared writes, or are symlinks. The adapter reads only regular files after that check. If a host reaches the real project during its run, the runner detects the change and fails the run; the OS does not prevent the write.
- Protected paths such as `.git` and `.aperio` are refused for plan writes.
- Undeclared writes are detected after execution inside the scanned project tree. Writes to excluded directories, outside the project, or to paths the scanner cannot read are not observed.
- Steps that change the project state used for approval, queue, plans, or evidence fail the run or verification.
- A task cannot be marked done without a confirmed review whose reviewer label differs from the builder label. Labels are self-reported; this is not authenticated identity.
- Acceptance checks that mutate a project file fail verification. Newly created files are removed; modified or deleted files are reported but not restored.
- Host detection does not authenticate a host or prove model access.

See `docs/ARCHITECTURE.md` for the full boundary.
