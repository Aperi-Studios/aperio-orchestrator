# Discovery and Evidence Intake

**Status:** research and specification. The questionnaire model below is not yet a CLI command; the current product records only the free-text ask. This document defines what the next intake slice must implement.

**Research date:** 2026-10-26

**Purpose:** collect enough truthful evidence from a non-technical owner to write a bounded, testable plan without inventing requirements.

## 1. What discovery must produce

Discovery is not a form and it is not planning. It ends when Aperio can answer, with evidence:

1. What outcome the owner wants, and why now.
2. Who the user is and what that user must be able to do.
3. What exists today: nothing, a repository, a live site, a partial build, or a broken system.
4. What is in the first release, what is explicitly out, and what can wait.
5. How success will be measured.
6. What constraints are fixed: time, money, brand, technology, hosting, law, privacy, language, accessibility.
7. Who owns the content, accounts, approvals, and launch.
8. What evidence the owner can provide, and what the agent can inspect directly.

The output is a **discovery record**, not a conversation transcript. The record separates facts, assumptions, decisions, constraints, and acceptance criteria. Planning begins only when the critical fields are covered or explicitly marked unknown with an owner and a risk.

Research basis: GOV.UK says discovery must understand users, constraints, the policy or business intent, and opportunities, and should not start building; NN/g defines discovery as reaching consensus on the problem and desired outcomes when unknowns block progress; requirements-elicitation research treats questionnaires as early, focused aids that must be combined with interviews and document study, not as a substitute for them.

## 2. Operating principles

1. **Ask one question at a time.** A non-technical owner should never receive a 60-question form.
2. **Inspect before asking.** If the owner gives a repository or URL, read it first. Ask the owner only for intent, constraints, access, and decisions that cannot be discovered.
3. **Capture the owner's words.** Store the raw answer and a normalized fact separately. Do not silently turn "make it modern" into a design requirement.
4. **Record the source.** Every fact names whether it came from the owner, a document, a URL, a repository, a command, or an independent review.
5. **Separate fact from assumption.** "The site gets 40 leads a month" is a fact only with an export or dashboard. Otherwise it is an owner estimate.
6. **Allow "I do not know."** An explicit unknown is safer than an invented answer. It becomes a risk or a research task.
7. **Do not ask for secrets.** Ask which accounts exist and who can authorize access. Never ask the owner to paste passwords, API keys, card data, or recovery codes into chat.
8. **Contradictions are recorded, not averaged.** If two answers conflict, show both and ask the owner to resolve them.
9. **Stop when the plan is safe, not when every field is full.** Depth is driven by risk and scenario, not by a fixed question count.
10. **Do not use discovery to sell a solution.** Start with the problem and the outcome; propose a stack or design only after the constraints are known.

## 3. The first questionnaire

These eight questions are universal. Ask them in order, one per message. Reflect each answer back in one sentence before moving on.

| # | Question | Why it matters | Evidence to request |
|---|---|---|---|
| 1 | Is this a new build, a change or redesign of something existing, a repair, an audit, a migration, or SEO/growth work? | Selects the branch and the required depth. | A short choice; no artifact needed. |
| 2 | When this is finished, what should be different, and why does it matter now? | Defines the outcome, not the requested feature. | The owner's own words; examples of the current problem. |
| 3 | What exists today: a URL, a folder, a repository, screenshots, a document, or nothing? | Prevents planning in a vacuum and tells the agent what to inspect. | URL, path, repository link, screenshots, or "nothing yet". |
| 4 | Who is the primary person this is for, and what is the one action they must be able to take? | Separates the audience from the owner's preferences. | A named user group and one primary action; current journey if available. |
| 5 | What are the three must-haves for the first release, and what is explicitly not included? | Creates scope and non-goals before design or code. | Owner list; existing pages or features that must be preserved. |
| 6 | How will you know it worked? | Produces measurable acceptance criteria instead of "looks good". | A number, a user action, a conversion, a search/metrics export, or a concrete check. |
| 7 | What is fixed: deadline, budget, brand, technology, hosting, legal or privacy rules, languages, or accessibility target? | Separates real constraints from preferences. | Contracts, brand guide, policy, existing stack, target standard. |
| 8 | Who owns the domain, hosting, repository, content, analytics, and final approval? What access exists? | Establishes authority and avoids blocked work later. | Role names and access confirmation only; never secret values. |

After question 8, ask one evidence question:

> What can you show me that would let us verify this: an existing URL, analytics or Search Console export, brand assets, examples you like, a screenshot, an error message, or a current process document?

Do not ask all nine at once. A good first turn is question 1 plus a plain-language explanation of why it is being asked.

## 4. The twelve domains and 68 evidence fields

The working model has **12 domains** and **68 fields**. Not every field applies to every project. The scenario branch decides which fields are required.

| # | Domain | Core fields | Usually owner-only? |
|---|---|---|---|
| 1 | Outcome and value | problem, trigger, desired outcome, business value, priority, non-goals | Yes |
| 2 | Users and jobs | primary user, secondary users, jobs to be done, current workaround, barriers | Mostly yes |
| 3 | Current state and access | scenario, existing URL/repo, stack, hosting, domain, accounts, known failures | Mixed; inspect first |
| 4 | Scope and priorities | must/should/could/won't, first-release boundary, preserved behavior, dependencies | Yes |
| 5 | Content and information architecture | pages, content inventory, owner, source, tone, media, localization, migration | Mixed |
| 6 | Brand and experience | references, anti-references, visual direction, tone, responsive expectations, design owner | Yes |
| 7 | Functional and data | user flows, roles, forms, data model, validation, error states, admin actions | Mixed |
| 8 | Integrations and CMS | CMS, editors, publishing, CRM, email, payments, booking, APIs, webhooks | Mixed |
| 9 | SEO and discoverability | goals, queries, locations, competitors, baseline, URL map, redirects, metadata, schema, internal links, measurement | Mixed |
| 10 | Quality attributes | accessibility target, performance budget, browsers/devices, content freshness, analytics | Mixed |
| 11 | Security, privacy, legal | personal data, authentication, authorization, retention, consent, compliance, threat model | Yes, with inspection |
| 12 | Delivery and handoff | deadline, budget, approvers, launch owner, deployment, backup/rollback, maintenance, training | Yes |

The 68 fields are a checklist, not a script. For a simple new brochure site, about 14 to 18 fields are enough. A redesign or SEO project usually needs 25 to 35. A web application, CMS migration, or ecommerce project usually needs 45 to 60. The aim is coverage of risk, not a perfect score.

## 5. Evidence model

Every recorded answer should carry these fields:

| Field | Meaning |
|---|---|
| `fact_id` | Stable ID, for example `outcome.primary`. |
| `domain` | One of the twelve domains. |
| `statement` | Normalized one-sentence fact. |
| `owner_words` | The owner's original wording, kept separately. |
| `kind` | `fact`, `assumption`, `decision`, `constraint`, `preference`, or `acceptance`. |
| `source` | `owner`, `document`, `repository`, `url`, `command`, `analytics`, or `review`. |
| `evidence_ref` | Path, URL, export, screenshot, command output, or review record. |
| `evidence_level` | E0 to E4, defined below. |
| `confidence` | `confirmed`, `likely`, `unknown`, or `contradicted`. |
| `sensitivity` | `public`, `internal`, `personal`, or `secret-adjacent`. |
| `owner` | Who can confirm or change it. |
| `captured_at` | Timestamp. |
| `follow_up` | What remains to inspect or ask. |

### Evidence levels

| Level | Meaning | Use |
|---|---|---|
| E0 | No evidence; not recorded. | Cannot support a requirement. |
| E1 | Owner statement or estimate. | Useful for intent, not proof of current behavior. |
| E2 | Owner-provided artifact: URL, file, screenshot, export, document. | Minimum for a factual current-state claim. |
| E3 | Agent inspected or reproduced it read-only. | Stronger; records command or URL and timestamp. |
| E4 | Independent reviewer or measurement confirmed it. | Required for a "verified" claim where review is in scope. |

A plan must not turn E1 into E2 in its own wording. "The owner believes traffic is 10k/month" remains an owner estimate until an analytics export or dashboard is recorded.

### Secrets rule

Ask **which access exists and who can authorize it**, not for the secret itself. Never accept a password, API key, card number, recovery code, or private token in chat. Use the owner's existing vault or environment injection, and record only the credential **name** and the fact that access was confirmed.

## 6. Scenario branches

The first answer selects the branch. Each branch adds required fields and changes the acceptance evidence.

| Scenario | First branch question | Required extras | Gate before planning |
|---|---|---|---|
| New static site | New build with no existing code | audience, pages, content owner, domain/hosting, SEO basics, analytics, launch owner | Outcome, pages, content source, primary action, SEO/analytics decision, owner |
| New web application | New build with users and data | roles, workflows, data model, auth, integrations, error states, deployment | Users/roles, must-have flows, data sensitivity, auth, hosting, acceptance |
| Existing feature | Change an existing repository | current behavior, tests, affected paths, regression risk, deployment | Repo inspected, current tests, preserved behavior, rollback |
| Redesign | Change an existing site or app's experience | current URL, analytics/GSC baseline, content inventory, brand, redirects, accessibility | Baseline, URL inventory, preserve/retire decisions, redirect owner |
| Repair | Fix a defect | reproduction, environment, logs, recent changes, severity, expected behavior | Reproduction, impact, acceptance check, rollback |
| Audit | Review without changing yet | scope, standards, access, evidence format, reviewer independence | Scope, standards, access, report format |
| Migration | Move platform, domain, CMS, or data | source/target, URL map, data map, DNS, redirects, rollback, SEO baseline | URL/data map, redirect plan, rollback, owner |
| SEO/growth | Improve discoverability | goals, queries, locations, competitors, GSC/analytics, URL inventory, content gaps, measurement | Baseline, target intent, URL/metadata plan, measurement |
| Performance | Improve speed | baseline Core Web Vitals, pages, devices, third parties, budget | Baseline, target pages, budget, measurement method |
| Accessibility | Meet an accessibility standard | target level, pages, assistive technologies, current audit, remediation owner | Target (for example WCAG 2.2 AA), scope, test method |
| CMS | Add or change content management | editors, roles, content types, workflow, preview, media, publishing, backup | Roles, content model, workflow, publish/rollback |
| Ecommerce | Sell products or services | catalog, payments, tax, shipping, inventory, email, fraud, PCI scope | Catalog, payment path, tax/shipping, security, returns |
| API/integration | Connect systems | endpoints, auth, contracts, rate limits, errors, retries, observability | Contract, auth, failure behavior, owner |
| Documentation/handoff | Explain or transfer a system | audience, runbooks, setup, deployment, known limits | Audience, source of truth, verification |

## 7. Branch question bank

### 7.1 Existing site or repository

1. What is the URL or repository path, and may I inspect it read-only?
2. What works today that must not break?
3. What is the current stack, build command, and deploy path?
4. Which tests exist, and what do they actually cover?
5. What are the top three user journeys or pages by importance?
6. What are the top three by traffic, conversion, or revenue, if known?
7. What changed recently that might explain the problem?
8. Who can approve a change, and who can deploy it?
9. What is the rollback path?
10. What evidence can you provide: analytics, Search Console, error logs, screenshots, support messages?

### 7.2 New project

1. What is the one job the first release must do?
2. Who is the primary user, and what do they do before and after?
3. What are the pages or screens in the first release?
4. What content exists, and who writes the missing content?
5. What brand assets and examples exist?
6. What domain, hosting, and analytics accounts exist?
7. Does it need a CMS, forms, payments, accounts, or integrations?
8. What is explicitly out of scope?
9. What is the launch date and the approval path?
10. What would make you say this was a waste of money?

### 7.3 Redesign or migration

1. Why redesign or migrate now?
2. What must be preserved: URLs, rankings, content, integrations, brand, data?
3. Do you have Search Console, analytics, and a full URL inventory?
4. Which pages bring traffic, leads, or revenue?
5. Which pages will be kept, merged, redirected, or retired?
6. Who owns the redirect map and who tests it?
7. What is the CMS and editorial workflow after launch?
8. What is the rollback plan if launch fails?
9. What accessibility and performance targets apply?
10. How will success be measured at 30, 60, and 90 days?

### 7.4 SEO/growth

1. What business outcome should search produce: leads, sales, bookings, calls, or something else?
2. Which services, products, locations, or questions should you be found for?
3. Who is the intended searcher, and what do they need to believe before acting?
4. Who are the three most relevant competitors, and why?
5. Do you have Search Console, analytics, and Bing Webmaster access?
6. What are the top pages by impressions, clicks, conversions, and revenue?
7. Which URLs, rankings, or backlinks would be costly to lose?
8. Will URLs change, and who owns the redirect map?
9. Which titles, descriptions, headings, internal links, and structured data need work?
10. How will results be measured, and over what period?

SEO acceptance must be based on a baseline and a measurement plan, not a promise of a ranking. Google explicitly says meeting its requirements does not guarantee crawling, indexing, or serving, and that changes can take weeks or months to show.

### 7.5 Repair or audit

1. What exactly happens, and what did you expect instead?
2. Can you reproduce it? On which device, browser, account, and environment?
3. When did it start, and what changed?
4. What is the impact: blocked work, lost data, lost revenue, security, or cosmetic?
5. What logs, screenshots, or error messages exist?
6. What is the smallest acceptable fix, and what must not change?
7. Who can approve an emergency change?
8. For an audit, which standard and which evidence format are required?

### 7.6 CMS, ecommerce, and web applications

Add these to the relevant branch:

- Roles and permissions: who can create, edit, approve, publish, delete, and roll back?
- Content model: types, fields, relationships, required metadata, media, localization.
- Workflow: draft, review, schedule, publish, unpublish, archive.
- Commerce: catalog, variants, prices, tax, shipping, inventory, refunds, fraud, PCI scope.
- Application: authentication, authorization, audit log, data retention, export, deletion.
- Integrations: owner, contract, auth method, rate limits, retry behavior, failure state, monitoring.

## 8. Coverage and stop rule

Use four levels per field: `missing`, `claimed` (E1), `evidenced` (E2/E3), and `verified` (E4). A simple first-release gate is:

- all universal fields answered or explicitly marked unknown;
- every must-have has an owner, an acceptance check, and at least E2 evidence for the current-state claim;
- every non-goal is recorded;
- every required account/access is confirmed by role, not by secret value;
- every critical unknown has an owner, a follow-up, and a risk;
- the scenario-specific gate is satisfied.

Do not require every field. Do not let an agent mark a field "answered" from its own inference. The owner confirms owner-only facts; the agent records inspected facts with a command or URL.

## 9. Simulated scenarios

These are design simulations, not live host runs. Each row shows the minimum path and the expected gate result.

| Scenario | Starting evidence | Simulated path | Depth | Gate result |
|---|---|---|---|---|
| New static site | Empty folder, owner wants a portfolio | 8 universal + pages, content, domain, analytics, SEO basics | 18 fields | Ready with assumptions for content and hosting |
| New web app | Idea only | 8 universal + roles, flows, data, auth, integrations, deployment | 42 fields | Blocked until roles and data sensitivity are known |
| Existing feature | Repository and issue link | Inspect tests and routes; ask preserved behavior, acceptance, rollback | 22 fields | Ready after reproduction and test baseline |
| Redesign | Live URL and GSC access | Baseline traffic, URL inventory, preserve/retire, design, redirects | 34 fields | Blocked until redirect owner and content inventory exist |
| Repair | Screenshot and error text | Reproduce, environment, recent change, impact, smallest fix | 12 fields | Ready after reproduction and rollback |
| Audit | Repository, standard, read-only access | Scope, standards, evidence format, reviewer | 20 fields | Ready; no code change |
| Migration | Old and new platforms | URL/data map, DNS, redirects, rollback, SEO baseline | 38 fields | Blocked until data and redirect maps exist |
| SEO/growth | Live site and GSC export | Queries, competitors, top pages, URL map, metadata, schema, measurement | 26 fields | Blocked until baseline and target intent are recorded |
| Performance | Live URL and page list | Core Web Vitals baseline, devices, third parties, budget | 17 fields | Ready after baseline and target pages |
| Accessibility | Live URL, target standard | WCAG target, pages, keyboard/screen-reader checks, remediation owner | 16 fields | Ready after target level and scope |
| CMS | Existing content and editors | Roles, content model, workflow, preview, publish, rollback | 24 fields | Blocked until roles and workflow are confirmed |
| Ecommerce | Product list and payment idea | Catalog, checkout, tax, shipping, inventory, security, returns | 40 fields | Blocked until payment and tax ownership are clear |
| API/integration | Endpoint docs or sample | Contract, auth, rate limits, errors, retries, monitoring | 20 fields | Ready after contract and failure behavior |
| Documentation | Existing repository | Audience, setup, deploy, known limits, verification | 12 fields | Ready after a fresh-reader test |

The numbers are planning estimates, not a quota. The important result is the **blocked** cases: a plan written without those facts would be guesswork.

## 10. Anti-patterns

- A single giant form sent before any inspection.
- Asking a non-technical owner to choose a framework, database, or hosting provider without explaining trade-offs.
- Asking "Do you want a modern design?" instead of asking what is wrong with the current one.
- Treating an owner's guess as a measured baseline.
- Accepting "make it fast", "make it SEO-friendly", or "make it accessible" as acceptance criteria without a target and a test.
- Asking for passwords or API keys in chat.
- Recording only the normalized answer and losing the owner's original words.
- Letting the agent answer its own question and calling it discovery.
- Planning before the current state is inspected.
- Treating a host binary's presence as proof that a reviewer is available or permitted.

## 11. Agent behavior contract

1. Open with the scenario question; do not dump a questionnaire.
2. Explain why the current question matters in one sentence.
3. Offer examples and an explicit "I do not know" option.
4. After each answer, restate it and ask for correction.
5. Inspect a provided URL or repository read-only before asking questions it can answer.
6. Record raw answer, normalized fact, source, evidence level, and confidence.
7. At the end of each domain, show a short summary and the remaining unknowns.
8. Stop and ask the owner to resolve contradictions.
9. Do not write a plan until the gate is met or the owner explicitly accepts a named risk.
10. Never claim that a field is verified because a document says so; verify with a command, export, or independent review.

## 12. Next implementation slice

The product currently records a free-text ask only. The next slice should add, in order:

1. A discovery record with stable field IDs, raw owner words, normalized facts, source, evidence reference, level, and confidence.
2. A deterministic question bank for the twelve domains and the scenario branches.
3. A coverage report that prints missing, claimed, evidenced, and verified fields per domain.
4. A plan gate that refuses to plan when a required field is missing, unless the owner records an explicit waiver and risk.
5. Scenario fixtures that run the gate against all fourteen scenarios above.
6. A read-only inspection adapter that records repository, URL, and metrics evidence without asking the owner to retype it.

Do not add an LLM judge to decide whether discovery is complete. Use explicit fields, evidence levels, and owner decisions. The agent can conduct the interview; the gate must be deterministic.

## 13. Sources

- GOV.UK Service Manual, “How the discovery phase works”: https://www.gov.uk/service-manual/agile-delivery/how-the-discovery-phase-works
- Nielsen Norman Group, “Discovery: Definition”: https://www.nngroup.com/articles/discovery-phase/
- Zowghi and Coulin, “Requirements Elicitation: A Survey of Techniques, Approaches, and Tools”: https://web.eecs.umich.edu/~weimerw/2022-481W/readings/requirements.pdf
- Google Search Central, “Search Essentials”: https://developers.google.com/search/docs/essentials
- Google Search Central, “SEO Starter Guide”: https://developers.google.com/search/docs/fundamentals/seo-starter-guide
- Google Search Central, “Redirects and Google Search”: https://developers.google.com/search/docs/crawling-indexing/301-redirects
- web.dev, “Web Vitals” (LCP, INP, CLS thresholds): https://web.dev/articles/vitals
- W3C WAI, “How to Meet WCAG 2.2”: https://www.w3.org/WAI/WCAG22/quickref/
- Schema.org vocabulary: https://schema.org/
- OWASP Application Security Verification Standard: https://owasp.org/www-project-application-security-verification-standard/
- Web discovery question bank example (practitioner source, used only for coverage ideas): https://yourwebteam.io/website-discovery-questionnaire/
