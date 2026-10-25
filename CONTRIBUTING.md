# Contributing

Aperio is a small, evidence-first project. Keep changes bounded.

## Before a change

1. Read `START-HERE.md` and `docs/AGENTS.md`.
2. Record the request and the acceptance checks.
3. Work on a branch. Do not push to `main` without review.
4. Do not add a dependency without a written reason, license, and portability check.

## Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
bash -n install.sh
```

All tests must pass. If you add behavior, add a test that fails when the behavior is broken.

## Review

- A builder does not approve its own work as the only reviewer.
- Review the diff, not the summary.
- State what was not tested.
- Do not claim a host, CMS, deployment, or public release works unless it was run.

## Secrets and client data

Never commit credentials, tokens, client identifiers, private URLs, or personal data. If a secret is committed, stop, remove it from the working tree, and report it privately. Do not rewrite public history without the owner's approval.

## Documentation

Keep one canonical PRD (`docs/PRD.md`), one status page (`docs/STATUS.md`), one architecture document, and one roadmap. Do not add a second queue, handoff, or generated PRD.
