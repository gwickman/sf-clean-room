# 02 — Record / Data Download (v2): Goals and Requirements

**Status:** Ideation. No contract yet; this is the input to a future `02-design-v2.md`.
**Governed by:** [`00-design-principles.md`](00-design-principles.md) — read it first.
**Companion:** [`01-metadata-ideation.md`](01-metadata-ideation.md) and the v1 contract [`../01-design-v1.md`](../01-design-v1.md).

---

## 1. The problem

Agents need the org's **data values** — to validate a model against real distributions, trace records across orgs, count fill rates, reconcile grains — not just its structure. The naive move (`sf data export bulk` → a CSV the agent reads) hands the AI raw PII, special-category data, and bulk personal-data dumps — Restricted under any reasonable acceptable-use policy, never to be processed.

The job: fold safe record extraction into the `sf-clean-room` CLI as the `get_records` subcommand (reserved in the design contract, §4.1), so the agent gets the org's data **without ever touching Salesforce directly and without raw PII ever landing where it can read it.**

The unit of safety for record data is the **field**, and field-level safety is mostly a **judgment call** rather than a fixed rule: which custom fields carry PII cannot be fully known ahead of time, because orgs name and add fields freely. So the tool **abstracts the agent from Salesforce, performs the dangerous mechanics safely, recommends a classification for every field, and lets the trusted operator refine it.** (Principles A1, A2, A3, B1–B4.)

## 2. What is mechanical vs. what is collaborative

The split is the whole design.

**Mechanical and non-negotiable** (principle A3 "zero-judgment harms", A4, A2):
- **Read-only.** No writes, ever. No override.
- **No raw dump.** There is no code path that writes a raw, unclassified extract to disk or sends raw values anywhere except into the in-flight classifier. The raw Bulk-API stream exists only in the extractor's memory. (Fields the operator classifies as PASS/RAW *are* emitted as values — that is the analytical signal, chosen deliberately, recorded in the audit. The guarantee is "nothing reaches disk except through the classification plan," not "no value ever reaches disk.")
- **Abstraction.** The agent obtains data only through `get_records`; it does not run its own `sf data query`/`export`. This is the durable safety property (A1).

**Collaborative and overridable** (principle A3 "judgment calls", B1–B4):
- Which fields are PII that matters, which identifiers should hash vs. pass, whether a long-text or special-category field is genuinely needed for the analysis. The tool **recommends**; the trusted operator **decides**, with context the tool lacks (the user's authorised analytical need). Every override is recorded (C5).

## 3. The classifier as a recommendation engine

The classifier reads each field's `Describe` metadata (name, label, type, length, `calculated`/`formula`, help text) and **recommends** one action. The actions, and the fixed hash recipes that let hashed columns join across sources:

- **RAW** — Salesforce intra-system IDs (`Id`, `*Id` references, `type=reference`). Emitted as-is: opaque outside Salesforce, and keeping them lets an analyst locate the real record.
- **DROP** — recommended for direct PII (names, addresses, phones, DOB, photos, social URLs), special-category data (GDPR Art. 9), free-text essays, and **formula-leak fields** (calculated fields whose formula references a PII source — the subtle one that launders PII onto child objects and defeats row-level hashing).
- **HASH_EMAIL** — `sha256(lower(strip(value)))`, empty → None.
- **HASH_ID** — externally-meaningful identifiers (membership/patron numbers, cross-system external IDs, card/account/government/industry IDs, social handles). `sha256(strip(value))`, empty → None.
- **PASS** — everything else: the analytical signal (picklists, booleans, counters, currency, dates except DOB, categories/cohorts).
- **DERIVE** — opt-in non-PII derivation (UK postcode → outcode, DOB → year-of-birth bucket), raw dropped.

**Hash recipes are frozen and never salted** — the one part of classification that is *not* an operator preference. Salting, or an operator picking an ad-hoc recipe, would break the cross-source join (e.g. a parallel extract from another system, or the same logical entity held in two different orgs). The recipe is mechanical; *whether* a field hashes is the judgment call.

These recommendations are **defaults, not gates** (principle B4). The shipped defaults are deliberately conservative so that an operator who accepts them wholesale gets a safe artefact; an operator with context may override, and the override is audited rather than blocked.

## 4. Requirements

### 4.1 The collaborative pipeline

The pipeline is a **recommend → refine → extract** loop, where `--dry-run` produces the plan and a real run consumes it:

1. **Capability probe** (read-only, no record data). Confirm the alias can reach the Data API and the target objects; surface FLS/permission holes early. Output `_capability-probe.json`. If the Data API is blocked, abort — this is a genuine blocker, not a judgment call.
2. **Schema scan + annotation** (read-only, metadata only — no row values). For each in-scope object, fetch every field's `Describe`, run the classifier, and emit an **annotated schema / classification plan**: every field with its recommended action and the reason. Admin free-text that flows into the scan (labels, help text, formulas, picklists) is sanitised in flight. This is the collaboration surface and the natural output of `get_records --dry-run`.
3. **Operator review / override.** The agent reads the annotated schema and, with the user's authorised analytical need, may change any recommendation — keep a field the tool would DROP, switch a PASS to HASH_ID, etc. Overrides are expressed as an explicit, recordable classification plan (see §5). The operator is trusted (B1) and accountable via the audit (C5).
4. **Hashed extract** (read-only, hashed in flight). Per object: build SOQL excluding DROP fields, run via Bulk API, **stream-transform raw → TSV applying the agreed plan before any file is written**, emit `<Object>.tsv`, the audit `_field-handling-applied.csv` (object, field, type, action, recipe, and whether it was a default or an operator override), and `_extract-summary.json` (rows in/out, fields dropped/hashed/kept, the `where_clause` used).

### 4.2 Iterative refinement (a first-class requirement)
The tool and agent must be able to **converge on the right extract across repeated runs** (principle B3). Concretely: `--dry-run` produces the annotated plan cheaply and without touching values; the operator edits the plan; a real run consumes it; the operator inspects the audit and may re-run with a revised plan. The tool must make this loop fast, self-describing, and idempotent. A single perfect invocation is not assumed — refinement is the expected path.

### 4.3 Autonomy — no forced human decisions (principle B2)
The tool does not abort on ambiguous classification; it recommends the conservative action and proceeds. Specifically:
- A `type=email` field not otherwise classified → the annotated schema flags it clearly and **recommends DROP** (or HASH_EMAIL where the type makes intent obvious).
- A calculated field whose formula references a PII source but isn't yet classified → flagged in the annotated schema with a **recommended DROP/HASH**, with the offending source named.
- Any field the classifier cannot confidently place → **recommend the conservative action (DROP)** and say so.

The operator resolves these from the annotated schema as part of normal review. The only things that abort are genuine zero-judgment blockers: Data-API failure, a write being attempted, or a request that would bypass the tool to dump raw data.

### 4.4 Default handling of high-risk field shapes
These field shapes carry a **strong default recommendation** with its rationale attached, but the trusted operator may override them (and the override is audited). The rationale travels with the recommendation so the operator can weigh it:
- `textarea` length ≥ 30000 → **default DROP** (essay fields routinely carry biographical/third-party content). Overridable if the analysis genuinely needs the text.
- Special-category data (ethnicity, gender, disability, nationality, religion, orientation, health/biometric/genetic) → **default DROP** (GDPR Art. 9). Overriding is the highest-risk class — flagged as such in the audit so it is conspicuous for human review.
- Date of birth → **default DROP** (hashing a DOB leaks set-membership; prefer a DERIVE year-bucket if age-cohort signal is needed). Overridable.

Read-only and no-raw-dump (§2) are not defaults but mechanical guarantees; they are never overridable.

### 4.5 Special-category overrides require a recorded justification
Keeping a special-category field (GDPR Art. 9) is the highest-risk judgment call the operator can make, so it must be **self-explaining in the audit, not just visible.** A `[keep]` of a special-category field in the classification plan must carry a short free-text justification string (e.g. `reason = "lawful basis confirmed by user for cohort analysis"`). The tool records that string in `_field-handling-applied.csv` alongside the field, so a later human reviewer sees *why* the default was overridden, not merely *that* it was.

If a special-category field is kept **without** a justification, the tool does **not** abort (that would violate B2) — it falls back to the safe default (**DROP**) for that field and reports the downgrade clearly in its response and the audit. The effect: justifying a special-category keep is the only way to actually retain it, but failing to justify costs the operator nothing except that field, and never halts the run. This keeps the safe path the default (B4) while making every special-category retention a deliberate, documented act.

This requirement applies only to special-category fields. Ordinary `[keep]`/`[hash_id]`/`[drop]` overrides need no justification string — they are recorded as default-vs-override in the audit (§4.1) but carry no extra friction.

### 4.6 Output contract and sentinel
Output lands at the fixed asset path `…/anonymised-salesforce-data/<alias>/`. The **sentinel is `_field-handling-applied.csv`** — its presence at the alias-folder root signals a complete, audited extract; absent it, treat the run as failed and do not consume (principle C2). A consumer reading a sentinel-complete folder may assume every field is accounted for in the audit, hashed columns use the frozen recipes (and therefore join across sources), and every departure from the default recommendation is recorded.

### 4.7 Headless, scheduled runs from a persisted plan
The recommend→refine→extract loop (§4.1–4.2) needs an operator only to *author* the plan, not to *execute* it. Once agreed, the plan is a complete, persistable run specification — objects in scope, per-field actions and overrides, `--where` predicates, derive rules, and any special-category justifications. A persisted plan must be runnable **non-interactively, with no agent in the loop**, so a scheduler (Windows Task Scheduler, cron) can refresh a specific dataset on a cadence. This is the common case after the first interactive pass: go through probe → scan → review once, persist the plan, then re-run it on a schedule.

Requirements for the headless path:

- **Plan as input.** `get_records` accepts a saved plan (e.g. `--plan <file>`) alongside `--org-alias` and `--path`. With a plan supplied, a real run needs no `--dry-run` and no operator review — it extracts directly. This is a *narrowing/specification* input (principle C4), not a safety-loosening knob: it pre-records judgments the operator already made and reviewed.
- **Re-scan every run; apply the plan over fresh schema.** A headless run still runs the capability probe and schema scan, then applies the saved plan to the freshly described fields. It does not trust a stale schema snapshot — orgs gain and change fields between runs.
- **Schema drift defaults safe.** Any field present in the new scan but absent from the plan falls back to the conservative classifier default (DROP for anything PII-shaped, the recommended action otherwise) and is logged as drift. A new sensitive field can never silently enter the output just because the plan predates it. This is the property that makes unattended scheduling safe (principle B4 applied across time).
- **Drift is reported, not fatal.** New, changed, or removed fields are recorded in the audit and surfaced in `_extract-summary.json` so a later review (human or agent) can fold them into the plan — but their presence does not abort the run. Only genuine blockers (Data-API failure, a removed in-scope object) still fail closed.
- **Deterministic and machine-readable.** Same plan + same org state → same output. The exit code plus `_extract-summary.json` and the audit CSV are sufficient for a scheduler or a downstream job to decide success without parsing prose.

The division of labour: an agent (or a person) goes through probe → scan → review *once* to produce a reviewed plan; thereafter the plan runs itself on a schedule, safe-by-default against drift, with the operator re-engaged only when drift or a changed analytical need warrants a fresh review. The agent authors the safety decisions; the schedule executes them.

## 5. The collaboration mechanism

The design question: **how does the operator's classification decision flow into the extract, auditably?**

The recommended shape:
- `get_records --dry-run` emits the annotated schema **as an editable classification plan file** (e.g. a TOML/CSV the operator can amend). It is the *agreed plan*, not a locked override gate. Its `[drop]`/`[hash_id]`/`[keep]`/`[derive]`/`[scope]` sections express the operator's decisions.
- A real `get_records` run consumes that plan and extracts accordingly.
- The audit records, per field, the final action and whether it came from the default or an operator override — so a human reviewer sees exactly where judgment was applied. A `[keep]` of a special-category field additionally carries the operator's justification string (§4.5); without it, the tool downgrades that field to DROP rather than aborting.

Narrowing inputs stay as safe CLI flags (principle C4): `--only <objects>` and a validated `--where` predicate (non-empty; no `;`; no SQL comment markers; no DML/DDL verbs; no `LIMIT`/`OFFSET`; requires `--only`; appended verbatim and logged). These cannot expose anything — the classification plan still runs on every returned row — so they need no gating.

What is **not** on the surface and not in the plan: anything that would disable the in-flight classification machinery wholesale, write to Salesforce, or dump raw rows. Those are the §2 mechanical guarantees; there is no knob for them.

## 6. Acceptable-use compliance map

| Policy rule | How v2 complies |
|---|---|
| The agent may not process Restricted data (bulk personal data, financial PII, special-category data) | No raw-dump path (§2); classification applied in flight; the agent reads only TSVs produced through the agreed plan. Special-category defaults to DROP; keeping one requires a recorded justification string and silently downgrades to DROP without it (§4.5), so every Art. 9 retention is deliberate and self-explaining in the audit. |
| Anonymisation/pseudonymisation mandatory before AI analysis of bulk personal data | Conservative DROP/HASH defaults; frozen recipes keep output joinable; departures are explicit and recorded — the trusted operator (B1) carries the residual judgment the policy expects of it. |
| No transmitting non-public data to non-approved platforms | All output local; the only network call is the authorised `sf` CLI. |
| No AI direct access to production systems | The tool **abstracts** the agent from Salesforce (A1): the agent never gets direct access, only hashed, plan-shaped access through `get_records`. Abstraction, not gatekeeping, is what satisfies this rule. |
| No fine-tuning/RAG on extracted data | TSV outputs are for in-session analysis only. |
| On accidental Restricted exposure → stop, escalate to a human owner, don't auto-clean | The tool fails closed on genuine blockers and names fields (not values) in messages; the operator surfaces up rather than auto-remediating. |

## 7. Out of scope for v2 (candidate boundaries to confirm)

- Writing to Salesforce — permanently out (A4).
- Pulling metadata — that is `get_metadata`'s job; the schema scan here uses `sobject describe`, not `project retrieve`.
- Content-level redaction *inside* kept free-text — essays are DROPped by default rather than redacted; finer redaction is a later stage.
- Cross-object referential sampling (a record plus its related graph) — useful, but later than getting field-level collaboration right.

## 8. Open questions for the v2 design doc

1. **Plan file format and location.** TOML vs CSV; project-local (versioned with the consuming project) vs a fixed config location. The plan is the operator's decision record, so it should be human-reviewable and live with the project's other assets.
2. **One subcommand or a scan/extract split?** Leaning: one `get_records` subcommand where `--dry-run` emits the annotated plan and a real run consumes it, which makes the recommend→refine→extract loop (B3) the obvious path. The intermediate artefacts (`_capability-probe.json`, `_schema-scan.csv`, annotated plan) are still published for inspection.
3. **Whole-object default vs forced `--only`.** Bulk-API cost and the wide-object SOQL-length limit (some standard objects, e.g. `User`, can carry 500+ fields, and the full column list can exceed the 100k-character SOQL limit) argue for narrow projection by default. Likely require `--only` or a `[scope]` in the plan rather than defaulting to "every object."
4. **Encoding hardening — a hard requirement.** Windows cp1252 mojibake corrupts non-ASCII values before hashing and breaks cross-source joins. Mandate `encoding="utf-8"` on every `sf` subprocess call. Correctness, not nicety.
5. **TSV robustness.** Embedded tabs/newlines in field values can split rows. v2 needs proper quoting/escaping for reliable field-level analysis.
6. **Special-category visibility.** Beyond the per-field audit record (§4.5), whether to *also* surface a summary count of special-category retentions on stderr for at-a-glance operator visibility.
