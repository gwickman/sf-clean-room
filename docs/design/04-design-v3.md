# SF Clean Room — Design (v3: `get_event_logs`)

**Status:** Draft → being implemented.
**Scope:** The third tool in the family — safe export of Salesforce **EventLogFile** data via the `get_event_logs` subcommand. v1 (`get_metadata`) and v2 (`get_records`) are unchanged.
**Principles:** [`00-design-principles.md`](../00-design-principles.md). **Goals/requirements:** [`04-event-log-download.md`](../requirements/04-event-log-download.md). **Schema:** [`salesforce-event-log-reference.md`](../reference/salesforce-event-log-reference.md). **Field classification:** [`04-event-log-fields.md`](../requirements/04-event-log-fields.md). **Decision history:** [`docs-change-log.md`](../docs-change-log.md). **Companion plan:** [`04-plan-v3.md`](../plan/04-plan-v3.md).

This document is the authoritative v3 contract.

---

## 1. Purpose

`get_event_logs` downloads Salesforce EventLogFile CSVs for an org and publishes them **anonymised** to a local folder. Every column is classified; IPs are derived to a network prefix, URLs are stripped of query strings, usernames are hashed, the rare free-text column is dropped — before any value is written. Salesforce IDs (incl. the pre-hashed `SESSION_KEY`/`LOGIN_KEY`) are kept RAW so event rows join to each other and to the `get_metadata`/`get_records` extracts. The agent reads anonymised CSVs, never the raw download.

The download mechanism is the one proven in `ai-framework`'s `salesforce_download_eventlog_files`: REST query of `EventLogFile`, then a per-record `LogFile` fetch. The **one change** is that the raw `LogFile` is held in memory and classified in flight; only the anonymised CSV reaches disk (invariant A2).

## 2. Safety model

- **Read-only.** Only REST `GET` (`/query` and `/sobjects/EventLogFile/{id}/LogFile`). No write path. (A4)
- **No raw dump.** The raw `LogFile` body lives only in process memory; only the post-classification CSV is written. There is no code path that writes a raw event-log row to disk. (A2)
- **Abstraction.** The agent reads the published folder; it never holds a Salesforce session or the raw download. (A1)
- **Classifier = the safety boundary, source-controlled, rule-based.** Every column is resolved by the rules in [`04-event-log-fields.md`](../requirements/04-event-log-fields.md) §2; the rules cover every column of every EventType (drift-safe). A reviewed plan may override, with special-category-style justification for the risky direction.
- **Pseudonymous output.** Output is keyed by Salesforce IDs, never names/emails.

## 3. Classification actions

`RAW` (Salesforce IDs + opaque/pre-hashed correlation keys), `HASH` (`USER_NAME`, `DELEGATED_USER_NAME`, `DEVICE_ID` — frozen, unsalted `sha256`), `DERIVE` (IP → network prefix; URL → host+path, query stripped), `PASS` (metrics, enums, names, Salesforce-provided geo), `DROP` (free-text/content/secrets). Full per-column mapping: [`04-event-log-fields.md`](../requirements/04-event-log-fields.md). Reuses `hashing.hash_id`.

## 4. CLI surface

```
sf-clean-room get_event_logs --org-alias <alias> --path <dir>
    [--only <EventType> [<EventType> ...]]
    [--plan <file>]
    [--dry-run]
```

| Flag | Required | Meaning |
|---|---|---|
| `--org-alias` | yes | Authenticated `sf`/`sfdx` alias. |
| `--path` | yes | Base directory (must exist). Output lands under `<path>/event_logs/<alias>/`. |
| `--only` | no | EventTypes to include (default: all available in the window). |
| `--plan` | no | Classification plan (TOML): `[scope].event_types` and `[overrides].<COLUMN> = <action>`. With `--dry-run` it is written; without, consumed. |
| `--dry-run` | no | Query the window and report what would download + the column classification plan. No `LogFile` fetch, no values, no publish. |

These are narrowing/specification inputs (C4). No flag disables the classifier or the read-only/no-raw-dump guarantees. No `--where` (the date window is computed, §6).

## 5. Pipeline

```
session → query EventLogFile (window) → per record: fetch LogFile (memory)
        → parse CSV header → classify columns → transform rows in flight (to temp)
        → publish run-folder (sentinel last)
```

1. **Session** via `get_session` (token + instance_url).
2. **Window** (§6) → `start_date`, `end_date`.
3. **Query** `SELECT Id, EventType, LogDate, LogFileLength, ApiVersion FROM EventLogFile WHERE [Interval='Daily' AND] LogDate >= start AND LogDate < end+1` (REST). `Interval='Daily'` only if the org's describe shows the field (some orgs lack it).
4. **Per record** (filtered to `--only`/scope if set): `GET /sobjects/EventLogFile/{id}/LogFile` into memory. Parse the CSV; classify each header column once; stream rows applying the per-column action; write `<LogDate>_<EventType>_<Id>.csv` into the per-run temp folder. The raw body is never written.
5. **Audit + sentinel.** Write `_field-handling-applied.csv` (column, action, recipe, EventTypes seen) and `_extract-summary.json` (per-type row/column counts, dropped/hashed/derived columns) into the temp run folder.
6. **Publish** the run folder into `<path>/event_logs/<alias>/<start>_to_<end>/`, sentinel `_field-handling-applied.csv` moved last.

## 6. Output model — incremental, not clear-and-republish

Event logs **accumulate**: Salesforce retains only ~30 days (1 day without the add-on), so the value is building a longer local history. Unlike `get_metadata`/`get_records` (which clear and republish `--path`), `get_event_logs` is incremental, following the proven tool:

- Output root: `<path>/event_logs/<alias>/`. Each run publishes a **new** dated subfolder `<start>_to_<end>/`; prior subfolders are never cleared.
- **Never "today".** `end_date = yesterday (UTC)` — today's logs are incomplete.
- **Resume.** `start_date = max(existing subfolder end) + 1 day`, or `yesterday - 29 days` on a cold start.
- **Idempotent.** If a `<...>_to_<yesterday>` subfolder already exists, the run is a no-op (returns the existing folder, downloaded=0).
- The temp-then-publish discipline and the sentinel apply **per run subfolder**: a run builds its subfolder in temp and moves it into place with the sentinel last; a failed run leaves prior subfolders untouched (fail-closed).

## 7. Output contract

A consumer reading a `<start>_to_<end>/` subfolder that contains `_field-handling-applied.csv` (the sentinel) may assume: the run completed; one `<LogDate>_<EventType>_<Id>.csv` per downloaded record; every column accounted for in the audit; no raw IP (only `*_PREFIX` and any Salesforce `COUNTRY_CODE`), no URL query strings, hashed usernames, no dropped column present. No sentinel → do not read that subfolder.

## 8. Failure modes

| Failure | Behaviour |
|---|---|
| Session / Data-API unavailable | Abort before any temp/publish. |
| `EventLogFile` query fails | Abort (fail-closed). |
| A single record's `LogFile` fetch fails | **Skip that record, record it, continue** (per-record tolerance, like v2.1's per-type tolerance — one bad record must not lose the run). |
| A record's CSV is unparseable | Skip-and-log; continue. |
| Idempotent no-op (yesterday folder exists) | Exit 0, downloaded=0. |
| No records in the window | Publish an empty run folder with a header-only audit sentinel; exit 0. |

Exit code: 0 on completed publish (including the no-op and empty cases), non-zero on abort.

## 9. Deliberate simplifications (v3-initial)

- **IP derivation is prefix-only.** `CLIENT_IP`→`CLIENT_IP_PREFIX` (IPv4 last octet zeroed; IPv6 last 80 bits zeroed). Country-from-IP needs a geo-IP dataset; deferred (would need a local dataset to honour "all local"). Where Salesforce already supplies `COUNTRY_CODE`/`CLIENT_GEO`, those are kept (PASS), so country signal is not lost on the events that matter most (Login).
- **Plan overrides are column-global.** Event-log column names are consistent across types, so `[overrides].<COLUMN> = <action>` applies wherever that column appears. Simpler than per-type; sufficient.
- **`--dry-run` cannot detect per-record fetch issues** (no fetch happens); it reports the query result and the classification plan only.
- **No raw-`QUERY` salvage yet.** Raw `QUERY`/`SEARCH_QUERY`/error text DROP by default; the `UniqueQuery` `SQL_ID` fingerprint already covers "which queries ran". A sanitised-SOQL form is future work (ideation §7).

## 10. Reuse of family infrastructure

`session.py` (token), `audit.py` (per-run log + stderr tee), `hashing.py` (`hash_id`), `publish.py` (sentinel-last + `preceding_artefacts`), the `config.py`/temp-root and per-run temp discipline, and the `get_records` plan/recommend→review→extract model. The classifier is a new module; the REST download is a new module adapted from the proven `ai-framework` tool.

---

## Appendix A — Implementation plan

Detailed in [`04-plan-v3.md`](../plan/04-plan-v3.md). High-level:

1. `eventlog_classify.py` — column classifier (rules), IP-prefix derive, URL sanitise; reuses `hashing.hash_id`.
2. `eventlog_download.py` — REST: describe-Interval check, EventLogFile query, per-record LogFile fetch **into memory**; window/resume/idempotent date logic (from the proven tool).
3. `eventlog_pipeline.py` — orchestrator + `--dry-run`; per-record parse→classify→transform→write to temp; audit/summary; incremental publish.
4. `eventlog_plan.py` (or extend `plan.py`) — `[scope].event_types`, `[overrides].<COLUMN>`.
5. `publish.py` — reuse `preceding_artefacts`; add an incremental-publish helper (move a run subfolder without clearing siblings).
6. `cli.py` — `get_event_logs` subcommand + help (generated from the action set / rules).
7. Tests (C7): offline (classifier rules, IP/URL derive, in-flight transform, CSV round-trip, window/resume/idempotent logic, no-raw-dump) + live against the test org; update `regression-testing.md`.
8. Docs: `docs-change-log.md`; README note.
