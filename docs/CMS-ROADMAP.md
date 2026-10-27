# Custom CMS design and delivery roadmap

**Status: separate target-project method. Not an Aperio feature. No CMS is implemented in Aperio. No framework is selected yet.**

This document defines how a **target project** should design and build a complete
custom CMS. It is not a feature list for Aperio. The framework, database, media
store, and hosting model are **outputs of the project discovery**, not defaults
chosen in advance.

## 1. Decision order

Do not start with "which framework?" Start with the operating constraints:

1. **Content and jobs.** What content types exist, who edits them, how often,
   and what must be published vs private?
2. **Deployment and operations.** Who runs the server? VPS, serverless, shared
   cPanel, or static hosting? Who handles TLS, backups, monitoring, and
   incidents?
3. **Data and media.** Where does content live? Where do uploads live? What is
   the backup and restore target?
4. **Access and workflow.** Who are the roles? Who may edit, review, publish,
   delete, restore, or export? Is approval required before publish?
5. **Locales and discovery.** One language or several? RTL? SEO-critical?
   Machine translation allowed, or human-only?
6. **Integrations.** Payments, CRM, email, analytics, forms, auth provider,
   search, or none.
7. **Stack.** Only now choose the renderer, CMS runtime, database, and media
   adapter.
8. **Proof.** A real target project must pass edit, save, publish, deny,
   rollback, render, SEO, accessibility, backup, and restore checks.

The stack decision is recorded as a short decision record with the constraints
that drove it. A later constraint change reopens the decision; it does not get
silently overridden.

## 2. Deployment profiles

| Profile | Fits | Renderer | Data | Media | Ops burden | Main risks |
|---|---|---|---|---|---|---|
| VPS with Docker/PM2 | Full control, predictable traffic, custom backend, long-lived CMS | Astro, Next.js, Nuxt, SvelteKit, Django/FastAPI, Laravel, Go | PostgreSQL or SQLite for a small single-node CMS | Local disk with backups, or S3-compatible storage | TLS, patching, backups, monitoring are ours | Single point of failure; backup discipline is mandatory |
| Serverless | Low-ops marketing sites, preview-heavy workflows, spiky traffic | Astro on a serverless adapter, Next.js, SvelteKit | Managed Postgres, D1/Turso, or a managed API | R2/S3, never local ephemeral disk | Low, but vendor limits and cold starts apply | Connection limits, vendor lock-in, preview/publish differences |
| Shared cPanel | Client already has PHP hosting and wants no new ops | Laravel/PHP or static export | MySQL/MariaDB | Local uploads | Low if the host is competent | Weak isolation, limited process control, deployment via file copy |
| Static + small API | Content-heavy site with no request-time rendering | Static HTML/Astro export | JSON files or a tiny API database | Static assets, object storage | Lowest | Rebuild/publish latency, no request-time personalization |
| Hybrid | Public site static, admin/API separate | Static renderer + CMS API | Managed Postgres or SQLite service | Object storage | Medium | Two deploy surfaces to monitor |

### Deployment decision tree

- **"The client has no server operator and traffic is modest."**
  Prefer serverless/static public output and a managed database. Do not put a
  CMS on an unmonitored VPS just because it is cheap.
- **"The client requires a VPS or already has one."**
  Use Docker or a process manager, a reverse proxy with TLS, a database with
  scheduled logical backups, object storage for media, and a documented restore
  drill. A VPS without a restore drill is not a deployment plan.
- **"The client is on cPanel and will not move."**
  Use the stack the host can actually run (usually PHP/MySQL) or deliver static
  output. Do not force a Node server onto a host that cannot supervise it.
- **"The site is static and content changes are infrequent."**
  Prefer a JSON-backed CMS with a build/publish step; do not pay for a
  request-time CMS the project does not need.
- **"The project needs accounts, payments, or live data."**
  Treat it as an application, not a brochure site. Choose a runtime and database
  that support transactions, migrations, and backups.

## 3. Stack selection matrix

Score each candidate against the project, not against fashion. Weights are
project-specific; the default weights below are only a starting point.

| Criterion | Weight | What "good" means |
|---|---|---|
| Deployment fit | 25% | The stack runs cleanly on the chosen host with the available ops skill |
| Content workflow | 20% | Draft, review, publish, revision, rollback, and scheduled publish are natural |
| Data integrity | 15% | Transactions, constraints, migrations, and backup/restore are practical |
| Media handling | 10% | Upload validation, derivatives, storage, and CDN path are clear |
| SEO and rendering | 10% | Built output is crawlable, fast, and metadata is first-class |
| Security model | 10% | Auth, RBAC, CSRF, output encoding, and audit are implementable |
| Team maintainability | 5% | The client or maintainer can operate it without the original builder |
| Cost and lock-in | 5% | Hosting, database, and media costs are understood and portable |

Candidate families (not a selection):

- **Astro** — strong content sites and static/SSR output; pair with SQLite for a
  small single-node CMS or Postgres for a larger one.
- **Next.js** — strong when the site is really an application; pair with
  Postgres and a managed auth/session model.
- **Nuxt / SvelteKit** — same decision shape as Next.js; choose when the team
  already knows the framework.
- **Laravel/PHP** — strong cPanel/shared-host fit, mature auth and queues.
- **Django/FastAPI** — strong Python data/ops fit; Django brings admin and auth,
  FastAPI needs those pieces assembled deliberately.
- **Go** — strong single-binary VPS deployment; more assembly for CMS UX.
- **Vanilla HTML + JSON CMS** — strong static fit; weakest for concurrent
  editors, permissions, and large media libraries.

A stack is approved only after the decision record names the host, runtime,
database, media store, auth model, and backup target.

## 4. CMS architecture

### 4.1 Content model

The CMS owns a model, not a pile of HTML files.

- **Content types / collections.** Article, page, product, service, project,
  author, category, inquiry, media asset, redirect, setting.
- **Pages and sections.** A page has an ordered list of approved sections; a
  section has a type, a variant, and content props. Layout belongs to the
  renderer, not the editor.
- **Global settings.** Company name, logo, contact details, social links,
  tracking IDs, default SEO, and legal text.
- **Inquiries.** Name, contact, message, source page, consent, status, notes,
  and export metadata.
- **Media.** Original file, MIME, dimensions, alt text, focal point, derivatives,
  storage key, and checksum.
- **Users and roles.** Owner, admin, editor, reviewer, author, viewer; role
  permissions are explicit, not implied by UI.
- **Revisions and audit.** Every content mutation creates a revision before it
  is saved; every admin action appends an audit entry (actor, role, action,
  target, time).

### 4.2 Layers

```text
public renderer  ->  read model / cache  ->  published content
admin UI         ->  API                  ->  domain service
visual editor    ->  API                  ->  same domain service
media pipeline   ->  validation/derivatives -> object/local storage
domain service   ->  validation -> repository -> database
domain service   ->  revision + audit + outbox/job
```

The admin and the public renderer must read the same domain service. A second
write path for "quick fixes" is a defect.

### 4.3 Content lifecycle

```text
draft -> in_review -> scheduled -> published -> archived
                 \-> rejected (with reason)
```

Rules:

- Draft content is excluded from public rendering and sitemaps.
- Publishing goes through one state machine; no direct writes to the status
  field.
- Every publish, unpublish, archive, and restore creates a revision and an
  audit entry.
- A rollback restores content, not unrelated settings or user data.
- A whole-store restore captures the pre-restore state first, so the restore is
  itself undoable.
- Deleting content is soft-delete plus retention policy, never an immediate
  destructive purge unless the owner explicitly confirms.

### 4.4 Editing and design

- **Visual editing is optional but, when selected, measured.** Every editable
  visible surface has a stable key; a page with an unkeyed visible string fails
  coverage. A click opens an inspector; it never navigates away.
- **Block registry.** Approved blocks and variants only. Content edits cannot
  inject CSS, arbitrary HTML, hex colours, or fixed pixel type.
- **Design system.** Tokens for colour, type, spacing, radius, and motion.
  Lumos is one option, not a universal requirement. Do not mix token systems.
- **Preview.** Preview uses the real renderer with the draft read model and
  `noindex`; it must not leak draft content to crawlers.
- **Accessibility.** Keyboard paths, focus states, labels, error messages, and
  contrast are part of the editor and the public site, not a later audit.

### 4.5 Media

- Validate extension, declared MIME, and actual file signature; refuse SVG as a
  source unless a deliberate sanitizer exists.
- Require alt text at upload; an image without alt text is incomplete, not
  "stored for later."
- Generate AVIF/WebP derivatives when the toolchain exists; otherwise record a
  derivative plan and do not claim conversion.
- Store originals and derivatives with checksums; serve private media through
  authorization, not a public directory listing.
- Enforce a size cap and a storage quota; clean up orphaned derivatives.

### 4.6 SEO

- Title, description, canonical, robots, Open Graph, and structured data are
  fields with measured limits, not guesses.
- Sitemap and robots are generated from published content only.
- Redirects are first-class records with loop detection.
- SEO checks run against **built or served output**, not the CMS database.
- A green SEO light is a measured condition, not a ranking guarantee.

### 4.7 Security and permissions

- Authenticate admin users; hash passwords with a modern KDF; support session
  expiry and revocation.
- RBAC checks every mutating action on the server. Hiding a button is not a
  permission check.
- Encode at the output sink exactly once; validate plain text at entry.
- CSRF protection on state-changing requests; rate-limit login, forms, and
  uploads.
- Uploads are untrusted; scan names and paths; never execute uploaded files.
- Audit log is append-only and exportable.
- Secrets stay in environment/secret storage; never in content, logs, or the
  repository.

### 4.8 Internationalization

- Locale is part of the content identity, not a string prefix bolted on later.
- Missing translations fall back explicitly; no silent mixed-language page.
- RTL affects layout tokens and editor direction, not just text.
- Machine translation requires an approved provider/key and human review before
  publish.

## 5. Build phases

Each phase ends with a demo and evidence, not a status paragraph.

### Phase 0 — Discovery and decision record

Deliver: content inventory, roles, deployment profile, data/media/auth
decisions, threat model, acceptance scenarios, stack decision record.

Exit: owner approves the scope and the decision record names every infrastructure
choice. No CMS code before this.

### Phase 1 — Content kernel

Deliver: content types, validation, repository, atomic writes, revisions,
audit, roles, publish state machine.

Exit: create/edit/draft/publish/archive/rollback work in tests and against a real
database. Permission denial is proven, not assumed.

### Phase 2 — Public renderer

Deliver: page/section rendering, published-only reads, metadata, sitemap,
robots, redirects, 404/500, accessibility baseline.

Exit: built output renders real content; a draft cannot appear publicly; a
broken link/redirect is detected.

### Phase 3 — Admin and editor

Deliver: login, dashboard, content list, editor, media picker, settings, role
management, audit view.

Exit: a non-technical editor can complete the round trip without a developer;
an unauthorized role is refused on the server.

### Phase 4 — Visual surface and blocks (if in scope)

Deliver: block registry, coverage report, inspector, preview, media focal point.

Exit: every visible editable string has a key; a click never navigates; a
disallowed style/block is rejected.

### Phase 5 — Media, settings, inquiries, i18n

Deliver: upload pipeline, derivatives, global settings, lead inbox with status
and CSV export, locale fields and fallback.

Exit: a real image is uploaded and rendered; an inquiry is stored and exported;
a missing translation falls back correctly.

### Phase 6 — Publish, backup, restore

Deliver: publish/unpublish, revision history, content rollback, whole-store
snapshot, restore preview, restore with safety snapshot, retention.

Exit: edit → publish → render → rollback → render the prior state; restore is
undoable; a corrupt snapshot is refused.

### Phase 7 — Deployment and operations

Deliver: environment template, build/deploy commands, TLS/reverse proxy or
platform config, database migrations, media storage, backup schedule, restore
drill, monitoring, log rotation, rollback of a bad deploy.

Exit: a clean machine or platform project can be provisioned from the runbook;
a backup restores into a scratch environment; the public site survives a failed
deploy.

### Phase 8 — Independent proof and handoff

Deliver: test evidence, accessibility and SEO reports against built output,
security review, owner walkthrough, setup/content/recovery handoff.

Exit: the auditor reruns the decisive checks; the owner can edit, publish, and
recover without the builder; the ask-to-result matrix is complete.

## 6. M3 exit proof

The first real project is complete only when all of these are demonstrated on
the approved target:

1. The site builds and serves.
2. A real editor changes content and it persists.
3. The changed content renders on the public page.
4. A publish action makes it public; a draft stays private.
5. An unauthorized role is denied by the server.
6. A rollback restores the previous content.
7. Built output passes the agreed SEO and accessibility checks.
8. A backup restores into a scratch environment.
9. The handoff has setup, content, deployment, backup, and recovery steps.

Screenshots alone are not proof; commands and observed output are.

## 7. Decisions required before implementation

These are owner/product decisions, not framework preferences:

- Deployment profile: VPS, serverless, shared cPanel, static + API, or hybrid.
- Who operates it after handoff, and what uptime/backup obligations exist.
- Content inventory and which collections are required in the first slice.
- Roles and the publish approval rule.
- Languages and whether machine translation is allowed.
- Media storage and retention.
- Auth provider (local accounts vs an external identity provider).
- Lead capture destination and privacy/consent requirements.
- Budget for hosting, database, media, and any paid services.
- One target project and its non-negotiable content.

## 8. What is deliberately not decided here

- Astro vs Next.js vs Nuxt vs SvelteKit vs Laravel vs Django vs Go.
- Postgres vs MySQL vs SQLite vs D1/Turso.
- Local media vs S3/R2.
- VPS vs serverless vs cPanel.
- Whether the first project needs a CMS at all.

Those decisions belong in Phase 0, after the operating constraints are known.
