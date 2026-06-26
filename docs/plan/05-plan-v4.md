# SF Clean Room — Implementation Plan (v4: `get_technical_objects`)

**Authoritative contract:** [`05-design-v4.md`](../design/05-design-v4.md). Where this plan and the design disagree, the design wins.
**Grounding:** the proven `ai-framework` tool `salesforce_download_technical_objects.py` + its routing JSON (`salesforce_standard_object_metadata.json`), and the field-level schema reference [`salesforce-technical-objects.md`](../reference/salesforce-technical-objects.md).

Ordered; each step names its gate.

## 0. Pre-flight
1. Editable install resolves to `src/` (`regression-testing.md` §1); `pytest -q` green baseline. (The site-packages shadow has recurred repeatedly — check first.)

## 1. `technical_catalog.py` — the object catalogue (source constant)
One entry per object: `api_name`, `transport` (`soql` | `tooling` | `entitydef` | `rest_limits` | `rest_recordcount`), optional notes. Derive transports from the proven tool's routing: Tooling for the 9 Apex-tooling objects + `DebugLevel`/`TraceFlag`; `entitydef` for `EntityDefinition`; `rest_*` for `limits`/`recordCount`; `soql` for everything else (the proven tool's Bulk-routed objects all also support SOQL — v4 uses queryMore pagination per design §8). All 40 objects from the schema reference. Also `LAYER0_SKIP_TYPES` / `LAYER0_SKIP_NAMES` (the proven tool's skip-lists, verbatim).

**Tests:** catalogue has exactly the 40 documented names; transports cover every entry; no duplicates. **Gate:** green.

## 2. `technical_classify.py` — classifier
- `CURATED: dict["Object.Field", (action, recipe)]` — the table in requirements §3.2.
- `classify_field(object_name, field_meta) -> (action, recipe)`: curated first, then the generic rules (ids/references RAW; IP DERIVE/`ip_prefix`; email HASH/`email`; phone DROP; URL DERIVE/`url_sanitise`; fine-geo DROP / coarse-geo PASS; free-text-echo names DROP; else PASS). Reuse `eventlog_classify.derive_ip_prefix` / `sanitise_url`; `hashing.hash_email` / `hash_id`.
- `transform_value(action, recipe, value)` — coerce scalars, apply.

**Tests (table-driven, from the schema reference):** every curated row; `LoginGeo` lat/lon/city/postcode DROP vs country/subdivision PASS; `AuthSession.SourceIp` DERIVE; `Group.Email` HASH; `LoginHistory.Status` PASS; `PermissionsModifyAllData` PASS; `ApexTestResult.Message`/`StackTrace` DROP; unknown PII-shaped name → conservative default. **Gate:** green.

## 3. `technical_download.py` — transports (injectable HTTP for tests)
- `describe_fields(session, obj, transport)` — SObject vs Tooling describe; apply Layer-0 skip; return field metas (name, type).
- `page_soql(session, soql)` — REST `query` + follow `nextRecordsUrl` (queryMore); yields record dicts; strips `attributes`.
- `query_tooling(session, soql)` — Tooling query endpoint (note: no queryMore loop in the proven tool; add `nextRecordsUrl` follow anyway — Tooling supports it).
- `page_entitydefinition(session, fields, limit)` — keyset pagination `WHERE QualifiedApiName > '<last>' ORDER BY QualifiedApiName LIMIT 2000` (ported from the proven tool).
- `fetch_limits(session)` / `fetch_recordcount(session)` — the two fixed-schema REST endpoints.
- `--limit` applied in SOQL (`LIMIT N`) and as a row cap when paging.

**Tests:** queryMore loop follows `nextRecordsUrl` to exhaustion; EntityDefinition keyset pagination terminates and de-dups; limits/recordCount parse the documented JSON shapes; Layer-0 skip removes `Body`/textarea fields from the describe result. **Gate:** green.

## 4. `technical_plan.py` (or extend `eventlog_plan.py`) — plan
`[scope].objects`, `[overrides."Object.Field"] = action`, `[reasons."Object.Field"]`. Exposure ranking + downgrade-without-justification, exactly the v3 rule. `emit_plan(classified_columns_by_object)` for `--dry-run`.

**Tests:** load/validate/override; exposing override without reason downgrades; with reason retained; scope respected. **Gate:** green.

## 5. `technical_pipeline.py` — orchestrator
- `dry_run`: for each in-scope object → describe → classify → report columns/actions (and `recordCount` row estimates where cheap); emit the plan; **no row values**.
- `execute`: per object (skip-and-log on describe/query failure — bucket + verbatim detail to audit log only): build SELECT from non-DROP columns → page → transform rows in flight → write `<ApiName>.csv` to the per-run temp dir. Then `_extract-summary.json` + `_field-handling-applied.csv` (sentinel) → `publish()` (clear-and-republish, sentinel last) → temp removed.
- Abort only on session failure or all-objects-failed.

**Tests (offline, injected transports):** end-to-end with crafted describes/rows for `LoginHistory` (SourceIp→prefix, Status PASS, UserId RAW), `LoginGeo` (fine-geo absent), `FlowInterview` (InterviewLabel absent), `SetupAuditTrail` (Display absent, Action present), `limits` (pure PASS); **no-raw-dump blob check** (no raw IP dotted-quad, no email text, no dropped values anywhere in published CSVs); sentinel present + last; one failing object → skipped + recorded, run completes; all failing → abort, publish path untouched; 0-row object → header-only CSV. **Gate:** green; full v1–v3 suite green.

## 6. `cli.py` — subcommand + help
`get_technical_objects` with the §4 flags; help generated from the catalogue (object list!) and the action set — per C1 the full object list must appear in `--help`. Top-level command list + README (C8).

**Tests:** parser; help runs without auth, names all 40 objects, documents sentinel/read-only/skip-list. **Gate:** green.

## 7. Live (chatbot-driven, C7) — against `tests/live_org.toml`
Dev-edition caveats: some objects will be empty or permission-gated (`IdpEventLog`, `SetupAuditTrail` may be sparse; `AuthSession`/`LoginHistory` will have real rows for the test user).
- `--dry-run` → per-object column plan; exit 0; no values.
- Real run `--limit 50` → published folder with sentinel; leak checks: no dotted-quad IPs, no `@` emails outside hashed columns, hashed cells 64-hex, no `InterviewLabel`/`Display` columns, fine-geo columns absent from `LoginGeo.csv`.
- Re-run → snapshot replaces cleanly.
- Add `tests/test_live_technical.py` (auto-skip pattern); record any not-exercisable paths in `regression-testing.md` (C7: surface, don't hide).

## 8. Docs
README Commands table + section (C8); `regression-testing.md` §4c (C7); `docs-change-log.md` entry.

## 9. Acceptance
- [ ] Offline suite green (v1+v2+v2.1+v3+v4).
- [ ] Live run green against the test org; gaps explicitly recorded.
- [ ] No-raw-dump verified on live output (leak checks above).
- [ ] `--help` lists all 40 objects; no operator knob disables skip-list/classifier.
- [ ] README, regression-testing, change log updated in the same change.
