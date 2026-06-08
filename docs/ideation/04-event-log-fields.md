# 04 — Event Log Field Classification (overlay on the schema reference)

**Schema source (authoritative):** [`salesforce-event-log-reference.md`](salesforce-event-log-reference.md) — a field-by-field reference for 65 EventLogFile EventTypes, built from observed CSV headers. That doc is the *schema*; **this doc is the classification overlay** — for each column (or column pattern) it gives the handling action and why. It does not repeat the per-type tables.
**Companion:** [`04-event-log-download.md`](04-event-log-download.md) (the requirements).

---

## 1. Actions (same family as `get_records`)

| Action | For event logs | Preserves |
|---|---|---|
| `RAW` | Salesforce IDs **and** opaque correlation keys (incl. Salesforce's already-hashed `SESSION_KEY`/`LOGIN_KEY`) | joins to the metadata/records extracts and across event rows |
| `HASH` | direct human / persistent-device identifiers Salesforce did *not* already pseudonymise (`USER_NAME`, `DELEGATED_USER_NAME`, `DEVICE_ID`) — `sha256(strip(v))`, frozen recipe | de-identified but joinable |
| `DERIVE` | raw IP → `*_COUNTRY` + `*_PREFIX` (/24); URL/URI → host+path, query string stripped | location/network and "what was accessed" without the identifying detail |
| `PASS` | everything analytical and non-identifying, **including Salesforce's own derived geo** (`COUNTRY_CODE`, `CLIENT_GEO`) | full value (the bulk of every file) |
| `DROP` | free-text / content that can embed PII, record data, or secrets, and that derivation can't salvage | last resort |

Hash recipe is frozen and never salted (so a hashed `USER_NAME` joins consistently). There is **no** re-hashing of `SESSION_KEY`/`LOGIN_KEY` — the schema reference confirms Salesforce already emits these as hashes, so re-hashing would only break the cross-row join for zero privacy gain.

## 2. Classification rules (first match wins; cover every column)

1. **IP addresses → DERIVE.** `CLIENT_IP`, `SOURCE_IP`, `FORWARDED_FOR_IP`, `REMOTE_ADDRESS`, `IP_ADDRESS`. Emit `<name>_COUNTRY` + `<name>_PREFIX` (last octet zeroed); drop the exact address. *Not* hashed (IPv4 is brute-forceable — the phone-number lesson).
2. **Salesforce-provided geo → PASS.** `COUNTRY_CODE`, `CLIENT_GEO` are already coarse (country); keep as-is. (They are the safe derivation, already done by Salesforce.)
3. **URL / URI fields → DERIVE (sanitise).** Any column ending `URI`/`URL` or named `*_REFERER`/`REFERRER`/`LOGIN_URL`/`NEXT_LINK`/`BLOCKED_URI`/`MALFORMED_URL`/`REQUEST_URI`/`REQUEST_PATH`/`API_RESOURCE`. Keep host+path (and embedded Salesforce IDs); strip the query string. (Security events keep the threat URL's host+path.)
4. **Direct human / persistent-device identifiers → HASH.** `USER_NAME`, `DELEGATED_USER_NAME` (login usernames, email-shaped), `DEVICE_ID` (persistent device fingerprint).
5. **Free-text / content / secrets → DROP.** See §4. Conservative default; a reviewed plan may keep a sanitised form with justification.
6. **Salesforce IDs and opaque correlation keys → RAW.** `*_ID`, `*_ID_DERIVED`, `REQUEST_ID`, `ORGANIZATION_ID`, `USER_ID`, and the opaque/pre-hashed correlation keys `SESSION_KEY`, `LOGIN_KEY`, `BOT_ID`, `BOT_SESSION_ID`, `PLANNER_ID`, `DEVICE_SESSION_ID`, `WAVE_SESSION_ID`, `SESSION_ID`, `QUERY_ID`, `CORRELATION_ID`, `SQL_ID`, `QUERY_IDENTIFIER`, `SERVER_REQUEST_ID`, `UI_ROOT_ACTIVITY_ID`, `UI_EVENT_ID`.
7. **Everything else → PASS** (metrics, timings, enums, counts, sizes, config/code names, device/browser/OS model, key prefixes). A no-match column whose name suggests content (`QUERY`, `SEARCH`, `MESSAGE`, `TEXT`, `HEADERS`, `DESCRIPTION`, `STACK`, `SAMPLE`, `FILTER`, `DATA`) defaults to DROP; otherwise PASS.

## 3. Column inventory by action

Representative — the rules in §2 cover any column not named. (See the schema reference for which type carries which column.)

**RAW — Salesforce IDs + opaque/pre-hashed correlation keys**
`REQUEST_ID`, `ORGANIZATION_ID`, `USER_ID`, `USER_ID_DERIVED`, `URI_ID_DERIVED`, `SESSION_KEY`, `LOGIN_KEY`, `BOT_ID`, `BOT_SESSION_ID`, `PLANNER_ID`, `DEVICE_SESSION_ID`, `WAVE_SESSION_ID`, `SESSION_ID`, `QUERY_ID`, `CORRELATION_ID`, `SQL_ID`, `QUERY_IDENTIFIER`, `SERVER_REQUEST_ID`, `CONNECTED_APP_ID`, `CLIENT_ID`, and every record/asset id: `REPORT_ID(_DERIVED)`, `MASTER_REPORT_ID`, `DASHBOARD_ID(_DERIVED)`, `DASHBOARD_COMPONENT_ID`, `JOB_ID`, `BATCH_ID`, `DOCUMENT_ID(_DERIVED)`, `VERSION_ID(_DERIVED)`, `DELIVERY_ID`, `RELATED_ENTITY_ID`, `ENTITY_ID`, `RECORD_ID`, `CLICKED_RECORD_ID`, `FIRST_ENTITY_ID`, `PARENT_ID`, `ATTACHMENT_ID`, `SHARED_WITH_ENTITY_ID`, `GROUP_ID`, `MEMBER_ID`, `FEATURE_ID`, `KEY_ID(_DERIVED)`, `SITE_ID`, `SANDBOX_ID`, `PENDING/CURRENT_SANDBOX_ORG_ID`, `TRIGGER_ID`, `FLOW_VERSION_ID`, `CASE_ID`, `ACTUAL_USER_ID`, `ACTUAL_LOGGED_IN_USER_ID`, `VIEWING_USER_ID`, `DELEGATED_USER_ID(_DERIVED)`, `EFFECTIVE_ACCOUNT_ID`, `WEBSTORE_ID`, `ASSET_ID`, `DATASET_IDS`, `ARTICLE_ID`/`ARTICLE_VERSION_ID`, `PAGE_ENTITY_ID`, `PREVPAGE_ENTITY_ID`, `SAVED_VIEW_ID`, `PAGE_ID`, `TAB_ID`, `AUTHENTICATION_SERVICE_ID`, `AGENT_ACTION`, `PROMPT_TEMPLATE`, `LOG_GROUP_ID`, `UNIQUE_ID`.
*Rationale:* opaque outside Salesforce; the join keys to `get_metadata`/`get_records` and across events (`REQUEST_ID`, `LOGIN_KEY`). `SESSION_KEY`/`LOGIN_KEY` are Salesforce-hashed already.

**HASH — direct identifiers Salesforce left in the clear**
`USER_NAME`, `DELEGATED_USER_NAME`, `DEVICE_ID`.
*Rationale:* `USER_NAME` is the login username (email-shaped) — redundant with `USER_ID_DERIVED` for joining, so DROP is also acceptable; HASH keeps it joinable to other systems while de-identified. `DEVICE_ID` persists across sessions (a tracking fingerprint), unlike the ephemeral `DEVICE_SESSION_ID`.

**DERIVE — IP → country + /24 prefix**
`CLIENT_IP`, `SOURCE_IP`, `FORWARDED_FOR_IP`, `REMOTE_ADDRESS`, `IP_ADDRESS`.

**DERIVE — URL/URI → host+path, query stripped**
`URI`, `URL`, `PAGE_URL`, `PREVPAGE_URL`, `REFERRER_URI`, `REFERRER`, `HTTP_REFERER`, `LOGIN_URL`, `REQUEST_URI`, `REQUEST_PATH`, `API_RESOURCE`, `NEXT_LINK`, `BLOCKED_URI`, `BLOCKED_URI_DOMAIN`, `MALFORMED_URL`.

**PASS — analytical, non-identifying (the bulk)**
- Salesforce geo: `COUNTRY_CODE`, `CLIENT_GEO`.
- Time: `TIMESTAMP`, `TIMESTAMP_DERIVED`, all RUM phase timings, `WAVE_TIMESTAMP`, `UI_EVENT_TIMESTAMP`, `ERROR_TIMESTAMP`.
- Metrics/sizes/counts: `RUN_TIME`, `CPU_TIME`, `DB_TOTAL_TIME`, `DB_BLOCKS`, `DB_CPU_TIME`, `EXEC_TIME`, `CALLOUT_TIME`, `DURATION`, `EPT`, `EFFECTIVE_PAGE_TIME`, `ROW_COUNT`, `ROWS_PROCESSED`, `RECORDS_PROCESSED`, `NUMBER_*`, `NUM_*`, `*_SIZE`, `*_BYTES`, `SAMPLE_FACTOR`, `RANK`, `THROUGHPUT`, etc.
- Enums/flags: `EVENT_TYPE`, `USER_TYPE`, `REQUEST_STATUS`, `API_TYPE`, `API_VERSION`, `API_FAMILY`, `METHOD`, `METHOD_NAME`, `HTTP_METHOD`, `STATUS_CODE`, `STATUS`, `SUCCESS`, `IS_*`, `RENDERING_TYPE`, `DISPLAY_TYPE`, `LOGIN_TYPE/STATUS/SUB_TYPE`, `SESSION_TYPE/LEVEL`, `OPERATION(_TYPE)`, `ACTION(_TYPE)`, `SHARING_*`, `TRANSACTION_TYPE`, `DML_TYPE`, `KEY_PREFIX`, `PREFIXES_SEARCHED`, `TRIGGER_TYPE`, `QUIDDITY`, `PROCESS_TYPE`, `GROUP_TYPE`, `PERMISSION_TYPE`, `REQUEST_TYPE`, `CONNECTION_TYPE`, `AUTHENTICATION_METHOD_REFERENCE`, `AUTHENTICATION_CONTEXT_CLASS_REFERENCE`, `TLS_PROTOCOL`, `CIPHER_SUITE`, `LANGUAGE`, `ARTICLE_STATUS`, `QUERY_TYPE`, `REQUESTED_ACCESS_LEVEL`, `EXCEPTION_TYPE`, `EXCEPTION_CATEGORY`, `FAILURE_TYPE`, `LARGE_LANGUAGE_MODEL`.
- Config / code / client names (not personal): `CLIENT_NAME`, `CONNECTED_APP_NAME`, `ENTITY_NAME`, `TRIGGER_NAME`, `APEX_ENTITY_NAME`, `ENTRY_POINT`, `CLASS_NAME`, `PACKAGE_NAME`, `NAMED_CREDENTIAL_NAME`, `*_NAMESPACE`, `ACTION_NAME`, `ACTION_MESSAGE`, `APP_NAME`, `PAGE_NAME`, `COMPONENT_NAME`, `PAGE_FLEXI_PAGE_NAME_OR_ID`, `SERVICE_NAME`, `REPORT_DESCRIPTION`, `CLIENT_INFO`, `USER_AGENT`, `BROWSER_*`, `PLATFORM(_TYPE)`, `OS_*`, `DEVICE_MODEL`, `DEVICE_PLATFORM`, `RESOLUTION_TYPE`, `SDK_*`, UI element descriptors (`TARGET/PARENT/GRANDPARENT_UI_ELEMENT`, `PAGE_CONTEXT`, `PAGE_ENTITY_TYPE`).

**DROP — free-text content / secrets (the rare case)** — see §4.

## 4. The DROP set (and the salvage options)

These columns can carry user-entered text, record values, or secrets; derivation can't reliably clean them, so they DROP by default. Each notes whether a *sanitised* form is worth keeping (a plan override, mirroring the special-category justification rule in `get_records`).

| Column(s) | Event types | Why DROP | Salvage option |
|---|---|---|---|
| `QUERY` | API, ApexRestApi, RestApi, VisualforceRequest, Sites | raw SOQL / URL query text — embeds filter **values** (PII) | the **UniqueQuery** event already gives a hashed `SQL_ID` fingerprint + `QUERY_TYPE` — use that for "which queries ran" instead of raw text |
| `SEARCH_QUERY` | Search | verbatim global-search text — users search names/emails | keep `NUM_RESULTS`, `PREFIXES_SEARCHED` (PASS); the text itself stays dropped |
| `EXCEPTION_MESSAGE`, `ERROR_MESSAGE`, `MESSAGE`, `ERROR_DESCRIPTION`, `STACK_TRACE`, `ACCESS_ERROR`, `DOWNLOAD_ERROR`, `CANCELLED_REASON`, `FAILURE_REASON` | Apex*, Bulk*, Composite*, OData, Wave*, InsufficientAccess | error/stack text can echo record field values | keep `EXCEPTION_TYPE`/`EXCEPTION_CATEGORY`/`STATUS_CODE` (PASS) — the shape without the payload |
| `HTTP_HEADERS` | Sites | truncated request headers — can carry `Authorization`/`Cookie` tokens | none safe; DROP |
| `CONTEXT_MAP` | OneCommerceUsage | JSON blob of arbitrary contextual key/values | DROP (could keep allow-listed keys via plan) |
| `RESOURCE_SAMPLE` | CSPViolation | ~40 bytes of offending page content | DROP |
| `DATA` | TimeBasedWorkflow | workflow context blob | DROP |
| `FILTER`, `SELECT`, `SEARCH`, `ORDERBY`, `EXPAND` | ExternalODataCallout | OData query fragments — `FILTER` carries literal values | keep field/structure, strip literals (future sanitiser); default DROP |
| `DESCRIPTION` | PermissionUpdate | human-readable change summary | usually safe (config text); PASS-with-review is defensible — start DROP |

Everything *not* in this table is RAW/HASH/DERIVE/PASS — i.e. almost the entire schema survives.

## 5. Non-obvious classification notes

- **`SESSION_KEY` / `LOGIN_KEY` → RAW, not HASH.** Salesforce already hashes them (schema reference §2). They are the backbone of session/login correlation; keep verbatim.
- **`USER_NAME` → HASH, not PASS.** It is the only routinely-present *human* identifier (login/email). `USER_ID(_DERIVED)` already carries the join, so some projects will prefer DROP; HASH is the keep-it-joinable default.
- **IP is salvaged, not dropped or hashed.** Where Salesforce already gives `COUNTRY_CODE`/`CLIENT_GEO`, keep it (PASS) and DERIVE the raw IP columns alongside.
- **Security events stay useful.** `BlockedRedirections`, `CSPViolation`, `CorsViolation`, `InsufficientAccess` keep their structural fields (directive, origin host, access level, record id); only the free-text/sample payloads drop.
- **`DatabaseSave` is sampled** — keep `SAMPLE_FACTOR` (PASS) so the consumer can scale `NUM_ROWS`.
- **Cross-event joins survive classification:** `REQUEST_ID`, `LOGIN_KEY`, `SESSION_KEY`, `QUERY_ID`, `JOB_ID`, `WAVE_SESSION_ID`, `DEVICE_SESSION_ID` are all RAW — the join graph in the schema reference §4 is fully preserved.
