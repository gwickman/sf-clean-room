# Documentation Change Log

Decision history for the design and ideation documents. Per principle **C6**, the design docs themselves hold only current facts; the *why-it-changed*, superseded approaches, and version-to-version evolution live here, where they can be as verbose as they need to be.

Newest entries first. Each entry records what changed, the before/after where useful, and the reasoning.

---

## 2026-06-04 — `get_records` (v2) designed, implemented, and tested

**Change.** Added the v2 contract `docs/02-design-v2.md` and implemented the
`get_records` subcommand end-to-end, with a full offline test suite and a
chatbot-driven regression guide.

**New source modules:** `sfcli.py` (shared, hardened `sf` runner — `session.py`
refactored onto it with no behaviour change), `hashing.py` (frozen SHA-256
recipes), `classify.py` (the field recommendation engine), `schema_scan.py`
(describe → field metadata + recommendations), `probe.py` (capability probe),
`plan.py` (classification-plan TOML: load/merge/override, special-category
justification, drift), `records_extract.py` (SOQL build + `--where` validation +
in-flight transform + TSV/audit/summary writers), `records_pipeline.py`
(orchestrator + dry-run). `constants.py` gained the classifier pattern lists;
`publish.py` was generalised so the sentinel name is a parameter
(`package.xml` for v1, `_field-handling-applied.csv` for v2); `cli.py` gained the
`get_records` subcommand and help.

**Key design choices (rationale in `02-design-v2.md` §11):**
- Extraction uses `sf data query --json` (records returned in memory, parsed),
  not the Bulk API — simpler, no CSV embedded-tab corruption, raw values never
  hit disk. Bulk streaming for very large objects is deferred; an over-long
  SELECT aborts with a "narrow scope" message.
- Hash in place (column name unchanged) rather than a `_hash` suffix.
- Object scope is explicit (`--only` or `[scope]`), not "all objects."
- DERIVE recipes are auto-inferred from field name (postcode→outcode,
  DOB→year); a DERIVE without an inferable recipe is treated as DROP (safe).

**Testing.** 125 offline tests pass (classifier, hashing, plan/override/
special-category/drift, SOQL + `--where` validation + transform + TSV escaping,
full mocked pipeline incl. sentinel and no-DROP-leak, CLI surface) plus the
entire v1 suite (regression-green). Live tests (`-m live`) and the chatbot-driven
steps in `docs/regression-testing.md` target the org in `tests/live_org.toml`
(default `example-dev-edition`) and auto-skip when it is not authenticated.
Chatbot-driven offline verification produced and inspected real artefacts
(plan, schema CSV, audit CSV, TSV, summary JSON), confirming no raw PII reaches
the TSV, hashing is applied, and the special-category downgrade-without-abort
works in the real pipeline.

**Known gap at time of writing:** the default test org `example-dev-edition` was
not authenticated on the build machine, so the *live* round was deferred (the
tooling must never auto-login). Everything offline is green; live runs are ready
to execute once the org is authenticated.

---

## 2026-06-03 — Decision history moved out of the design docs (this log created)

**Change.** Stripped the version-evolution narrative ("in v1 we…, now in v2 we…", "was the central tension", "were hard lines", "deliberate departure from the earlier model") out of `00`, `01`, and `02`, and created this log to hold it. Added principle **C6** ("Design docs hold current facts; decision history lives in the change log").

**Why.** The ideation docs had started to carry their own development history inline — comparisons against the earlier scripted pipeline, "we softened this," "this used to abort." That makes the docs longer, dates them, and forces a reader to reconstruct the current design from a sequence of edits. Splitting the two keeps the design docs evergreen and keeps the reasoning recoverable.

**What was removed from `02` and is preserved here:**

- **Former §6 "How v2 differs from v1 mechanically."** The substantive facts it stated all live elsewhere in `02` now (raw handling in §2, sentinel in §4.6, operator role in §2–3, the hashing requirement in §3). The *comparison* itself was the only thing lost, and it is captured in the v2-control-model entry below.
- **Former §10 "Deliberate departure from the earlier model."** Captured in the v2-control-model entry below.
- Assorted asides: `02` §1 "the reframing from v1"; §3 "carried over from the prior pipeline"; §4.3/§4.4 "the prior pipeline aborts… v2 removes"; §5 "in v1 the question was adversarial"; §7 "(under the new model)"; §9 "(Resolved — now a requirement)".
- **In `01`:** the "(Contrast with scrub-after-retrieve… rejected)" aside in §4.1, and the §7 closing paragraph ("these are the threads v2 picks up… reuses v1's spine… swaps the unit of safety").

**Kept in the docs deliberately:** the "How the principles divide v1 from v2" section in `00`. Comparing two tools that *coexist* in the family is a present-tense design fact, not history (C6 spells out this distinction).

---

## 2026-06-03 — `02` v2 control model: from rigid gate to trusted-operator collaboration

This is the central design decision for the record-download tool, and the reason most of the narrative above existed.

**Earlier reference model (the scripted `downloading-salesforce-data` pipeline).** Three standalone scripts (capability probe, schema scan, hashed extract) with a runtime field classifier treated as an immovable safety boundary. Its control model assumed an **untrusted operator** and tried to mechanically prevent every mistake:

- The classifier was "the safety boundary, never disable it."
- An unclassified `type=email` field **aborted** the run, forcing a human to classify it.
- Undetected formula-leaks **aborted**.
- Production aliases required **explicit per-task authorisation**.
- "Hard lines" that no override could cross: `textarea ≥ 30000` → DROP; special-category → DROP; DOB → DROP.

**Decision (Grant, 2026-06-03).** Assume the operator is a **flagship, privacy-aware model** already making a genuine effort to follow the governing privacy rules, and design to leverage that intelligence rather than treat it as an adversary. The earlier model is too fragile — every abort is a forced human decision, which is an anti-pattern for an autonomy-first tool. Specifically:

- **Forcing a human decision is an anti-pattern.** Replaced the aborts with: the tool recommends the conservative action (DROP) in its annotated-schema response and proceeds. `type=email`-unclassified → recommend DROP/HASH_EMAIL, no abort. Formula-leak → flag with recommended action, no abort.
- **The classifier became a recommendation engine, not a gate.** It runs a schema scan and returns an annotated schema with recommended classifications; the operator can override (it may already know it needs specific data, or the user authorised it).
- **Soften the hard lines** to strong default recommendations the operator can override (with audit) — *except* the genuinely mechanical guarantees.
- **Keep "Read-only, period."** absolute.
- **Drop "per-task prod authorisation"** as a tool requirement — abstraction from direct Salesforce access (A1), not gatekeeping, is what satisfies the "no AI direct access to production" rule.
- The durable, non-negotiable floor shrank to three mechanical guarantees: **read-only (A4), no-raw-dump (A2), abstraction (A1).** Everything else is a recommendation the trusted operator refines, with the audit trail (C5) making each judgment call reviewable.

**Reused wholesale from the earlier model:** the classifier's action taxonomy (RAW/DROP/HASH_EMAIL/HASH_ID/PASS/DERIVE), the field-shape rules, and the frozen, never-salted hash recipes (so hashed columns still join across sources). The *rules* were proven; only the *control model* changed.

**Mechanical v1↔v2 differences (the former §6), preserved for reference:**
- v1's temp tree holds already-safe metadata; v2's raw data is never safe, so classification happens in-stream between Bulk API and the first write — only already-classified TSVs touch disk.
- Sentinel differs: v1 = `package.xml` (manifest); v2 = `_field-handling-applied.csv` (audit). Both written last.
- v1 operator runs but cannot weaken (credentials = zero-judgment); v2 operator actively shapes the extract via the classification plan (PII = judgment).
- v1 only omits; v2 must actively transform (hash) so output stays joinable.

**Escape hatch recorded with the decision:** if real use shows the trust is misplaced for a particular harm, promote *that specific harm* into the mechanical floor (A3) rather than re-rigidifying the whole classifier.

---

## 2026-06-03 — `02` special-category overrides require a recorded justification (open question → requirement)

**Before.** Keeping a special-category (GDPR Art. 9) field was permitted as a high-risk override, flagged in the audit, but the doc left "how conspicuous must it be?" as an open question.

**After (requirement §4.5).** A `[keep]` of a special-category field must carry a short free-text justification string, recorded in `_field-handling-applied.csv`. An *unjustified* special-category keep does **not** abort (that would violate B2) — the tool downgrades that one field to the safe default (DROP) and reports it.

**Why.** This was the cleanest way to make "trust the flagship operator" verifiable after the fact without reintroducing a hard abort: justifying is the only way to actually retain the field, but failing to justify costs only that field and never halts the run. Satisfies safe-by-default (B4) and no-forced-decision (B2) simultaneously. Scoped narrowly to special-category fields so ordinary overrides stay friction-free.

---

## 2026-06-03 — `02` headless / scheduled runs from a persisted plan (requirement added)

**Change.** Added requirement §4.7 and a supporting clause to principle **B3**: a reviewed classification plan is a persistable run specification that executes **non-interactively, with no agent in the loop**, so a scheduler (Task Scheduler/cron) can refresh a dataset on a cadence.

**Why (Grant, 2026-06-03).** After an initial interactive probe/scan/review pass, the common case is re-downloading a specific dataset regularly. The agent's intelligence is needed to *author* the safety decisions, not to *execute* them. Key safety property attached to the decision: **schema drift defaults safe** — a field present in a later scan but absent from the plan falls back to the conservative classifier default and is logged, so a new sensitive field can never silently enter the output just because the plan predates it. Drift is reported, not fatal.

---

## 2026-06-03 — Repo-wide genericisation

**Change.** Removed all references to specific organisations, projects, individuals, and cross-repository paths from the tracked, product-facing files (`pyproject.toml` author field, the ideation docs, `CLAUDE.md` content). The governing policy is referred to generically as "an organisational AI acceptable-use policy"; prior real-world extraction work is referred to as "the earlier pipeline" / "prior extracts" without naming clients.

**Why (Grant).** The repo is intended to be a generic, shareable tool. Decision: **Salesforce is intrinsic** to the tool and stays named throughout; everything else (companies, client projects, people, private repo paths) is abstracted. SOAP/Salesforce protocol namespaces and the `<host>` placeholder in source are protocol constants, not leakage, and were left as-is. The `CLAUDE.md` filename was kept (it is a required harness convention) but its content was made vendor-neutral.

---

## 2026-06-03 — Initial documentation restructuring

**Change.**
- Renamed `docs/design.md` → `docs/01-design-v1.md` (git-tracked rename, history preserved); updated the references in `CLAUDE.md` and `README.md`.
- Created `docs/ideation/` with `00-design-principles.md` (family-wide principles), `01-metadata-ideation.md` (v1 goals/requirements, one altitude above the v1 contract), and `02-data-download.md` (v2 goals/requirements).

**Why.** The single `design.md` was the v1 contract only. Numbering it and adding an `ideation/` folder makes room for the planned tool family (metadata export, record download, …) and separates *contract* (the authoritative `01-design-v1.md`) from *rationale* (the ideation docs) from *principles* (the constitution all versions answer to).
