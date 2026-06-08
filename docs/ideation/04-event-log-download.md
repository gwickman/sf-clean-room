# 04 — Event Log Download: Goals and Requirements

**Status:** Ideation. Input to a future design. Scope here is **requirements and useful-information extraction** — *not* the technical mechanics of downloading EventLogFile data (deferred).
**Governed by:** [`00-design-principles.md`](00-design-principles.md) — read it first.
**Companions:** the schema reference [`salesforce-event-log-reference.md`](salesforce-event-log-reference.md) (65 EventTypes, observed CSV headers); the classification overlay [`04-event-log-fields.md`](04-event-log-fields.md); the record-data model [`02-data-download.md`](02-data-download.md) (the classifier/plan pattern this reuses).

---

## 1. The problem

Salesforce **EventLogFile** data is the richest source of operational, security, and adoption insight in an org: who logged in from where, what API clients did, which reports were exported, which pages and features were used, what ran slowly. An agent doing a security review, an adoption analysis, or a performance investigation wants it. The naive move — hand the agent the raw event-log CSVs — exposes personal data (IP addresses, occasionally search terms or error payloads in URIs/fields) and would be a bulk-personal-data dump under any reasonable acceptable-use policy.

But event logs differ from record data in a way that changes the whole calculus: **they are pseudonymous by construction.** Rows are keyed by Salesforce IDs (`USER_ID`, `ORGANIZATION_ID`, `REPORT_ID`, …), not by names or emails; Salesforce even ships `SESSION_KEY`/`LOGIN_KEY` pre-hashed and provides derived geo (`COUNTRY_CODE`, `CLIENT_GEO`). Direct PII is the exception, and where it appears it is **salvageable**:

- `CLIENT_IP` / `SOURCE_IP` / `FORWARDED_FOR_IP` — personal data, but its value (geography, network) survives derivation; and where Salesforce already gives `COUNTRY_CODE`, that is kept as-is.
- `URI` and other URL fields — can carry search terms or PII in **query strings**; the host+path is the useful part.
- A handful of **human-identifier** columns — `USER_NAME` / `DELEGATED_USER_NAME` (login/email-shaped), `DEVICE_ID` (persistent device) — appear in a few types; hashed, they de-identify while staying joinable.
- Free-text / content fields (`QUERY`, `SEARCH_QUERY`, error/stack messages, `HTTP_HEADERS`, OData `FILTER`, `CONTEXT_MAP`) — the routine drop, and even some of these have a salvage path (§5).

So the objective is unusually favourable: **deliver almost all of the event-log signal, anonymised, with very little dropped.** The job is to maximise retained, useful information while honouring the privacy rules — drop a column only when nothing can be salvaged; otherwise hash it, derive a safe form of it, or keep it.

## 2. Who the actors are

Same as the rest of the family ([`02-data-download.md`](02-data-download.md) §-actors): a trusted, privacy-aware **agent** operates the tool and is also the consumer; a **human maintainer** changes source-controlled safety surfaces. The tool **abstracts the agent from Salesforce** — the agent reads anonymised event-log files, never the raw download (principle A1).

## 3. Goals

1. **Maximise retained signal.** The default outcome keeps as much analytically useful information as the privacy rules allow. Dropping is the exception, not the reflex — "only drop a column if we absolutely have to."
2. **Salvage, don't discard.** Where a field carries both signal and risk, transform rather than drop: hash correlation keys, derive geography/network from IPs, keep URI paths while stripping query strings. (Principle B4 — useful despite anonymisation.)
3. **Pseudonymous, joinable output.** Salesforce IDs are kept RAW so event rows join to each other, to a user's activity over time, and to the structure/data extracts (`get_metadata` / `get_records`) — without ever resolving to a name or email. The agent analyses *what id 005… did*, not *what Jane did*.
4. **No raw PII reaches the agent — by construction.** No code path writes a raw, unclassified event-log row to a file the agent reads; classification is applied before any value is written (principle A2). Read-only throughout (A4).
5. **Same collaboration model as records.** A rule-based classifier recommends an action per column; a reviewed, persistable plan may override; runs are repeatable and headless-safe (the recommend → review → extract loop of `02-data-download.md`).
6. **Regression-tested as part of the change (C7).** Ships with offline tests for the classifier rules and the IP/URI derivations, plus a live check against the test org, and updates `regression-testing.md`.

## 4. Requirements

### 4.1 Classification is the safety boundary, rule-based and source-controlled
Every event-log column is resolved to one of `RAW / HASH / DERIVE / PASS / DROP` by the rules in [`04-event-log-fields.md`](04-event-log-fields.md) §2. The rules are source-controlled and cover **every column of every event type** — the 65 EventTypes catalogued in the schema reference, any Salesforce documents beyond them, and any column not individually classified — so a new event type or a new column is resolved by the conservative default, never silently emitted raw (drift-safe, as in `get_metadata` v2.1 and `get_records`).

### 4.2 The specific handling (the "keep useful info" requirements)
- **Salesforce IDs and opaque correlation keys → RAW.** `USER_ID`, `ORGANIZATION_ID`, `REQUEST_ID`, every `*_ID`/`*_ID_DERIVED`, **and `SESSION_KEY`/`LOGIN_KEY` (which Salesforce already emits hashed)** plus `BOT_*`, `DEVICE_SESSION_ID`, `QUERY_ID`, `WAVE_SESSION_ID`, `SQL_ID`. Opaque outside Salesforce; the join keys. *Required* — dropping or hashing these destroys the analytical value (attribution and cross-event correlation) for no privacy gain. Re-hashing the already-hashed session/login keys is explicitly *not* done — it would only break the join.
- **IP addresses → DERIVE, not drop, not hash.** `CLIENT_IP`/`SOURCE_IP`/`FORWARDED_FOR_IP`/`REMOTE_ADDRESS`/`IP_ADDRESS` → a derived country and `/24` prefix; exact address dropped. Where Salesforce already supplies `COUNTRY_CODE`/`CLIENT_GEO`, keep it (PASS). Hashing IPs is rejected: IPv4 is brute-forceable (the phone-number lesson from `get_records`).
- **Human / persistent-device identifiers → HASH** (frozen, unsalted). `USER_NAME`, `DELEGATED_USER_NAME` (login/email), `DEVICE_ID`. These are the only routinely-present direct identifiers; hashing de-identifies while keeping them joinable. (`USER_ID` already carries the join, so DROP is an acceptable alternative for `USER_NAME` per project taste.)
- **URL / URI fields → DERIVE (sanitise).** Keep host+path (and embedded Salesforce IDs — opaque); strip the query string. Applies to `URI`, `URL`, `PAGE_URL`, `*REFERER*`, `LOGIN_URL`, `BLOCKED_URI`, `MALFORMED_URL`, etc. Preserves "what was accessed" (and the threat URL on security events) without the parameter payload.
- **Performance, enums, counts, names, Salesforce geo → PASS.** Timestamps, `RUN_TIME`/`CPU_TIME`/`DB_*`/RUM timings, `METHOD`/`API_TYPE`/`STATUS`/`RENDERING_TYPE`, sizes/counts, `USER_AGENT`/`BROWSER_*`/`OS_*`/device model, config/code names (`ENTITY_NAME`, `CLASS_NAME`, `REPORT_DESCRIPTION`, …), key prefixes, and `COUNTRY_CODE`/`CLIENT_GEO`. The bulk of every log; non-identifying; kept whole.
- **Free-text / content / secrets → DROP, but only when unsalvageable.** `QUERY`, `SEARCH_QUERY`, error/stack messages (`EXCEPTION_MESSAGE`, `STACK_TRACE`, `ACCESS_ERROR`, …), `HTTP_HEADERS` (can carry auth tokens), `CONTEXT_MAP`, `RESOURCE_SAMPLE`, OData `FILTER`/`SELECT`/`SEARCH`. The rare case. A reviewed plan may keep a sanitised form with a recorded justification (the special-category-style override from `get_records`).

### 4.3 Output is anonymised, self-describing, and joinable
- One anonymised file per event type (e.g. `<EventType>.csv`/`.tsv`), columns transformed per the agreed plan.
- An audit/sentinel artefact recording, per column, the resolved action and recipe (the completion sentinel, published last — the family's discipline). Verbatim provenance/detail in the audit log, not the published folder (v1 §9).
- Derived columns are clearly named (`CLIENT_IP_COUNTRY`, `CLIENT_IP_PREFIX`) so a consumer knows it is reading a derivation, not a raw value.

### 4.4 Read-only, no raw dump, abstraction (unchanged family floor)
The tool issues only read queries; the raw event-log content stays in process memory; only classified output is written; the agent never holds the raw download. These are mechanical guarantees, not judgment calls (A2, A4, A1).

### 4.5 Collaboration and headless reuse
Reuse the `get_records` model: `--dry-run` emits an annotated classification plan (every column with its recommended action and reason); the operator may override (e.g. keep a sanitised `QUERY` for a security investigation, with justification); a real run consumes the plan; a persisted plan runs unattended and is drift-safe. Object/type scope is explicit (which event types to pull). No operator-tunable knob disables the classifier.

## 5. Why so little is dropped (the case, stated plainly)

A record-data extract drops a lot because records *are* the PII (names, emails, addresses sit in columns). An event-log extract drops almost nothing because the PII was largely never in the columns — Salesforce already replaced people with IDs, pre-hashed the session/login keys, and even pre-derived geo (`COUNTRY_CODE`). The genuinely personal raw values are few: the IP (salvaged by derivation), URL query strings (stripped), one or two username columns (hashed), and a small set of free-text/content fields (dropped). Everything else — timing, volumes, API/method/status, report/page/class ids, session and request correlation — is either non-identifying or pseudonymous. That is why "give the chatbot the most information without violating the policy" is achievable here to a degree it is not for record data: the schema reference catalogues 65 EventTypes and only a handful of columns across all of them ever need dropping.

## 6. Out of scope (here)

- **The technical download mechanism.** How EventLogFile is queried, fetched, paged, hourly-vs-daily, and stored is deferred to the design. (Salesforce exposes it via the EventLogFile object: `Id, EventType, LogDate, LogFileLength, LogFile, LogFileFieldNames, LogFileFieldTypes`. Noted only so the requirements are concrete.)
- **Real-Time Event Monitoring streaming events** (the `*Event` platform-event objects, e.g. `LoginEventStream`, `ReportEvent`, transaction-security events). Different delivery model and schema; a separate question.
- **Re-identification modelling beyond the field level.** The combination of pseudonymous columns (time + prefix + user id + path) carries some re-identification risk in principle; under the family model the operator is trusted and the output is pseudonymous-for-in-session-analysis. If a stricter bar is needed (e.g. k-anonymity on derived geo), that is a future iteration.
- **Relaxing any zero-judgment floor** — read-only, no-raw-dump, deny-equivalent secret handling stay absolute.

## 7. Open questions

1. **Event-type scope default.** 65 EventTypes are catalogued (Salesforce documents a few more). Default to a curated high-value set (auth, API, report/export, URI, Apex) and let the plan widen, or attempt all available? Bulk/storage cost argues for an explicit scope (as `get_records` requires `--only`).
2. **IP derivation depth.** For the raw IP columns where Salesforce does *not* pre-derive geo: country only, or country + `/24` prefix? Proposal: country + `/24` prefix by default; finer geo opt-in. Needs a geo-IP data source decision (offline dataset vs. service — a service call would breach "all local"). Note Salesforce already provides `COUNTRY_CODE` on `Login`, reducing how often the tool must derive at all.
3. **URI sanitisation rules.** Strip the whole query string, or keep allow-listed non-PII params (e.g. `id`, `tab`)? Proposal: strip entirely by default; allow-list specific params per project via the plan.
4. **`QUERY` / free-text fields — largely resolved.** Raw `QUERY`/`SEARCH_QUERY` DROP loses less than feared: the **`UniqueQuery`** EventType already supplies a hashed `SQL_ID` fingerprint + `QUERY_TYPE`, so "which distinct queries ran, how often" survives without the raw text. Remaining prototype question: is a sanitised form (SOQL structure kept, literals stripped) worth it for OData `FILTER` and error messages, where no fingerprint exists?
5. **Cross-extract join key stability.** `USER_ID` kept RAW joins event logs to the `get_records`/`get_metadata` extracts (which also keep SF IDs RAW). Confirm the ID forms line up (15- vs 18-char; `USER_ID` vs `USER_ID_DERIVED`).
6. **Where this lives.** A new subcommand (e.g. `get_event_logs`) under the same dispatcher, reusing the classifier/plan/sentinel machinery — to be confirmed when the design starts.
