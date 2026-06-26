# SF Clean Room — Design (v4: `get_technical_objects`)

**Status:** Draft — for review before implementation.
**Scope:** The fourth tool in the family — safe export of the 40 Salesforce **technical objects** (Tooling entities, system tables, REST metrics endpoints). v1–v3 are unchanged.
**Principles:** [`00-design-principles.md`](../00-design-principles.md). **Goals/requirements:** [`05-technical-objects.md`](../requirements/05-technical-objects.md). **Schema:** [`salesforce-technical-objects.md`](../reference/salesforce-technical-objects.md). **Decision history:** [`docs-change-log.md`](../docs-change-log.md). **Companion plan:** [`05-plan-v4.md`](../plan/05-plan-v4.md).

This document is the authoritative v4 contract.

---

## 1. Purpose

`get_technical_objects` downloads the catalogued technical objects for an org and publishes them **anonymised** to a local folder: one CSV per object, every column classified in flight (RAW / HASH / DERIVE / PASS / DROP), blob and long-text fields never even selected. The agent gets the org's operational truth — code/test health, job machinery, privilege topology, login/session/MFA activity, setup audit, usage telemetry, limits — keyed by pseudonymous Salesforce IDs, with IPs reduced to network prefixes, geolocation to country/subdivision, emails/usernames hashed, and data-echoing free text dropped.

The download mechanics are those proven in `ai-framework`'s `salesforce_download_technical_objects`: a metadata-driven catalogue routes each object to the right API (SObject SOQL / Tooling / REST pseudo-endpoint), field lists come from describe with a structural skip-list, EntityDefinition uses keyset pagination. The changes for sf-clean-room: classification in memory before any write (A2), REST `queryMore` pagination instead of the Bulk API (no new dependency, no raw-CSV transport), per-object skip-and-log instead of print-and-continue, and the family's temp-then-publish + sentinel discipline.

## 2. Safety model

- **Read-only.** SOQL `query`/`queryMore`, Tooling `query`, and two REST `GET` endpoints. No write path. (A4)
- **No raw dump.** Query results live in process memory; only post-classification CSVs are written. (A2)
- **Exclude at source.** Layer-0 skip: field types `base64`, `textarea`, `address`, `location`, `complexvalue`, `anyType` and field names `Body`, `Metadata`, `SymbolTable`, `FullName`, `HtmlValue`, `Content` are never included in any SELECT — source code, log bodies, and long text never transit. (the v1 move, applied at field level)
- **Catalogue and classifier are source-controlled.** The 40-object catalogue (API routing + special cases) and the classification rules (generic + curated per-object overrides) are source constants; no runtime mechanism adds objects, re-routes them, or disables classification. A reviewed plan may override per-column actions; the **exposing direction requires a recorded justification** or it downgrades to the safe default (the v2/v3 rule).
- **Abstraction.** The agent reads the published folder; the tool holds the session. (A1)
- **Pseudonymous output.** Activity and privilege tables are keyed by Salesforce IDs (RAW); no name/email/IP survives in the clear.

## 3. Classification

Layer 0 (structural skip) then Layer 1 (first match wins): curated per-object overrides → ids/references RAW → IP-named DERIVE(prefix) → email HASH → phone DROP → URL DERIVE(sanitise) → fine geo (lat/lon/city/postcode) DROP, coarse geo (country/subdivision/state) PASS → free-text echoes DROP → else PASS. Full rules and the curated table: requirements §3. Reuses `hashing.py` recipes and the `eventlog_classify` derive helpers (IP prefix, URL sanitise).

The curated overrides include: `FlowInterview.InterviewLabel`/`.PauseLabel` DROP, `SetupAuditTrail.Display` DROP / `.DelegateUser` HASH, `IdpEventLog.IdentityUsed` HASH, `Organization.PrimaryContact` DROP, `*.ExtendedStatus` and `BackgroundOperation.Error` DROP, `ApexLog.Status` DROP, `VerificationHistory.Remarks` DROP, `LoginHistory.Status` PASS (documented vocabulary), `CronTrigger.CronExpression` PASS.

**Note on Profile/PermissionSet/Role:** v4 downloads their *sObject rows* (privilege topology — structural columns + permission bits). This does not touch v1's deny list, which excludes their *Metadata API XML* for retrieve-fragility and payload reasons (requirements §3.3).

## 4. CLI surface

```
sf-clean-room get_technical_objects --org-alias <alias> --path <dir>
    [--only <Object> [<Object> ...]]
    [--limit <N>]
    [--plan <file>]
    [--dry-run]
```

| Flag | Required | Meaning |
|---|---|---|
| `--org-alias` | yes | Authenticated `sf`/`sfdx` alias. |
| `--path` | yes | Publish directory. Cleared only at the publish step. |
| `--only` | no | Objects to include (default: the full catalogue). Unknown names abort with the valid list. |
| `--limit` | no | Max rows per object — smoke-test narrowing, mirrors the proven tool. |
| `--plan` | no | Classification plan (TOML): `[scope].objects` and `[overrides."Object.Field"]` (+ `[reasons]`). Written by `--dry-run`, consumed by a real run. |
| `--dry-run` | no | Describe + classify only: report the per-object column plan and row estimates. No record values, no publish mutation. |

All narrowing/specification inputs (C4). No flag disables the skip-list or the classifier.

## 5. Pipeline

```
session → for each catalogued object (scope-filtered):
            describe → layer-0 skip → classify columns → build SELECT (non-DROP cols)
            → page results (queryMore / Tooling / REST) → transform rows in flight (to temp)
        → audit + summary → publish (sentinel last)
```

- **Routing** per the catalogue: `tooling` (describe + query via `/tooling/`), `soql` (REST query + queryMore), `entitydef` (keyset pagination on `QualifiedApiName`, batch 2000), `rest_limits` / `rest_recordcount` (fixed schemas `LimitName,Max,Remaining` / `ObjectName,RecordCount` — pure metrics, all PASS).
- **DROP columns are never selected** (like `get_records`): the SELECT contains only RAW/HASH/DERIVE/PASS columns, so dropped content never transits.
- **Per-object fault tolerance** (v2.1 discipline): describe or query failure for one object → skip, record bucket + verbatim detail to the audit log, continue. Only session failure or *every* object failing aborts.
- **Output:** `<path>/<ApiName>.csv` per object; `_field-handling-applied.csv` (object, column, type, action, recipe, source, downgraded — the sentinel, moved last); `_extract-summary.json` (per-object rows/columns/action-counts, skipped objects with buckets, the limit used). Snapshot model: clear-and-republish, like `get_records`.

## 6. Failure modes

| Failure | Behaviour |
|---|---|
| Session unavailable | Abort before temp. |
| One object's describe/query fails (permission, edition) | Skip-and-log (recorded in summary + audit), continue. |
| Every object fails | Abort — fail-closed; publish path untouched. |
| Unknown `--only` name | Abort before any query, listing valid names. |
| Plan override in the exposing direction without justification | Downgrade to safe default, report, continue (B2/B4). |
| Object returns 0 rows | Header-only CSV, recorded; not fatal. |

Exit 0 on completed publish; non-zero on abort.

## 7. Output contract

A consumer reading a `--path` containing `_field-handling-applied.csv` may assume: the run completed; one CSV per successfully-extracted catalogued object; every column accounted for in the audit; no Layer-0 field, no DROP column, no raw IP/email/username/fine-geo present; hashed columns use the frozen recipes (joinable to the other extracts); skipped objects are listed in `_extract-summary.json`. No sentinel → do not read.

## 8. Deliberate simplifications (v4-initial)

- **queryMore pagination, not Bulk.** No `simple-salesforce` dependency, no raw-CSV-on-the-wire; slower on enterprise-scale `GroupMember`/`LoginHistory` — acceptable first; Bulk is future work if real runs hurt.
- **Snapshot, not incremental.** Retention-limited tables (LoginHistory 6 mo, SetupAuditTrail 180 d) would benefit from event-log-style accumulation later; the snapshot model ships first and does not preclude it.
- **`Description` columns DROP by default** (overridable with justification) — revisit after first real runs (requirements §7.1).
- **No redacted form of dropped free text** — future work alongside 04's SOQL sanitiser.

## 9. Reuse of family infrastructure

`session.py`, `sfcli.py` (token), `audit.py`, `hashing.py`, `eventlog_classify.derive_ip_prefix`/`sanitise_url`, `publish.py` (sentinel + clear-and-republish), `config.py` temp-root, the plan/justification pattern from `eventlog_plan.py`, and the skip-and-log discipline from v2.1.

---

## Appendix A — Implementation plan (summary)

Detailed in [`05-plan-v4.md`](../plan/05-plan-v4.md): (1) `technical_catalog.py` — the 40-object catalogue constant; (2) `technical_classify.py` — Layer-0 skip + Layer-1 rules + curated overrides; (3) `technical_download.py` — describe/query/queryMore/Tooling/REST/EntityDefinition transports (injectable HTTP); (4) `technical_pipeline.py` — orchestrator + dry-run + audit/summary/publish; (5) plan support; (6) `cli.py` subcommand + help; (7) tests offline (classifier table, curated overrides, pagination, per-object skip, no-raw-dump leak checks) + live against the test org; (8) docs: README (C8), `regression-testing.md` (C7), change log.
