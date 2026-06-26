# SF Clean Room — Design (v2: `get_records`)

**Status:** Draft → being implemented.
**Scope:** The second tool in the family — safe record/data export via the `get_records` subcommand. v1 (`get_metadata`) is unchanged; see [`01-design-v1.md`](01-design-v1.md).
**Principles:** [`00-design-principles.md`](../00-design-principles.md). **Goals/requirements rationale:** [`02-data-download.md`](../requirements/02-data-download.md). **Decision history:** [`docs-change-log.md`](../docs-change-log.md).

This document is the authoritative v2 contract. It states what the tool does; the ideation doc states why.

---

## 1. Purpose

`get_records` exports Salesforce **record data** for an org to a local folder safe for downstream automated consumers. Raw PII never reaches a file the consumer reads: every field is classified, and DROP/HASH actions are applied **in flight** before any value is written. The agent never queries Salesforce directly — it goes through this tool (principle A1).

## 2. The safety model

- **Read-only, absolutely.** `get_records` issues only describe and SOQL `SELECT` queries via the `sf` CLI. No code path writes to Salesforce. (A4)
- **No raw dump.** The raw query result lives only in the extractor's process memory; only the post-classification TSV is written to disk. (A2)
- **Abstraction.** The consumer reads a directory; it does not hold a Salesforce session. (A1)
- **Classifier = recommendation engine, not gate.** Every field gets a recommended action; a persisted plan may override it. Overrides are recorded in the audit. (B1–B4, C5)
- **Conservative default + safe-on-drift.** Unmatched and PII-shaped fields default to DROP. A field seen at extract time but absent from the plan is classified fresh by the conservative default and logged as drift — never silently emitted. (B4)

## 3. Classifier actions

First match wins. Implemented in `classify.py`; pattern lists in `constants.py`.

| Action | Applies to | Output |
|---|---|---|
| `RAW` | Salesforce intra-system IDs: `Id`, `*Id` references, `type=reference`, Jigsaw IDs | value as-is |
| `DROP` | direct PII (name/address/phone/DOB/photo/social-URL), special-category (GDPR Art. 9), free-text essays (`textarea` ≥ 30000; note/bio/statement-shaped ≥ 1000), formula-leak fields | column omitted |
| `HASH_EMAIL` | `type=email`, or name/label contains `email` | `sha256(lower(strip(v)))`, empty→empty |
| `HASH_ID` | externally-meaningful identifiers (membership/patron/external/card/account/government/industry IDs, social handles) | `sha256(strip(v))`, empty→empty |
| `PASS` | everything else — the analytical signal | value as-is |
| `DERIVE` | opt-in non-PII derivation (postcode→outcode, DOB→year-bucket); plan-only | derived value, raw dropped |

**Hash recipes are frozen and never salted** (`hashing.py`) so hashed columns join across sources. Hashed values replace the value in the same column (column name unchanged).

**Conservative fallback:** a field matched by no rule whose name/label/help-text contains a PII-shape pattern → DROP; otherwise → PASS. A `type=email` field whose name lacks "email" is **recommended** DROP and flagged in the plan — it does **not** abort (principle B2).

## 4. CLI surface

```
sf-clean-room get_records --org-alias <alias> --path <dir>
    [--only <Object> [<Object> ...]]
    [--where "<SOQL predicate>"]
    [--plan <file>]
    [--dry-run]
```

| Flag | Required | Meaning |
|---|---|---|
| `--org-alias` | yes | Authenticated `sf`/`sfdx` alias. |
| `--path` | yes | Publish directory. Mutated only at the final publish step. |
| `--only` | conditional | Objects to extract. Required unless the plan file supplies `[scope].objects`. |
| `--where` | no | SOQL predicate appended to every object's query. Requires `--only`. Validated (§7). |
| `--plan` | no | Classification plan file (TOML). With `--dry-run` the plan is written; without, it is consumed. |
| `--dry-run` | no | Probe + scan + classify only. Writes the annotated plan and prints a summary. No query of values, no publish mutation. |

These are all **narrowing / specification** inputs (principle C4); none loosen the classifier. This does not widen `get_metadata`'s surface — `get_records` is a separate subcommand, as the family design intends.

## 5. Pipeline

```
probe → schema-scan + classify → (load/merge plan) → extract+transform (to temp) → publish
```

1. **Probe** — resolve session; confirm Data API works (trivial `SELECT Id … LIMIT 1` on the first in-scope object); record describe access per object. Output `_capability-probe.json`. Data-API failure aborts.
2. **Schema scan** — `sf sobject describe` per in-scope object → field metadata. Run the classifier → a recommended action + reason per field. Admin free-text in the scan (labels/help/formula/picklists) is sanitised. Output `_schema-scan.csv`.
3. **Plan**
   - `--dry-run`: write the annotated plan (`[scope]`, informational recommendations as comments, empty `[overrides.*]`/`[reasons.*]` for the operator) and print a summary. Stop.
   - real run with `--plan <file>`: load overrides + reasons + scope. Effective action per field = override if present, else the fresh recommendation. New field absent from the plan → fresh recommendation (drift-safe), logged.
   - real run without `--plan`: pure classifier recommendations.
4. **Extract + transform** — per object: build SOQL projecting non-DROP fields; run `sf data query --json` (records returned in memory); apply HASH/DERIVE in flight; write `<Object>.tsv` into the per-run temp directory. Emit `_field-handling-applied.csv` (object, field, type, action, recipe, source=`default|override`, reason) and `_extract-summary.json` (per-object rows in/out, fields per action, `where_clause`, drift list). Raw values are never written.
5. **Publish** — clear `--path`; move every artefact in; move the sentinel `_field-handling-applied.csv` **last**.

## 6. Special-category overrides

Keeping a special-category field requires a justification string in `[reasons].<Object>.<field>`. Recorded in the audit. A special-category `[keep]`/`PASS`/`RAW` override **without** a reason is **not** an abort — the field is downgraded to DROP and the downgrade is reported in the summary and on stderr (principles B2, B4). Scoped to special-category fields only; ordinary overrides need no reason.

## 7. `--where` validation

Validated before any `sf` call; failure aborts (non-zero) before the Data API is touched:
non-empty after strip; no `;`; no SQL comment markers (`--`, `/*`, `*/`); no DML/DDL verbs (`INSERT UPDATE DELETE MERGE UPSERT CREATE DROP ALTER TRUNCATE`); no `LIMIT`/`OFFSET`; requires `--only`. Appended verbatim after `FROM <object>`. Logged in the audit and `_extract-summary.json`.

## 8. Output contract

A consumer reading a `--path` that contains `_field-handling-applied.csv` (the sentinel) may assume: the run completed; every field is accounted for in that file; no DROP field is present; hashed columns use the frozen recipes; one `<Object>.tsv` per extracted object. No sentinel → do not read.

## 9. Failure modes (fail closed)

| Failure | Behaviour |
|---|---|
| Session/Data-API unavailable | Abort before temp creation. Publish path untouched. |
| `--where` invalid | Abort before any `sf` call. |
| Neither `--only` nor `[scope]` objects | Abort with an actionable message. |
| describe/query fails for an object | Abort. Temp retained. Publish path untouched. |
| Special-category kept without reason | Not fatal: downgrade that field to DROP, report it, continue. |
| Schema drift (new field not in plan) | Not fatal: classify fresh (safe default), log it, continue. |
| Object returns 0 rows | Not fatal: write a header-only TSV, record in summary. |

Exit code: 0 on completed publish (including empty extracts), non-zero on any abort.

## 10. Reuse of v1 infrastructure

`get_records` reuses `audit.py` (per-run log, stderr tee), `config.py`/`paths.py` (temp root, fixed locations), the temp-then-publish discipline, and the sentinel-published-last rule. The publish helper is generalised: the sentinel name is a parameter (`package.xml` for v1, `_field-handling-applied.csv` for v2).

## 11. Deliberate simplifications (v2-initial), with rationale

- **`sf data query --json`, not the Bulk API.** Simpler, returns parsed records (no CSV embedded-tab corruption), and keeps raw values in memory only. Adequate for dev/edition orgs and moderate volumes. Bulk-API streaming for very large objects is future work; a SELECT exceeding a safe length aborts with a message recommending narrower `--only`/scope.
- **Hash in place** (column name unchanged) rather than a `_hash` suffix — matches the established extracts and keeps joins obvious.
- **Object scope is explicit** (`--only` or `[scope]`) rather than defaulting to all objects — bounds Bulk cost and avoids the wide-object SOQL-length limit.

---

## Appendix A — Implementation plan

1. `sfcli.py`: extract the hardened `sf` JSON runner from `session.py`; add `run_cli_json`/`run_cli_text`; refactor `session.py` to use it (no behaviour change).
2. `hashing.py`: `hash_email`, `hash_id` (frozen sha256 recipes).
3. `constants.py`: classifier pattern lists (PII, special-category, identifier, formula-leak sources), essay thresholds, action enum strings.
4. `classify.py`: `classify_field(meta) -> Recommendation(action, reason)` — pure, ordered rules.
5. `schema_scan.py`: describe objects → `FieldMeta` list; sanitiser for admin free-text; CSV writer.
6. `probe.py`: capability probe → dict; JSON writer.
7. `plan.py`: plan model; emit annotated plan; load/merge overrides + reasons + scope; effective-action resolution; drift detection; special-category-reason enforcement.
8. `records_extract.py`: SOQL builder (projection, `--where`), in-flight transform, TSV/audit/summary writers.
9. `records_pipeline.py`: orchestrator + `--dry-run` path; reuses `RunPaths`, `audit`.
10. `cli.py`: `get_records` subcommand + help (generated from constants); top-level help lists it.
11. Tests (Appendix B). 12. Docs: `regression-testing.md`, README, `tests/live_org.toml`, `.gitignore`.

## Appendix B — Test strategy

**Offline (always run, no org):**
- `classify.py`: table-driven cases covering every action, ordering (RAW before DROP for `*Id`), special-category, essay thresholds, formula-leak, email-not-named-email recommendation, conservative fallback.
- `hashing.py`: known-vector sha256, lower/strip, empty→empty, determinism (no salt).
- `plan.py`: emit→reload round-trip; override precedence; special-category reason enforcement (downgrade-without-reason); drift (new field → safe default).
- SOQL builder: projection excludes DROP; `--where` appended; `--where` validation rejects each forbidden pattern.
- In-flight transform: HASH applied, DROP omitted, RAW/PASS preserved; TSV escaping; empty-rows header-only.
- Sentinel/publish: `_field-handling-applied.csv` moved last; missing sentinel refuses publish.
- CLI parser: `get_records` flags; `--where` requires `--only`; top-level + per-command help; help runs without auth.
- Full regression: the entire existing v1 suite must stay green.

**Live (opt-in, chatbot-driven — see [`regression-testing.md`](../regression-testing.md)):**
- Org from `tests/live_org.toml` (default `example-dev-edition`); auto-skip if not authenticated.
- `get_records --dry-run` produces a plan; a real run produces TSVs + sentinel; audit shows no DROP field leaked; re-run is deterministic; v1 `get_metadata` still publishes with `package.xml`.
