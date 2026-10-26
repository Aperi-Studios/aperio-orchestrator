# Security audit ledger

`aperio audit` records a bounded source review. It is not a vulnerability scanner,
and it does not execute target code.

## Files

An audit lives in `.aperio/audits/<audit-id>/`:

| File | Purpose |
|---|---|
| run metadata | repo, scope, profile, source ref, run status, limits |
| coverage ledger | every planned source unit and its review status |
| findings | confirmed, unresolved, and rejected findings |
| report | generated summary |
| findings detail | confirmed findings only |
| needs-validation | unresolved findings with no severity |

Coverage is capped at 500 files. When the cap is reached, the ledger records
`truncated: true` and the report says the scope is incomplete.

The `--profile` value is a recorded planning hint. It does not add or remove
checks by itself; the host still has to review the units and record the result.

## Commands

```bash
aperio audit start --scope src --profile quick
aperio audit brief
aperio audit ingest --file findings.json
aperio audit add --title "..." --status confirmed --path src/app.py --line 12 \
  --severity high --boundary "..." --evidence "src/app.py:12 ..."
aperio audit add --title "..." --status needs_validation --path src/app.py \
  --evidence "The deployment configuration is not in this repository."
aperio audit unit --unit-id unit-0001 --status checked
aperio audit validate
aperio audit report
aperio audit status --json
```

`audit add` accepts `--unit unit-0001` or resolves the unit from `--path` when
exactly one unit matches.

## Host brief and ingest

`aperio audit brief` writes an audit brief with the exact coverage units and
the JSON output shape. A host can return one object:

```json
{
  "schema": 1,
  "findings": [
    {
      "title": "short title",
      "status": "confirmed",
      "path": "src/app.py",
      "line": 12,
      "severity": "high",
      "boundary": "what crosses what",
      "evidence": "src/app.py:12 ..."
    }
  ]
}
```

`aperio audit ingest --file findings.json` validates every record before it
writes anything. One invalid record rejects the whole batch, so the ledger never
contains a half-imported set. Unknown fields are rejected rather than ignored.

## Rules

- Every finding must reference an existing coverage unit. A finding path must
  match that unit and stay inside the project.
- **confirmed** requires a coverage unit, a boundary, a severity, a positive
  source line, and evidence containing that path. Do not infer exploitability
  from a suspicious string.
- **needs_validation** must not have a severity. State the missing fact.
- **rejected** must not have a severity.
- Every finding must reference an existing coverage unit.
- A finding path must be relative and stay inside the project.
- `validate` rejects unknown statuses, duplicate IDs, orphan findings, unsafe
  paths, missing evidence, and malformed line numbers.
- `report` refuses an invalid ledger. It marks the run `incomplete` while units
  remain `planned`, `candidate`, or `deferred`, while coverage is truncated, or
  when the source changed since the audit started. `aperio audit report` exits
  1 in those cases and 0 only for a complete report.

## Handoff

`aperio handoff` always includes a `Security audit` section. It says when no
source audit was recorded, when the latest ledger is invalid, and when coverage
or the source is incomplete. `aperio status` reports the latest audit in both
human and `--json` output.

## Limits

- The finder and the verifier should be different hosts. The ledger records
  findings; it does not authenticate who recorded them.
- A confirmed finding is not proof of exploitability.
- The files are local and not cryptographically signed or tamper-evident.
- The report is not a whole-repository security guarantee.
