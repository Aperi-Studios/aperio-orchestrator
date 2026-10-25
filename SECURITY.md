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

A shell step in an approved plan can change files before the runner detects the change. Treat plans from untrusted sources as code. Review every plan before approval.

## Known security boundaries

- Path checks stop traversal and symlink escapes.
- Protected paths such as `.git` and `.aperio` are refused.
- Undeclared writes are detected after execution and recorded as violations.
- A task cannot be marked done without a confirmed independent review.
- Host detection does not authenticate a host or prove model access.

See `docs/ARCHITECTURE.md` for the full boundary.
