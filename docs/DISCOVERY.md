# Discovery and Evidence Intake

**Version:** 2 (facet-based)

**Status:** research and specification. The product still records only the free-text ask; this defines the next intake slice. Do not treat it as implemented.

**Research date:** 2026-10-26

**Design rule:** there is no fixed list of project types. A project is a **profile of independent facets**, and the question set is assembled from those facets. A project can be a redesign + SEO + CMS + migration + accessibility at the same time.

## 1. Why the first version was too narrow

A list such as “new site, redesign, migration, repair, audit, SEO” is easy to explain but wrong at the edges:

- a redesign can also be a CMS migration;
- an SEO project can include a replatform;
- a repair can require an accessibility remediation;
- a “new site” can include an API, a booking engine, and a payment flow;
- a CLI, a data pipeline, an AI assistant, or an internal tool is not a website;
- the owner may not know which label fits.

The intake must not force a label before it understands the work. Facets can be added, combined, or marked unknown without changing the gate logic.

## 2. Design principles

1. **One question at a time.** Never send the owner a 60-field form.
2. **Inspect before asking.** If a repository or URL exists, read it first. Ask only for intent, constraints, access, decisions, and owner-only facts.
3. **Record the owner’s words and the normalized fact separately.**
4. **Every fact has a source and an evidence level.** An owner estimate is not a measurement.
5. **Unknown is a valid state.** It becomes a risk with an owner and a follow-up, not an invented answer.
6. **Contradictions are shown, not averaged.**
7. **No secrets in chat.** Ask which access exists and who can authorize it; never ask for a password, key, card number, or recovery code.
8. **Depth follows risk and combination, not a fixed scenario.**
9. **Stop when the plan is safe.** Do not ask every possible question.
10. **No LLM judge decides completeness.** The gate is explicit fields, evidence levels, and owner decisions.

## 3. The facet profile

A profile is a small JSON object. Facet values are examples, not a closed enum; add a new value when the work needs it.

```json
{
  "id": "profile-example",
  "labels": ["redesign", "seo", "cms-migration"],
  "facets": {
    "change": ["redesign", "migrate"],
    "surface": ["website", "cms"],
    "lifecycle": ["active", "legacy"],
    "content": ["cms", "localized"],
    "users": ["public"],
    "data": ["personal"],
    "commerce": ["none"],
    "discovery": ["seo"],
    "quality": ["accessibility", "performance", "privacy"],
    "delivery": ["hosted", "ci-cd", "handoff"],
    "integration": ["analytics", "crm"],
    "ai": ["none"],
    "locale": ["multi"],
    "risk": ["medium"],
    "stage": ["discovery"],
    "team": ["client"],
    "budget": ["range"],
    "timeline": ["fixed"]
  },
  "notes": "Example only; not a project type."
}
```

### 3.1 Facet catalog

| Facet | Example values | What it changes |
|---|---|---|
| `change` | new, extend, redesign, repair, audit, migrate, optimize, replace, decommission, research, operate | Which evidence and rollback rules apply |
| `surface` | website, web-app, api, cli, library, desktop, mobile, game, data-pipeline, automation, ai-feature, docs, email, integration, marketplace, cms, commerce, dashboard, internal-tool, firmware | Which delivery and test modules load |
| `lifecycle` | idea, greenfield, active, legacy, maintenance, sunset | How much current-state inspection is needed |
| `content` | none, static, cms, ugc, media, localized, regulated | Content, editorial, rights, and workflow questions |
| `users` | public, authenticated, roles, b2b, internal, multi-tenant, children, vulnerable | Auth, permissions, consent, and usability |
| `data` | none, content, personal, financial, health, children, regulated, large, realtime | Privacy, security, retention, backup, and scale |
| `commerce` | none, catalog, payments, subscription, booking, donation, marketplace | Checkout, tax, shipping, inventory, refunds |
| `discovery` | private, seo, paid, app-store, marketplace, internal-search | SEO, ASO, analytics, and measurement |
| `quality` | accessibility, performance, security, reliability, compliance, ai-safety | Targets, tests, and acceptance |
| `delivery` | hosted, self-hosted, ci-cd, multiple-envs, support, handoff, decommission | Deployment, operations, and ownership |
| `ai` | none, assistant, generation, classification, rag, agent, fine-tune | Model, data, evaluation, and human review |
| `locale` | single, multi, rtl, cjk | Translation, layout, and content workflow |
| `integration` | crm, email, payments, booking, erp, webhooks, analytics | Contracts, auth, failures, and monitoring |
| `risk` | low, medium, high, critical | Depth, evidence, and approval level |
| `stage` | discovery, build, launch, operate, maintain | What the current gate is for |
| `team` | solo, team, client, regulated | Stakeholders, approvals, and handoff |
| `budget` | fixed, range, unknown, ongoing | Scope and vendor decisions |
| `timeline` | fixed, flexible, unknown | Sequencing and risk |

A facet can also be `unknown`. Unknown is not “none”; it loads a clarification module and creates a risk.

### 3.2 Adding a new facet or module

To support a new kind of work, add a facet value and a module with:

- a trigger expression (for example `surface=game` or `ai=agent`);
- required fields;
- evidence hints;
- acceptance checks;
- the gate condition.

No central “project type” switch needs to change.

## 4. The eighteen domains and 138 base fields

The reference model has **18 domains** and **138 base fields**, plus conditional fields added by modules. A field is a question with a stable ID, not a paragraph.

| # | Domain | Base fields |
|---|---|---|
| 1 | Intent, outcome, value | problem, trigger, desired outcome, business value, priority, success statement, non-goals |
| 2 | Stakeholders and governance | owner, sponsor, approver, decision rights, conflicts, communication, escalation |
| 3 | Users, roles, jobs | primary user, secondary users, jobs, current workaround, barriers, frequency, accessibility needs |
| 4 | Current state and assets | existing URL/repo, stack, hosting, domain, accounts, known failures, baseline evidence |
| 5 | Scope and priorities | must, should, could, won’t, first-release boundary, dependencies, change control |
| 6 | Content and information architecture | pages/screens, content inventory, owner, source, tone, media rights, localization |
| 7 | Brand and experience | references, anti-references, visual direction, tone, responsive behavior, motion, design owner |
| 8 | Functional behavior | user flows, states, validation, errors, empty states, admin actions, notifications |
| 9 | Data and domain model | entities, relationships, ownership, lifecycle, retention, export, deletion, quality |
| 10 | Integrations and APIs | systems, contracts, auth, rate limits, retries, failure states, monitoring |
| 11 | CMS and editorial | editors, roles, content types, workflow, preview, scheduling, publishing, rollback |
| 12 | Commerce and payments | catalog, checkout, payments, tax, shipping, inventory, refunds, fraud, PCI scope |
| 13 | SEO and discoverability | goals, queries, competitors, baseline, URL inventory, redirects, metadata, schema, internal links, measurement |
| 14 | Analytics and experimentation | events, conversions, dashboards, consent, attribution, reporting owner, experiment rules |
| 15 | Accessibility, inclusion, localization | target standard, keyboard, screen reader, contrast, captions, languages, RTL, content readability |
| 16 | Performance, reliability, scale | Core Web Vitals, budgets, traffic, peak load, uptime, recovery, degradation, monitoring |
| 17 | Security, privacy, legal, AI risk | data classes, auth, authorization, retention, consent, compliance, threats, model risks, human review |
| 18 | Delivery, operations, support, handoff | environments, CI/CD, deployment, backups, support, documentation, training, decommission |

The SEO row carries more than seven practical fields. It is shown as one domain because the **module** expands it; the base table is a map, not a cap.

## 5. The interview

### 5.1 Universal first turn

Ask these **one at a time**, in plain language. Reflect each answer back before the next.

1. When this is finished, what should be different, and why does it matter now?
2. What exists today: a URL, a folder, a repository, screenshots, a document, or nothing?
3. Which of these apply? It can be more than one: new build, change, redesign, repair, audit, migration, SEO/growth, performance, accessibility, other.
4. Who is the primary person this is for, and what one action must they be able to take?
5. What are the three must-haves for the first release, and what is explicitly not included?
6. How will you know it worked?
7. What is fixed: deadline, budget, brand, technology, hosting, legal or privacy rules, languages, or accessibility target?
8. Who owns the domain, hosting, repository, content, analytics, and final approval? What access exists, without sharing any secret value?
9. What evidence can you show: analytics or Search Console export, brand assets, examples, screenshots, logs, or a current process document?
10. What should the project be called?

Do not ask all ten in one message. A good first turn is question 1 plus a one-sentence reason.

### 5.2 Selecting the next question

After the first answers, create the facet profile and load the core pack plus every triggered module.

For each unanswered required field, compute:

```text
risk = impact (1..5) × uncertainty (1..5) × dependency (1..5)
```

Ask the highest-risk field whose prerequisites are answered. If two fields are equally risky, prefer the one that can unlock the most other fields. Do not follow a fixed script.

Stop asking when:

- every blocking field is answered, evidenced, or explicitly unknown with an owner and risk;
- every must-have has an acceptance check and evidence source;
- every non-goal and fixed constraint is recorded;
- the gate expression for the loaded modules is satisfied.

### 5.3 Follow-up techniques

Use these only when the first answer is vague:

| Technique | Question | What it exposes |
|---|---|---|
| Critical incident | “Tell me about the last time this happened. What did you do, and what was the result?” | Real behavior, not a hypothetical |
| Laddering | “Why does that matter?” then “What happens today instead?” | Underlying outcome and workaround |
| Observation | “Can you show me the current screen, file, or process?” | Evidence and hidden steps |
| Five whys | “Why does that happen?” repeated until a cause or a boundary appears | Root cause, not symptom |
| Pre-mortem | “It is six months later and this failed. What went wrong?” | Risks and missing owners |
| Rejection test | “What would make you reject the result?” | Quality bar and non-goals |
| Handoff test | “If you disappeared for a month, who would run this and what would they need?” | Operations, documentation, ownership |
| Evidence challenge | “How do you know that number?” | Distinguishes estimate from measurement |

Avoid “Would you like…?” and “Do you want it modern?” Ask what happened, what exists, what was measured, and what was rejected.

### 5.4 Owner-only versus discoverable

| Owner-only | Agent can inspect |
|---|---|
| business goal, audience intent, budget, deadline, approvals, brand preference, legal constraints, risk tolerance, content ownership | repository structure, stack, tests, routes, metadata, links, page speed, console errors, accessibility tree, analytics if access is granted, public pages, sitemaps, robots, redirects |

If a fact can be inspected, do not make the owner retype it. Record the inspection command or URL and ask the owner only to confirm the interpretation.

### 5.5 Presentation format and the research fallback

A blank question puts the work on the owner. Present each answerable question as a short numbered menu:

```text
Which outcome matters most? Choose one or more:

1. More customers, leads, or sales
2. Save time or reduce manual work
3. Fix a problem or reduce errors
4. Launch a new product or service
5. Improve search visibility
6. Improve speed, accessibility, or usability
7. Reduce risk, compliance, or cost
8. Not sure — research and recommend
9. Other — type it
```

Rules:

- number every option;
- allow multiple selections when appropriate;
- always include **not sure — research and recommend** and **other**;
- keep the menu short; put examples in one sentence, not a paragraph;
- reflect the choice back before moving to the next question.

If the owner chooses “not sure”:

1. Inspect whatever exists read-only.
2. Research two or three credible options, references, or competitors.
3. Compare them on outcome fit, cost, time, risk, maintenance, and evidence.
4. Recommend one, in plain language, with the assumptions and what would change the recommendation.
5. Ask the owner to accept, change, or defer it.
6. Record the decision, alternatives, and evidence.

Example:

```text
I do not know which platform to use.

Agent: I checked the empty folder and your goal: publish a small portfolio
without a developer. I compared three options:

A. Static site, no CMS — fastest and cheapest, but every text change needs
   a developer.
B. Static site plus a small CMS — slightly more setup, but you can edit.
C. Full web application — unnecessary for this scope and costs more.

Recommendation: B. It meets the editing requirement without the cost of C.
Assumption: you want to edit text yourself. If you will never edit it, choose A.
```

The agent must not silently choose, and must not recommend a paid product or service without asking first. “Best” means best against the owner’s stated outcome and constraints, not the agent’s favorite stack.

## 6. Modules that expand the base fields

A module is a conditional question pack. These are examples; the trigger can be combined.

| Module | Trigger examples | Adds | Gate examples |
|---|---|---|---|
| Current-state audit | change in extend/repair/redesign/migrate/audit | repository, tests, routes, logs, baseline, preserved behavior | current state inspected; tests or explicit gap |
| Scope and change control | always | must/should/could/won’t, waiver owner, change path | non-goals recorded; approver named |
| Content inventory | content != none | pages, source, owner, freshness, rights, metadata | content source and owner exist |
| Design system | surface includes website/web-app/mobile | brand, references, tokens, components, responsive, motion | references and design owner confirmed |
| Frontend quality | surface includes website/web-app | routes, forms, states, responsive, browser/device, analytics | primary journeys and breakpoints tested |
| Application core | surface includes web-app/internal-tool | roles, auth, permissions, workflows, errors, audit log | roles and one end-to-end flow proven |
| API and integrations | surface includes api or integration != none | contract, auth, limits, retries, webhooks, monitoring | contract and failure behavior recorded |
| CMS | content includes cms or surface includes cms | editors, roles, content types, workflow, preview, publish, rollback | edit → preview → publish → rollback |
| Commerce | commerce != none | catalog, cart, checkout, tax, shipping, inventory, refunds, fraud, PCI | payment path and responsibility confirmed |
| Booking | commerce includes booking | availability, calendar, deposit, reminders, cancellation | booking and cancellation flow proven |
| SEO | discovery includes seo | queries, competitors, baseline, URLs, redirects, metadata, schema, internal links, content gaps, measurement | baseline and URL map captured |
| Analytics | measurement is required or discovery != private | events, conversions, dashboards, consent, owner | event plan and access confirmed |
| Migration | change includes migrate or replace | URL map, data map, DNS, redirects, freeze, rollback | URL/data map and rollback proven |
| Accessibility | quality includes accessibility or users include vulnerable | target, keyboard, screen reader, contrast, captions, forms | target level and pages defined; tests run |
| Performance | quality includes performance | baseline, budgets, pages, devices, third parties | baseline and target pages recorded |
| Reliability | quality includes reliability or data is large/realtime | traffic, uptime, peak, recovery, degradation, monitoring | failure and recovery behavior defined |
| Security | quality includes security or data != none | data classes, auth, authorization, threats, secrets, logging | threat model and access boundaries |
| Privacy and legal | data includes personal/regulated or locale multi | lawful basis, consent, retention, export, deletion, DPA, cookies | data map and retention owner |
| AI feature | ai != none | model, provider, data, prompts, evaluation, human review, cost, latency, fallback | eval set and human review path |
| Localization | locale != single | languages, RTL, translation owner, workflow, fallback | language list and owner |
| Operations | delivery includes hosted/support/handoff | environments, CI/CD, backup, monitoring, incident, support, training | deploy and rollback path |
| Documentation and handoff | always at launch | audience, runbook, setup, known limits, ownership | fresh-reader test |

A project can trigger many modules. A design cannot be “locked” to one row.

## 7. Evidence model

### 7.1 Fields

| Field | Meaning |
|---|---|
| `fact_id` | Stable ID, for example `seo.url_inventory`. |
| `domain` | One of the eighteen domains. |
| `statement` | Normalized one-sentence fact. |
| `owner_words` | The owner’s exact wording. |
| `kind` | fact, assumption, decision, constraint, preference, or acceptance. |
| `source` | owner, document, repository, URL, command, analytics, observation, or review. |
| `evidence_ref` | Path, URL, export, screenshot, command output, or review record. |
| `evidence_level` | E0–E4. |
| `confidence` | confirmed, likely, unknown, contradicted. |
| `freshness` | captured date and expected review date. |
| `sensitivity` | public, internal, personal, secret-adjacent. |
| `owner` | Who can confirm or change it. |
| `dependency` | Other facts that must be true first. |
| `follow_up` | What remains to inspect or ask. |

### 7.2 Evidence levels

| Level | Meaning | Permitted use |
|---|---|---|
| E0 | Missing | Cannot support a requirement. |
| E1 | Owner statement or estimate | Intent and hypotheses; not a measured baseline. |
| E2 | Owner-provided artifact | Minimum for a current-state factual claim. |
| E3 | Agent inspected or reproduced read-only | Stronger; include command, URL, and timestamp. |
| E4 | Independent reviewer or measurement confirmed | Required for a verified claim where review is in scope. |

### 7.3 Evidence quality checks

- **Freshness:** analytics, rankings, dependency versions, and security claims expire.
- **Completeness:** a screenshot of one page does not prove a site.
- **Independence:** the builder’s assertion is not an independent review.
- **Reproducibility:** a command with no output is not evidence.
- **Sensitivity:** redact personal data; record only credential names.
- **Contradiction:** keep both values and ask the owner to resolve them.

### 7.4 Assumption and unknown registers

Every unresolved item gets:

- an owner;
- a risk if wrong;
- a way to resolve it;
- a due date or a decision point;
- the gate it blocks.

A plan may proceed with an unknown only when the owner explicitly accepts the risk. “Assumed” without an owner is a placeholder and must fail the gate.

## 8. Coverage and gates

A field is `missing`, `claimed` (E1), `evidenced` (E2/E3), or `verified` (E4). A module gate is a boolean expression over its required fields, for example:

```text
core.outcome and core.scope and core.success
and (current_state.inspected or current_state.owner_accepts_unknown)
and seo.baseline and seo.url_inventory
and migration.url_map and migration.rollback
```

The plan gate refuses when a blocking field is missing. The owner can waive a field only by recording:

- the field ID;
- the reason;
- the risk;
- the person accepting it;
- the expiry or review point.

No waiver is implied by silence.

## 9. Simulation: composite profiles

These are **test profiles**, not a closed taxonomy. Each combines facets and loads different modules; the point is that no two need a special project-type switch.

| Profile | Facets | Modules that load | Expected gate |
|---|---|---|---|
| Portfolio site | website, new, static, public, seo | core, content, design, frontend, seo, analytics, ops | ready after content/hosting/SEO decisions |
| Marketing site + blog + CMS | website, new, cms, localized, seo | core, content, cms, design, frontend, seo, analytics, localization, ops | blocked until editors, languages, URL plan |
| SaaS dashboard | web-app, new, auth, roles, personal, api | core, app, auth, data, api, design, frontend, security, privacy, ops | blocked until roles and data map |
| Public API | api, new, integration, docs | core, api, auth, data, docs, observability, ops | ready after contract and failure behavior |
| CLI tool | cli, new, none, docs | core, cli, docs, tests, release, ops | ready after install and rollback |
| Library | library, new, docs | core, api, docs, compatibility, release | ready after supported versions and tests |
| Mobile app | mobile, new, auth, personal, app-store | core, mobile, auth, data, design, privacy, release | blocked until store/privacy/device matrix |
| Desktop app | desktop, new, local-data | core, desktop, data, update, security, release | ready after update and backup path |
| AI assistant | ai-feature, new, rag, personal | core, ai, data, privacy, security, eval, human-review, ops | blocked until eval set and data policy |
| Data pipeline | data-pipeline, new, large, integration | core, data, integration, reliability, observability, security | ready after schema, failure, and retention |
| Internal tool | internal-tool, new, auth, roles, internal | core, app, auth, data, accessibility, ops | ready after roles and support owner |
| Existing feature | web-app, extend, active, auth | core, current-state, app, tests, rollback, ops | ready after reproduction and regression baseline |
| Redesign + CMS + SEO + migration | website, redesign, migrate, cms, seo, localized | core, current-state, content, cms, seo, migration, design, accessibility, analytics | blocked until URL/data map and redirect owner |
| Repair + accessibility | website, repair, active, accessibility | core, current-state, reproduction, accessibility, tests, rollback | ready after reproduction and target page list |
| Security audit | web-app, audit, personal, security | core, current-state, security, privacy, evidence, review | ready after scope and access; no code change |
| SEO-only | website, optimize, seo, active | core, current-state, seo, analytics, content, performance | blocked until baseline and target intent |
| Performance-only | website, optimize, performance, active | core, current-state, performance, analytics, frontend | ready after baseline and target pages |
| Accessibility remediation | website, repair, accessibility, active | core, current-state, accessibility, frontend, tests | ready after target level and page scope |
| CMS migration | cms, migrate, content, active | core, current-state, content, cms, migration, redirects, ops | blocked until content model and rollback |
| Ecommerce launch | commerce, new, payments, personal, seo | core, commerce, payments, tax, shipping, security, privacy, seo, ops | blocked until payment/tax/returns ownership |
| Subscription membership | commerce, new, subscription, auth, personal | core, commerce, payments, auth, data, privacy, email, ops | blocked until billing and cancellation flow |
| Booking site | commerce, booking, calendar, payments | core, booking, payments, email, privacy, ops | ready after availability/cancellation policy |
| Marketplace | marketplace, multi-tenant, payments, content, seo | core, marketplace, auth, data, commerce, trust, moderation, seo, ops | blocked until trust and payout model |
| Documentation/handoff | docs, existing, handoff | core, current-state, docs, runbook, training, verification | ready after fresh-reader test |
| Decommission/replacement | replace, decommission, active | core, current-state, data, migration, redirects, rollback, support | blocked until data export and rollback |

A new surface can be added without editing the profile list: add a facet value, a module, and a test profile.

## 10. Anti-patterns

- A fixed “project type” list that cannot express combinations.
- A 60-question form sent before any inspection.
- Asking a non-technical owner to choose a framework or database without trade-offs.
- “Do you want it modern?” instead of asking what is wrong today.
- Treating a preference as a requirement or an estimate as a measurement.
- Accepting “make it fast”, “make it SEO-friendly”, or “make it accessible” without a target and a test.
- Asking for passwords, keys, card numbers, or recovery codes.
- Recording only the normalized answer and losing the owner’s words.
- Letting the agent answer its own question.
- Planning before current state is inspected.
- Treating a host binary as proof of a reviewer.
- Claiming “all scenarios covered” from a handful of demos.

## 11. Agent behavior contract

1. Start with the outcome, not a project-type label.
2. Reflect each answer back in plain language.
3. Build the facet profile; show it when asked.
4. Inspect existing URLs/repositories read-only before asking what they can prove.
5. Ask the highest-risk missing field next; explain why in one sentence.
6. Offer “I do not know”, “you decide”, and “later” as valid choices.
7. Record raw words, normalized fact, source, evidence level, confidence, owner, and follow-up.
8. At the end of each domain, show a short summary and unresolved items.
9. Stop and ask the owner to resolve contradictions.
10. Do not plan until the gate is met or a named risk is accepted.
11. Never claim verification from documentation alone.

## 12. Implementation order

1. **Discovery record:** stable field IDs, raw words, sources, evidence levels, confidence, sensitivity, owner, and follow-up.
2. **Facet profile:** validated facet values, extensible custom values, and module selection.
3. **Question engine:** deterministic next-question ordering, prerequisites, and “unknown” handling.
4. **Coverage report:** missing, claimed, evidenced, verified; per domain and per module.
5. **Plan gate:** block or waive with a recorded owner decision.
6. **Scenario fixtures:** composite profiles above, run against the real gate.
7. **Read-only inspectors:** repository, URL, analytics, Search Console, sitemap, redirects, accessibility, performance.
8. **Evidence attachments:** hashes, redaction, expiry, and a manifest.

Do not add an LLM judge to decide whether discovery is complete. The agent conducts the interview; the gate is deterministic.

## 13. Sources

- GOV.UK Service Manual, “How the discovery phase works”: https://www.gov.uk/service-manual/agile-delivery/how-the-discovery-phase-works
- Nielsen Norman Group, “Discovery: Definition”: https://www.nngroup.com/articles/discovery-phase/
- Zowghi and Coulin, “Requirements Elicitation: A Survey of Techniques, Approaches, and Tools”: https://web.eecs.umich.edu/~weimerw/2022-481W/readings/requirements.pdf
- U.S. OPM, structured interviews and critical-incident method: https://www.opm.gov/policy-data-oversight/assessment-and-selection/structured-interviews/guide/
- Google Search Central, “Search Essentials”: https://developers.google.com/search/docs/essentials
- Google Search Central, “SEO Starter Guide”: https://developers.google.com/search/docs/fundamentals/seo-starter-guide
- Google Search Central, “Redirects and Google Search”: https://developers.google.com/search/docs/crawling-indexing/301-redirects
- web.dev, “Web Vitals”: https://web.dev/articles/vitals
- W3C WAI, “How to Meet WCAG 2.2”: https://www.w3.org/WAI/WCAG22/quickref/
- Schema.org vocabulary: https://schema.org/
- OWASP Application Security Verification Standard: https://owasp.org/www-project-application-security-verification-standard/
- NIST AI Risk Management Framework: https://www.nist.gov/itl/ai-risk-management-framework
- NIST Generative AI Profile: https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf
- European Commission, GDPR principles: https://commission.europa.eu/law/law-topic/data-protection/information-business-and-organisations/principles-gdpr_en
- European Data Protection Board, data protection by design and by default: https://www.edpb.europa.eu/system/files/documents/2026-02/edpb-summary-gdpr-data-protection-design-default_en.pdf
