# 05 — Technical Objects Download: Goals and Requirements

**Status:** Ideation. Input to [`../05-design-v4.md`](../05-design-v4.md).
**Governed by:** [`00-design-principles.md`](00-design-principles.md) — read it first.
**Schema source (authoritative):** [`salesforce-technical-objects.md`](salesforce-technical-objects.md) — field-level reference for all 40 objects, with per-field "data content to inspect" notes and a sensitivity summary table. This doc is the *classification and requirements overlay* on that reference.
**Companions:** the record model [`02-data-download.md`](02-data-download.md) and the event-log model [`04-event-log-download.md`](04-event-log-download.md) — v4 sits between them: describe-driven field enumeration like records, pseudonymous-activity handling like event logs.

---

## 1. The problem

Salesforce's **technical objects** — the Tooling-API entities, system tables, and REST metrics endpoints catalogued in the schema reference — are where an org's *operational truth* lives: what Apex exists and how well it is tested, what runs on schedules and what fails, who holds which privileges, who logged in from where with which factor, what every admin changed in Setup, what the org's limits and data volumes are. An agent doing a security health-check, technical-debt review, or operational analysis needs them. The naive move — bulk-export the raw CSVs — hands the agent IP addresses, login geolocation down to postcode, federation identifiers, and free-text fields that routinely echo usernames and record data. Several of these tables are **bulk personal-activity data** under any reasonable acceptable-use policy.

But, as with event logs, the exposure is narrow and structured. The schema reference's summary table shows the pattern across all 40 objects:

- **Identity is pseudonymous.** Rows are keyed by Salesforce user IDs (`UserId`, `CreatedById`, `AssigneeId`, `UserOrGroupId`), not names or emails. Kept RAW, they join activity/privilege to a user *id* — the same model already accepted for event logs.
- **The personal raw values are few and salvageable:** `SourceIp` (3 objects) → network prefix; `LoginGeo`'s lat/lon/city/postcode → country/subdivision only; the odd email column → hashed; the odd username-ish string (`IdentityUsed`, `DelegateUser`) → hashed; one person-name (`Organization.PrimaryContact`) → dropped.
- **The routine DROP is free text that echoes data:** `SetupAuditTrail.Display`, `FlowInterview.InterviewLabel` (merge-field PII is *likely* there), test failure `Message`/`StackTrace`, job `ExtendedStatus`/`Error`. Their structured siblings (`Action`, `Section`, `Status` picklists, counts) carry most of the analytical signal and are kept.
- **Everything else is config and metrics** — names, picklists, counts, timestamps, permission bits — and passes whole.

## 2. Goals

1. **All 40 objects in scope.** The catalogue is the full list in the schema reference — Apex tooling (9), async/job machinery (4), debug/tracing (2), schema metadata (2), identity/session/login (7), groups/roles (3), authorization (3), audit (1), flow (1), event-monitoring headers (1), Lightning telemetry (4), organization (1), REST pseudo-endpoints (2). `--only` narrows; the default is everything available.
2. **Maximise retained signal; drop only the unsalvageable** — the same posture as event logs (B4): IDs raw, IPs derived, emails/usernames hashed, geo coarsened to country/subdivision, free-text echoes dropped (overridable with justification).
3. **No raw dump; classify in flight** (A2): raw query results stay in memory; only classified CSVs reach disk. Long-text/blob fields (`Body`, `Metadata`, `SymbolTable`, all `textarea`/`base64` types) are **never even selected** — excluded at SOQL-build time, the exclude-at-source move from v1.
4. **Read-only** (A4): SOQL/Tooling/REST `GET` only.
5. **Same collaboration model:** rule-based classifier recommends per column; `--dry-run` emits a reviewable plan; overrides need justification in the exposing direction; headless re-runs are drift-safe (a new field classifies by the conservative default).
6. **Regression-tested in the same change** (C7), README updated (C8).

## 3. Classification requirements

### 3.1 Two layers: structural skip, then per-column rules

**Layer 0 — structural field skip (at query build, never selected).** Adopted verbatim from the proven extractor: field types `base64`, `textarea`, `address`, `location`, `complexvalue`, `anyType`; field names `Body`, `Metadata`, `SymbolTable`, `FullName`, `HtmlValue`, `Content`. This keeps source code, log bodies, heap dumps, and long text out of the download entirely — the CSV column lists in the schema reference are exactly this post-skip subset.

**Layer 1 — per-column classification (first match wins), describe-driven:**

1. **Curated per-object overrides** (source-controlled table, §3.2) — the reference-driven exceptions the generic rules can't infer.
2. `type=id` / `type=reference`, and `*Id`-named strings → **RAW** (join keys; pseudonymous).
3. IP-named (`SourceIp`, `*Ip`) → **DERIVE** network prefix (the event-log recipe; never hash an IP).
4. `type=email` or email-named → **HASH** (frozen email recipe).
5. Phone-named / `type=phone` → **DROP** (family rule: low-entropy, never hash).
6. `type=url` / URL-named → **DERIVE** (host+path, query stripped).
7. Fine-grained geo names (`Latitude`, `Longitude`, `City`, `PostalCode`) → **DROP**; country/subdivision-level (`Country`, `CountryIso`, `CountryCode`, `Subdivision`, `State`) → **PASS**.
8. Free-text echo names (`Message`, `StackTrace`, `Display`, `Remarks`, `Error`, `Description`, `*Label` where curated) → **DROP**.
9. Everything else → **PASS** (picklists, booleans incl. the ~500 `PermissionsXxx` bits, counts, timestamps, config names like `Name`/`DeveloperName`/`MasterLabel`).

### 3.2 Curated overrides (the load-bearing exceptions, from the reference)

| Object.Field | Action | Why |
|---|---|---|
| `FlowInterview.InterviewLabel`, `.PauseLabel` | DROP | merge-field formatting routinely embeds `{!Contact.Name}`-style customer values — the reference's "likely customer-data echo" |
| `SetupAuditTrail.Display` | DROP | free text embedding user/field/profile names; `Action` + `Section` (PASS) keep the what/where signal |
| `SetupAuditTrail.DelegateUser` | HASH | username string |
| `IdpEventLog.IdentityUsed` | HASH | federation id / username / email used as NameID |
| `Organization.PrimaryContact` | DROP | person name (names are never hashed) |
| `AsyncApexJob.ExtendedStatus`, `ApexTestQueueItem.ExtendedStatus` | DROP | error free-text can echo processed data values |
| `BackgroundOperation.Error` | DROP / `ParentKey` → HASH | error text echoes data; ParentKey is a developer correlation key — hash keeps joins |
| `ApexLog.Status` | DROP | free-text fault messages; `Operation`/`Application` (PASS) keep the signal |
| `VerificationHistory.Remarks` | DROP | admin free text |
| `LoginHistory.Status` | PASS (explicit) | documented Salesforce status vocabulary (`Success`, `Invalid Password`, …) — central to security analysis; not user-authored text |
| `CronTrigger.CronExpression` | PASS (explicit) | schedule string, config not content |

Everything else in the 40 objects resolves through the generic rules. Per-object expected outcomes (spot-check set): `LoginGeo` keeps `CountryIso`/`Country`/`Subdivision`, drops lat/lon/city/postcode; `Group.Email` hashes; `AuthSession.LogoutUrl` / `LoginHistory.LoginUrl` derive; the Lightning telemetry and `limits`/`recordCount` tables pass untouched (pure metrics).

### 3.3 On Profile / PermissionSet / Role — not a deny-list contradiction

`get_metadata` (v1) deny-lists `Profile`, `PermissionSet`, `Role` — that exclusion targets their **Metadata API XML representation** (operationally fragile under wildcard retrieve, and a sprawling FLS payload). v4 downloads their **sObject rows**: structural columns plus boolean permission bits, keyed by IDs. That is the org's *privilege topology* — pseudonymous, queryable, and the backbone of any security review (which identities hold `ModifyAllData`, who is in which group, which assignments expire). The v1 deny list is untouched; nothing here re-enables a denied metadata type.

## 4. Requirements (functional)

- **Catalogue is a source constant**: all 40 objects with their API routing (SObject-SOQL / Tooling / REST pseudo-endpoint) and any special handling (EntityDefinition's keyset pagination on `QualifiedApiName`; the two REST endpoints' fixed schemas). Like the deny list: no runtime mechanism adds or re-routes objects.
- **Describe-driven field lists** at runtime (SObject describe / Tooling describe), filtered by Layer 0, classified by Layer 1 — drift-safe for fields Salesforce adds later.
- **Per-object fault tolerance** (the v2.1 discipline): an object the identity cannot query (missing permission, unsupported in edition) is skipped and recorded, not fatal. `limits`, `AuthSession`, `SetupAuditTrail` etc. all have permission gates that vary by org.
- **Pagination**, not Bulk, v4-initial: REST `query`/`queryMore` for SObject-routed objects, Tooling query for Tooling-routed, plus the EntityDefinition special case. (The proven tool uses Bulk for the big tables; Bulk adds a dependency and a raw-CSV-on-the-wire path — deferred, recorded as a simplification. `--limit` caps rows per object for smoke runs.)
- **Snapshot output model** (like `get_records`, unlike event logs): one `<ApiName>.csv` per object; clear-and-republish; sentinel `_field-handling-applied.csv` last; `_extract-summary.json` with per-object rows/columns/action counts and skip reasons.
- **CLI:** `get_technical_objects --org-alias --path [--only <Object> ...] [--limit N] [--plan FILE] [--dry-run]` — all narrowing/specification inputs; nothing disables the classifier.

## 5. Acceptable-use compliance map

| Policy rule | How v4 complies |
|---|---|
| No processing of Restricted data (bulk personal data, special-category) | Identity is pseudonymous IDs; IPs → prefix; geo → country/subdivision; emails/usernames hashed; person names and data-echoing free text dropped — before any write. |
| Anonymisation mandatory before AI analysis of bulk personal data | LoginHistory/AuthSession/VerificationHistory (the bulk-activity tables) get the same in-flight treatment already accepted for event logs (04). |
| No secrets/credentials to the agent | Blob/long-text fields (`Body`, `Metadata`, `SymbolTable`, …) never selected; no credential-bearing object is in the catalogue. |
| No direct production access for the agent | The agent reads the published folder; the tool holds the session (A1). Read-only (A4). |
| All output local | SOQL/Tooling/REST GET to the authorised org only; no other network calls. |

## 6. Out of scope (v4-initial)

- Bulk API transport for very large tables (deferred; pagination first).
- Incremental/windowed accumulation for the retention-limited tables (`LoginHistory` 6 months, `SetupAuditTrail` 180 days, `IdpEventLog` 30 days) — snapshot per run now; an event-log-style incremental mode is a natural later iteration and the design should not preclude it.
- Sanitised retention of dropped free-text (e.g. a redacted `SetupAuditTrail.Display`) — same future-work status as the SOQL-sanitiser idea in 04.
- Objects beyond the 40-object catalogue — additions are maintainer changes with review.

## 7. Open questions

1. **`Description` columns** (PermissionSet, Profile, RecordType, SessionPermSetActivation): admin-authored config text, usually safe and genuinely useful. Generic rule 8 drops them; is a curated PASS for these four defensible? Default: DROP, overridable per plan — revisit after first real runs.
2. **`EventLogFile` header rows** duplicate what `get_event_logs` already reports. Keep in the catalogue (cheap, useful inventory) or exclude to avoid overlap? Default: keep.
3. **Very large tables** (`GroupMember`, `LoginHistory` at enterprise scale) under queryMore pagination: acceptable runtime? If not, Bulk moves up the priority list.
4. **`recordCount`/`limits`** reveal org scale — Confidential, not Restricted; fine for the agent, but confirm they should be in the default scope (they are).
