# SF Clean Room — Implementation Plan (v3: `get_event_logs`)

**Authoritative contract:** [`04-design-v3.md`](../design/04-design-v3.md). Where this and the design disagree, the design wins.
**Grounding:** the proven `ai-framework` tool `salesforce_download_eventlog_files` (REST query + per-record `LogFile` fetch, window/resume/idempotent logic). The one change: classify in memory, never write the raw body.

Ordered; each step names its verification gate.

## 0. Pre-flight
1. Editable install resolves to `src/` (per `regression-testing.md` §1); `pytest -q` green baseline.

## 1. `eventlog_classify.py`
The classifier (pure, the heart). Reuses `hashing.hash_id`.
- `classify_column(name) -> (action, recipe)` implementing [`04-event-log-fields.md`](../requirements/04-event-log-fields.md) §2, first-match-wins: IP→DERIVE(prefix); SF-geo (`COUNTRY_CODE`,`CLIENT_GEO`)→PASS; URL/URI→DERIVE(url); human/device ids (`USER_NAME`,`DELEGATED_USER_NAME`,`DEVICE_ID`)→HASH; content names (`QUERY`,`SEARCH_QUERY`,`*MESSAGE`,`STACK_TRACE`,`ACCESS_ERROR`,`ERROR_DESCRIPTION`,`HTTP_HEADERS`,`CONTEXT_MAP`,`RESOURCE_SAMPLE`,`DATA`,`*_REASON`,`DOWNLOAD_ERROR`, OData `FILTER`/`SELECT`/`SEARCH`/`ORDERBY`/`EXPAND`,`DESCRIPTION`)→DROP; ids/correlation keys (`*_ID`,`*_ID_DERIVED`,`REQUEST_ID`,`ORGANIZATION_ID`,`USER_ID`,`SESSION_KEY`,`LOGIN_KEY`,`BOT_*`,`*_SESSION_ID`,`QUERY_ID`,`CORRELATION_ID`,`SQL_ID`,`QUERY_IDENTIFIER`,`SERVER_REQUEST_ID`,`UI_*_ID`)→RAW; else PASS, with a content-name fallback→DROP.
- `derive_ip_prefix(value)` — IPv4 last octet→`0`; IPv6 last 80 bits→`::`; empty→empty.
- `sanitise_url(value)` — keep scheme+host+path, drop `?...` and `;...`; empty→empty.
- `transform_value(action, value, name)` — RAW/PASS as-is; HASH→`hash_id`; DERIVE→ip-prefix or url-sanitise by which rule matched; DROP→(column omitted upstream).

**Tests:** every action via representative names; SESSION_KEY/LOGIN_KEY→RAW (not HASH); USER_NAME→HASH; CLIENT_IP→DERIVE and prefix correct (v4+v6); URL strip keeps path drops query; HTTP_HEADERS/QUERY/SEARCH_QUERY→DROP; COUNTRY_CODE→PASS; unknown content-shaped name→DROP, unknown benign→PASS. **Gate:** green.

## 2. `eventlog_download.py`
REST mechanics, adapted from the proven tool. Pure-ish (injectable HTTP for tests).
- `rest_get(session, url) -> Response` (Bearer token; reuse `requests`).
- `supports_interval(session) -> bool` (describe EventLogFile; fail-soft False).
- `query_event_log_files(session, start, end, only=None) -> list[record]` (`Id, EventType, LogDate, LogFileLength, ApiVersion`; build window WHERE; filter `--only` client-side or in SOQL).
- `fetch_logfile_text(session, record) -> str` — GET `.../EventLogFile/{id}/LogFile`, return decoded UTF-8 **text in memory**.
- Window helpers (ported verbatim in spirit): `compute_end_date(today_utc)=today-1`; `find_completed_folder(root, end)`; `determine_start_date(root, today)` (max prior end +1, else today-29); `_safe_date(logdate)`.

**Tests (offline, no network):** window/resume math (cold start → 29 days; with prior folders → max+1); idempotent detection of `_to_<yesterday>`; `_safe_date`. HTTP funcs covered via the pipeline test with an injected fetcher. **Gate:** green.

## 3. `eventlog_pipeline.py`
Orchestrator. Injectable `query_fn`/`fetch_fn` for tests.
- `dry_run(session, req, log)` → query the window, list records (count per EventType), and emit the column plan from the union of headers *without* fetching values (dry-run fetches **no** LogFile; the plan is derived from `--only`/known columns or, if a cheap header peek is acceptable, from `LogFileFieldNames`). Simplest: dry-run reports the records to download + the classifier's decision for the columns it can know from `LogFileFieldNames` on the query (add it to the SELECT). No values.
- `execute(session, req, paths, log, query_fn, fetch_fn)`:
  1. window → start/end; idempotent no-op check on the published root.
  2. query records; apply `--only`/scope.
  3. temp run dir; per record: fetch text (memory) → `csv.reader` → classify header → `csv.writer` rows applying `transform_value`, omitting DROP columns → write `<LogDate>_<EventType>_<Id>.csv`. Per-record fetch/parse error → skip-and-log, continue.
  4. write `_extract-summary.json`, `_field-handling-applied.csv` (sentinel).
  5. publish run subfolder into `<path>/event_logs/<alias>/<start>_to_<end>/` (sentinel last; siblings untouched).

**Tests:** full execute with injected query_fn (2 records, 2 EventTypes) + fetch_fn returning crafted CSVs incl. CLIENT_IP, USER_NAME, URI?query, QUERY, USER_ID, SESSION_KEY → assert published CSV: USER_ID/SESSION_KEY raw, USER_NAME hashed (64-hex), CLIENT_IP→prefix col, URI query stripped, QUERY column absent; **no raw IP / no `@username` / no query text anywhere** (no-raw-dump); sentinel present; idempotent second run = no-op; per-record fetch error skipped+logged. **Gate:** green.

## 4. `eventlog_plan.py` (small)
`load_plan(path)` → `EventLogPlan(event_types: list, overrides: dict[col,action])`; `emit_plan(columns_seen)` for `--dry-run`. `resolve(col)` = override if present (validated against the action set) else `classify_column`. Special-category-style note: an override that *exposes* a DROP content column needs a justification string in `[reasons]`, else it stays DROP (reuse the get_records rule shape). **Tests:** load/override/validate/justification-downgrade. **Gate:** green.

## 5. `publish.py`
Reuse `preceding_artefacts`. Add `publish_subfolder(temp_run_dir, dest_subfolder, sentinel, preceding_artefacts)` that moves a completed run dir into place **without clearing siblings** (incremental model) — or parameterise `publish` with `clear=False`. **Tests:** sibling subfolders untouched; sentinel last; missing sentinel aborts. **Gate:** v1/v2 publish tests stay green.

## 6. `cli.py`
`get_event_logs` subcommand: `--org-alias`, `--path`, `--only`, `--plan`, `--dry-run`. Help (from the action set + rules): output layout, sentinel, incremental/never-today model, classification summary, read-only. Top-level help lists it. **Tests:** parser flags; help runs without auth and documents the sentinel + actions + "anonymised in flight".

## 7. Live (chatbot-driven, C7)
Against `tests/live_org.toml` (`example-dev-edition`). Note dev orgs may have limited EventLogFile access/retention — **auto-skip if the EventLogFile query returns no access/zero records**.
- `--dry-run` → lists available EventTypes + the column plan; exit 0.
- real run → a `<start>_to_<end>/` subfolder with anonymised CSVs + sentinel; **leak checks**: no raw IPv4 dotted-quad in any CSV; any `*_PREFIX` column ends `.0`; no `@`-bearing username column; hash columns 64-hex; no DROP column header present.
- second run same day → idempotent no-op.

## 8. Docs (C7)
- `regression-testing.md`: new §for get_event_logs (dry-run, real, leak checks, idempotent; auto-skip when no Event Monitoring).
- `docs-change-log.md`: entry.
- README: `get_event_logs` section.

## 9. Acceptance
- [ ] Offline suite green (v1+v2+v2.1+v3).
- [ ] Live run green or cleanly skipped (no Event Monitoring) — reported either way.
- [ ] No-raw-dump verified (no raw IP/username/query text in any published CSV).
- [ ] Help documents the contract; no operator knob disables the classifier.
- [ ] `regression-testing.md` + change log updated.
