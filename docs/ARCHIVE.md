# Archive

The pre-v2 repository is preserved locally. It is not the source of truth for v2, and it is not part of the public v2 tree.

## Local archive

- Directory: `~/Desktop/Aperio-Orchestrator-pre-v2-20261026`
- Documents and reports: `docs-and-reports.tar.gz` (1.8 MB)
- Git bundle of all refs: `repository.bundle` (9.6 MB)
- Checksums: `SHA256SUMS`

The bundle and tarball were created before the v2 rebuild. Keep them private: the old tree contains client material and historical reports.

## What was archived

- top-level reports and user guides;
- `docs/audits/`;
- `reports/`;
- the historical `Shahid/` reports and generated PRDs;
- `SPS2-PROJECT-COMPLETION-RECORD/`.

Raw owner asks and the small canonical v2 document set are not part of the old archive. If a future migration needs an old requirement, import it deliberately into `docs/PRD.md` or a dated decision record.

## Why the old URL is not reused

The old repository history contained client identifiers. A scrub reduced the current history, but old Git objects can remain reachable on a remote. Publishing a fresh repository avoids depending on a remote garbage collection. The old repository stays private.

## Recovery

```bash
git clone ~/Desktop/Aperio-Orchestrator-pre-v2-20261026/repository.bundle aperio-old
```

Verify the bundle before cloning:

```bash
shasum -a 256 -c SHA256SUMS
```
