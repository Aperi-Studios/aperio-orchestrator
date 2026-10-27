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
- does not claim an OS sandbox for host steps. Shell and read steps are optionally sandboxed when a plan sets `sandbox: true`; if no supported backend exists the run fails closed.

A shell step in an approved plan can change files before the runner detects the change unless the plan requests `sandbox: true` and a supported OS backend is available. Treat plans from untrusted sources as code. Review every plan before approval. An acceptance check is intended to inspect the result, not change it; if it changes a project file, verification fails.

## Known security boundaries

- Path checks refuse lexical traversal, absolute paths, and symlinked components for paths resolved through the project path helper, including dangling symlinks.
- A project whose `.aperio` state directory or any state subdirectory/file is a symlink is refused.
- Host changes are rejected if they are outside the plan, outside the host step's declared writes, or are symlinks. The adapter reads only regular files after that check. If a host reaches the real project during its run, the runner detects the change and fails the run; the OS does not prevent the write.
- Protected paths such as `.git` and `.aperio` are refused for plan writes.
- Undeclared writes are detected after execution inside the scanned project tree. Writes to excluded directories, outside the project, or to paths the scanner cannot read are not observed. A plan with `sandbox: true` narrows this for shell/read steps; host steps remain outside the OS boundary.
- Steps that change the project state used for approval, queue, plans, or evidence fail the run or verification.
- Verification records an artifact digest. Review and finish refuse if the project no longer matches that digest, and a new run or verification clears the previous review.
- A task cannot be marked done without a confirmed review whose reviewer label differs from the builder label. Labels are self-reported; this is not authenticated identity.
- A review host is asked not to edit. The review runner fingerprints the project before and after and refuses a verdict if anything changed; this is detection, not an OS sandbox. A detected change is reported, not restored.
- Acceptance checks that mutate a project file fail verification. Newly created files are removed; modified or deleted files are reported but not restored.
- Shell commands run in a new process group and a timeout kills the group. A command that detaches itself can still outlive the runner.
- Host detection does not authenticate a host or prove model access.
- `aperio audit` is a source-anchored ledger, not a vulnerability scanner. It never executes target code, and `needs_validation` findings carry no severity. The ledger and report are local files and are not cryptographically signed or tamper-evident; a reviewer still has to verify each confirmed finding.

See `docs/ARCHITECTURE.md` for the full boundary.
