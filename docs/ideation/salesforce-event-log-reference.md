# Salesforce EventLogFile Reference

A field-by-field reference for the Salesforce **EventLogFile** EventTypes that an Event Monitoring-enabled org emits.

- **Source of column lists:** observed CSV headers from EventLogFile downloads. Salesforce evolves the schema across API versions, so columns may be added or dropped over time.
- **Source of column descriptions:** Salesforce EventLogFile Object Reference (Platform Event docs).
- **65 EventTypes** covered.
- **Data sensitivity:** the rows in these files contain user-level activity (USER_ID, CLIENT_IP, SESSION_KEY, URI, query text). This reference documents the *schema only*, not any row content.

---

## 1. File format

Each EventLogFile is a downloaded artefact from one Salesforce `EventLogFile` record. The downloader writes one file per record at:

```
[base]/event_logs/[org_alias]/[start_date]_to_[end_date]/[LogDate]_[EventType]_[Id].csv
```

- **Encoding:** UTF-8, no BOM.
- **Line ending:** LF.
- **Delimiter:** comma.
- **Quoting:** all fields wrapped in `"` double quotes. Embedded quotes are escaped by doubling (`""`).
- **First row:** header. All header names are upper-snake-case.
- **Body rows:** one row per event instance. A single CSV typically holds 24 hours of events of one EventType for one org (Interval = "Daily"); some EventTypes also publish at hourly intervals.
- **Empty cells:** literal empty string between commas (e.g. `,,`), not the string `null`.

EventLogFile records (and therefore these CSVs) are retained for **30 days** by default (1 day on orgs without Event Monitoring add-on). Files older than that on disk are local copies; they no longer exist in Salesforce.

---

## 2. Common columns

Most EventTypes share a "transaction header" set of columns. Rather than repeating them per type below, here is the canonical meaning. A column listed under a specific EventType refers back to this table by name.

| Column | Meaning |
|---|---|
| `EVENT_TYPE` | The EventType string, identical to the type embedded in the filename. |
| `TIMESTAMP` | Wall-clock time the event occurred. Format `YYYYMMDDhhmmss.fff` (Salesforce internal). |
| `TIMESTAMP_DERIVED` | The same time, normalised to ISO-8601 UTC (`YYYY-MM-DDThh:mm:ss.fffZ`). Use this for analysis. |
| `REQUEST_ID` | Salesforce-generated identifier for the originating request. Joins events across EventTypes for the same transaction. |
| `ORGANIZATION_ID` | 15- or 18-char Salesforce Org Id (`00D…`). |
| `USER_ID` | 15-char Salesforce User Id of the requester. May be empty for guest/anonymous events. |
| `USER_ID_DERIVED` | 18-char (case-safe) form of USER_ID. Prefer this when joining to other tables. |
| `USER_TYPE` | Standard / Guest / CustomerPortalManager / PowerCustomerSuccess / etc. |
| `CLIENT_IP` | IPv4/IPv6 of the client. May be the public IP of an intermediate proxy. |
| `URI` | The Salesforce-side URL path of the request. |
| `URI_ID_DERIVED` | 18-char Id parsed out of the URI, if the URI contains a record Id. |
| `RUN_TIME` | Total wall-clock time of the operation, in **milliseconds** (some events use microseconds — check per-type). |
| `CPU_TIME` | Apex CPU time consumed, in **milliseconds**. |
| `DB_TOTAL_TIME` | Total database time for the request, in **nanoseconds**. |
| `DB_BLOCKS` | Number of database blocks read. |
| `DB_CPU_TIME` | Database CPU time, in **milliseconds**. |
| `SESSION_KEY` | Hashed session identifier; correlates events in the same session without exposing the actual session token. |
| `LOGIN_KEY` | Hashed login identifier; correlates a user's activity within a single login window. |
| `REQUEST_STATUS` | Salesforce-internal status code for the request (`S` success, `F` failed, etc.). |
| `BOT_ID`, `BOT_SESSION_ID`, `PLANNER_ID` | Agentforce / Einstein Copilot correlation IDs. Empty when the request was not initiated by an agent. |
| `CONNECTED_APP_ID`, `CONNECTED_APP_NAME` | The Connected App through which the request was authenticated. |
| `CLIENT_NAME` | Name supplied by the OAuth client (e.g. "Workbench", "sfdx", or any deployment tool's identifier). |

Everywhere below, **bolded** columns are the ones that distinguish the EventType. Plain columns are the common header above.

---

## 3. EventType reference (alphabetical)

### 3.1 API

REST/SOAP API call (not Apex REST and not Bulk). Issued by external clients against `/services/data/...` endpoints.

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, RUN_TIME, CPU_TIME, URI, SESSION_KEY, LOGIN_KEY, USER_TYPE, REQUEST_STATUS, DB_TOTAL_TIME | common |
| **API_TYPE** | `REST`, `SOAP_PARTNER`, `SOAP_ENTERPRISE`, `SOAP_METADATA`, `SOAP_CROSS_INSTANCE`, etc. |
| **API_VERSION** | API version of the request (e.g. `60.0`). |
| **CLIENT_NAME** | Caller-supplied client name. |
| **METHOD_NAME** | SOAP method or REST verb + resource. |
| **ENTITY_NAME** | Primary sObject involved. |
| **ROWS_PROCESSED** | Rows returned / mutated. |
| **REQUEST_SIZE** / **RESPONSE_SIZE** | Bytes. |
| DB_BLOCKS, DB_CPU_TIME | common |
| **EXCEPTION_MESSAGE** | Populated on failure. |
| **QUERY** | SOQL text, if applicable. |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP, URI_ID_DERIVED | common |

### 3.2 ApexCallout

Outbound HTTP callout made by Apex (`Http.send` and friends).

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, RUN_TIME, CPU_TIME, URI, SESSION_KEY, LOGIN_KEY | common |
| **TYPE** | Callout type (`Http`, `WebService`). |
| **METHOD** | HTTP verb. |
| **SUCCESS** | `1` / `0`. |
| **STATUS_CODE** | HTTP response status. |
| **TIME** | Callout duration, milliseconds. |
| **REQUEST_SIZE** / **RESPONSE_SIZE** | Bytes. |
| **URL** | Outbound URL called. |
| BOT_ID, BOT_SESSION_ID, PLANNER_ID | common |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP, URI_ID_DERIVED | common |

### 3.3 ApexExecution

Top-level Apex execution event (one per transaction/anonymous block/trigger entry).

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, RUN_TIME, CPU_TIME, URI, SESSION_KEY, LOGIN_KEY | common |
| **EXEC_TIME** | Apex execution time, ms. |
| **DB_TOTAL_TIME** | ns, see common. |
| **CALLOUT_TIME** | Time spent in outbound callouts, ms. |
| **NUMBER_SOQL_QUERIES** | SOQL count. |
| **ENTRY_POINT** | Class.method or trigger entry. |
| **QUIDDITY** | Internal Apex transaction category (`Synchronous`, `Queueable`, `Future`, `Batch`, `Schedule`, `Trigger`, `VF`, etc.). |
| **IS_LONG_RUNNING_REQUEST** | `1` if the request exceeded the long-running threshold (5 s). |
| BOT_ID, BOT_SESSION_ID, PLANNER_ID | common |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP, URI_ID_DERIVED | common |

### 3.4 ApexRestApi

Hit on a custom Apex REST endpoint (`@RestResource` class).

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, RUN_TIME, CPU_TIME, URI, SESSION_KEY, LOGIN_KEY, USER_TYPE, REQUEST_STATUS, DB_TOTAL_TIME | common |
| **METHOD** | HTTP verb. |
| **MEDIA_TYPE** | Content-type negotiated. |
| **STATUS_CODE** | HTTP response. |
| **USER_AGENT** | Caller user agent. |
| **ROWS_PROCESSED**, **NUMBER_FIELDS** | Volume metrics. |
| DB_BLOCKS, DB_CPU_TIME | common |
| **REQUEST_SIZE**, **RESPONSE_SIZE** | Bytes. |
| **ENTITY_NAME** | Primary sObject. |
| CONNECTED_APP_ID, CLIENT_NAME | common |
| **EXCEPTION_MESSAGE**, **QUERY** | Free-text fault / SOQL. |
| BOT_ID, BOT_SESSION_ID, PLANNER_ID | common |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP, URI_ID_DERIVED | common |

### 3.5 ApexTrigger

Execution of a single Apex trigger.

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, RUN_TIME, CPU_TIME, URI, SESSION_KEY, LOGIN_KEY, USER_TYPE, REQUEST_STATUS, DB_TOTAL_TIME | common |
| **TRIGGER_ID** | 15-char Id of the trigger. |
| **TRIGGER_NAME** | Apex trigger name. |
| **ENTITY_NAME** | sObject the trigger fired on. |
| **TRIGGER_TYPE** | `BeforeInsert`, `AfterUpdate`, etc. |
| **EXEC_TIME** | Trigger execution time, ms. |
| BOT_ID, BOT_SESSION_ID, PLANNER_ID | common |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP, URI_ID_DERIVED | common |

### 3.6 ApexUnexpectedException

An uncaught Apex exception. Lean schema — no perf columns.

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID | common |
| **APEX_ENTITY_NAME** | Class.method or trigger that threw. |
| **EXCEPTION_TYPE** | Apex exception class name. |
| **EXCEPTION_MESSAGE** | Message text. |
| **STACK_TRACE** | Full Apex stack. |
| **EXCEPTION_CATEGORY** | `User` (governor limit / null pointer) vs `System`. |
| TIMESTAMP_DERIVED, USER_ID_DERIVED | common |

### 3.7 ApiTotalUsage

A per-call API usage record used to enforce daily API limits. Logged for every API request that counts against the limit.

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID | common |
| **API_FAMILY** | `Rest`, `Soap`, `Bulk`, `Streaming`, `Metadata`, `Tooling`, `GraphQL`, etc. |
| **API_VERSION** | API version. |
| **API_RESOURCE** | The endpoint hit. |
| **CLIENT_NAME** | OAuth client name. |
| **HTTP_METHOD** | Verb. |
| CLIENT_IP | common |
| **COUNTS_AGAINST_API_LIMIT** | `1` / `0`. |
| CONNECTED_APP_ID | common |
| **ENTITY_NAME** | sObject. |
| **STATUS_CODE** | HTTP status. |
| CONNECTED_APP_NAME | common |
| **USER_NAME** | Username string of the caller. |
| **API_CLIENT_CATEGORY** | `Customer`, `Partner`, `Internal`, `Salesforce_Client`, etc. |
| BOT_ID, BOT_SESSION_ID, PLANNER_ID, TIMESTAMP_DERIVED | common |

### 3.8 AsyncReportRun

A report run executed asynchronously (large report, dashboard refresh, scheduled report).

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, RUN_TIME, CPU_TIME, URI, SESSION_KEY, LOGIN_KEY, USER_TYPE, REQUEST_STATUS, DB_TOTAL_TIME | common |
| **ENTITY_NAME** | Primary sObject of the report. |
| **DISPLAY_TYPE** | `Tabular`, `Summary`, `Matrix`, `Joined`. |
| **RENDERING_TYPE** | `HTML`, `Printable`, `Export`, `JSON`, etc. |
| **REPORT_ID** | 15-char Id. |
| **ROW_COUNT** | Rows in result. |
| **NUMBER_EXCEPTION_FILTERS**, **NUMBER_COLUMNS**, **UI_NUMBER_COLUMNS** | Definition shape. |
| **AVERAGE_ROW_SIZE** | Bytes. |
| **SORT** | Sort specification. |
| DB_BLOCKS, DB_CPU_TIME | common |
| **NUMBER_BUCKETS** | Bucket field count. |
| **DASHBOARD_ID** | Populated when triggered by a dashboard refresh. |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP, URI_ID_DERIVED | common |
| **REPORT_ID_DERIVED** | 18-char form. |
| **ORIGIN** | What triggered the run (`Manual`, `Dashboard`, `Scheduled`, `API`). |

### 3.9 Attachment

Activity against the legacy `Attachment` object (mostly superseded by Files / ContentDocument).

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID | common |
| **PARENT_ID** | Record the attachment was attached to. |
| **ATTACHMENT_ID** | Attachment Id. |
| **CONTENT_TYPE** | MIME. |
| **OPERATION** | `Insert`, `Update`, `Delete`, `Download`. |
| **IS_PRIVATE_ON** | Attachment.IsPrivate flag. |
| TIMESTAMP_DERIVED | common |

### 3.10 AuraRequest

An Aura framework server request (Lightning Experience pre-LWC, and some LWC server actions).

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, RUN_TIME, CPU_TIME, URI, SESSION_KEY, LOGIN_KEY, USER_TYPE, REQUEST_STATUS, DB_TOTAL_TIME | common |
| **USER_AGENT** | Browser UA. |
| **REQUEST_METHOD** | HTTP verb. |
| **ACTION_MESSAGE** | Aura action descriptor (controller.method). |
| **EASY_SUITE_VALUE** | Internal Salesforce diagnostic field. |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP, URI_ID_DERIVED | common |

### 3.11 BlockedRedirections

Logged when Salesforce's URL redirect protection blocked an open-redirect attempt.

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID | common |
| **MALFORMED_URL** | The URL that triggered the block. |
| **BLOCKED_URI** / **BLOCKED_URI_DOMAIN** | The would-be redirect target. |
| **ORIGIN** | Where the redirect was attempted from. |
| **REFERRER** | HTTP Referer. |
| **REMOTE_ADDRESS** | Client IP. |
| TIMESTAMP_DERIVED | common |

### 3.12 BulkApi

A Bulk API v1 job's batch.

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, RUN_TIME, CPU_TIME, URI, SESSION_KEY, LOGIN_KEY | common |
| **JOB_ID** / **BATCH_ID** | Bulk API job and batch Ids. |
| **ROWS_PROCESSED**, **NUMBER_FAILURES** | Outcome. |
| **SUCCESS** | `1` / `0`. |
| **MESSAGE** | Error message. |
| **ENTITY_TYPE** | sObject. |
| **OPERATION_TYPE** | `insert`, `update`, `upsert`, `delete`, `hardDelete`, `query`. |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP, URI_ID_DERIVED | common |

### 3.13 BulkApi2

A Bulk API v2 job (one row per job, not per batch).

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, RUN_TIME, CPU_TIME, URI, SESSION_KEY, LOGIN_KEY | common |
| **JOB_ID** | v2 job Id. |
| **OPERATION_TYPE** | As v1, plus `queryAll`. |
| **ENTITY_TYPE** | sObject. |
| **JOB_STATUS** | `Open`, `UploadComplete`, `JobComplete`, `Failed`, `Aborted`. |
| **RECORDS_PROCESSED**, **RECORDS_FAILED** | Outcome counts. |
| **RESULT_SIZE_MB** | Size of result set returned. |
| **ERROR_MESSAGE** | Failure detail. |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP, URI_ID_DERIVED | common |

### 3.14 BulkApiRequest

The HTTP request layer that delivered a Bulk API call (the v1/v2 events above describe outcome; this one describes the request).

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, RUN_TIME, CPU_TIME, URI, SESSION_KEY, LOGIN_KEY | common |
| **REQUEST_PATH** | Sub-path under `/services/async/...`. |
| **API_VERSION** | API version. |
| **JOB_ID** / **BATCH_ID** | Bulk Ids. |
| **OPERATION_TYPE** | Same as BulkApi. |
| **SUCCESS** | `1` / `0`. |
| **ERROR_MESSAGE** | Error text. |
| CONNECTED_APP_ID, CLIENT_NAME | common |
| **CONCURRENCY_MODE** | `Parallel` or `Serial`. |
| **STATUS_CODE** | HTTP status. |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP, URI_ID_DERIVED | common |

### 3.15 CSPViolation

Browser-reported Content Security Policy violation against a Salesforce-served page.

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID | common |
| **BLOCKED_URI** / **BLOCKED_URI_DOMAIN** | Resource the page tried to load. |
| **DIRECTIVE** | Which CSP directive was violated (e.g. `script-src`). |
| **CONTEXT** | Page or component context. |
| **UNIQUE_ID** | CSP report Id (deduplication key). |
| **DISPOSITION** | `enforce` or `report`. |
| **SOURCE** | Browser-reported source. |
| **COLUMN_NUMBER** / **LINE_NUMBER** / **SOURCE_FILE** | Where in the offending script. |
| **RESOURCE_SAMPLE** | Up to ~40 bytes of the offending content. |
| TIMESTAMP_DERIVED | common |

### 3.16 CompositeApi

A single Composite API call (one HTTP request bundling multiple subrequests).

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, RUN_TIME, CPU_TIME, URI, SESSION_KEY, LOGIN_KEY | common |
| **ALL_OR_NONE** | `1` / `0`. |
| **FAILURE_REASON** | If the composite failed. |
| **IS_REQUEST_COLLATION_ON** | `1` if subrequests were collated. |
| **NUM_RETRIES** | Retry count. |
| **NUM_GRAPH_DEPTH** | For composite-graph, max depth. |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP, URI_ID_DERIVED | common |

### 3.17 CompositeApiSubrequest

One subrequest inside a Composite API call (joined to CompositeApi via REQUEST_ID).

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, RUN_TIME, CPU_TIME, URI, SESSION_KEY, LOGIN_KEY, USER_TYPE, REQUEST_STATUS, DB_TOTAL_TIME | common |
| **METHOD** | HTTP verb of the subrequest. |
| **IS_CANCELLED** | `1` if skipped because an earlier sibling failed. |
| **CANCELLED_REASON** | Free text. |
| **SUCCESS** | `1` / `0`. |
| **STATUS_CODE** | HTTP status returned to the caller. |
| **INITIAL_REFERENCE_IDS** | The `referenceId` values of the subrequests this one depends on. |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP, URI_ID_DERIVED | common |

### 3.18 ConcurrentLongRunningApexLimit

Emitted when an Apex request was throttled because the org hit its concurrent long-running Apex limit (10 concurrent >5 s requests).

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID | common |
| **NUMBER_REQUESTS** | Concurrent requests at the time. |
| **REQUESTS_LIMIT** | The limit (typically 10). |
| ORGANIZATION_ID, USER_ID | common |
| **REQUEST_URI** | The URL of the throttled request. |
| TIMESTAMP_DERIVED | common |

### 3.19 ContentDistribution

Creation / update / delete of a Content Delivery (public-link share of a file).

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID | common |
| **DELIVERY_ID** | The ContentDistribution Id. |
| USER_ID | common |
| **VERSION_ID** | ContentVersion shared. |
| **RELATED_ENTITY_ID** | Linked record. |
| **DELIVERY_LOCATION** | Where the link was generated from. |
| **ACTION** | `Created`, `Updated`, `Deleted`, `Accessed`. |
| TIMESTAMP_DERIVED, USER_ID_DERIVED | common |

### 3.20 ContentDocumentLink

A file was shared with a user, group, record, or library.

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID | common |
| **DOCUMENT_ID** | ContentDocument Id. |
| **SHARED_WITH_ENTITY_ID** | User / Group / Record / Library Id. |
| **SHARING_PERMISSION** | `V` (view), `C` (collaborator), `I` (inferred). |
| **SHARING_OPERATION** | `Insert`, `Update`, `Delete`. |
| TIMESTAMP_DERIVED, USER_ID_DERIVED | common |

### 3.21 ContentTransfer

File upload / download / preview transferred bytes.

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID | common |
| **TRANSACTION_TYPE** | `ContentUpload`, `ContentDownload`, `ContentPreview`. |
| ORGANIZATION_ID, USER_ID | common |
| **DOCUMENT_ID**, **VERSION_ID** | The file moved. |
| **FILE_TYPE** | Extension / type. |
| **FILE_PREVIEW_TYPE** | Preview rendition. |
| **SIZE_BYTES** | Transfer size. |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, DOCUMENT_ID_DERIVED, VERSION_ID_DERIVED | common |

### 3.22 CorsViolation

A cross-origin request was blocked by CORS policy on a Salesforce endpoint.

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID | common |
| **ORIGIN** | Origin header of the blocked request. |
| **HOST** | Salesforce host that received it. |
| TIMESTAMP_DERIVED | common |

### 3.23 Dashboard

A dashboard was viewed or refreshed.

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, RUN_TIME, CPU_TIME, URI, SESSION_KEY, LOGIN_KEY | common |
| **DASHBOARD_COMPONENT_ID** | The component within the dashboard. |
| **DASHBOARD_ID** | Dashboard Id. |
| **REPORT_ID** | Underlying report for the component. |
| **IS_SUCCESS** | `1` / `0`. |
| **DASHBOARD_TYPE** | `LoggedInUser`, `RunAsUser`, `MeUser`. |
| **IS_SCHEDULED** | `1` if it was a scheduled refresh. |
| **VIEWING_USER_ID** | The user actually viewing. |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP, URI_ID_DERIVED, DASHBOARD_ID_DERIVED, REPORT_ID_DERIVED | common |

### 3.24 DatabaseSave

A DML save committed to the database.

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID | common |
| **KEY_PREFIX** | The 3-char Salesforce Id prefix of the entity (e.g. `001` = Account). |
| **DML_TYPE** | `insert`, `update`, `upsert`, `delete`, `undelete`. |
| **NUM_ROWS** | Rows in the save. |
| **SAMPLE_FACTOR** | Sampling factor — DatabaseSave is sampled, not exhaustive. Multiply NUM_ROWS by this to estimate real volume. |
| **FIRST_ENTITY_ID** | Id of the first row in the save. |
| SESSION_KEY, LOGIN_KEY, TIMESTAMP_DERIVED | common |

### 3.25 DocumentAttachmentDownloads

Download of a legacy Document or Attachment (precursor to Files).

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID | common |
| **ENTITY_ID** | Document or Attachment Id. |
| **FILE_TYPE** | Extension / type. |
| USER_ID, TIMESTAMP_DERIVED, USER_ID_DERIVED | common |

### 3.26 ExternalODataCallout

An outbound call to an OData-protocol external data source (Salesforce Connect).

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID | common |
| **ENTITY** | External entity queried. |
| **OFFSET**, **LIMIT** | Pagination. |
| **SELECT**, **FILTER**, **ORDERBY**, **EXPAND**, **SEARCH** | OData query options. |
| **NEXT_LINK** | Next-page link. |
| **PARENT_CALLOUT** | Parent callout Id, if this is a continuation. |
| **STATUS** | Outcome. |
| **TOTAL_MS** / **EXECUTE_MS** / **FETCH_MS** | Latency breakdown. |
| **ROWS** / **ROWS_FETCHED** | Volume. |
| **BYTES** | Payload size. |
| **REQUESTS** | Number of HTTP requests made. |
| **THROUGHPUT** | Computed throughput. |
| **RATE_LIMIT_USAGE_PERCENT** | Of the external rate limit, if exposed. |
| **MESSAGE** | Free-text status / error. |
| **PROVIDER_TYPE** | Connect provider class. |
| **ACTION** | OData verb. |
| **LIBRARY** | Internal OData library version. |
| TIMESTAMP_DERIVED | common |

### 3.27 FlowExecution

A single execution of a Flow (record-triggered, screen, scheduled, autolaunched, etc.).

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, BOT_ID, BOT_SESSION_ID, PLANNER_ID, ORGANIZATION_ID, USER_ID | common |
| **PROCESS_TYPE** | `Flow`, `AutoLaunchedFlow`, `Workflow`, `InvocableProcess`, `CustomEvent`, etc. |
| **FLOW_VERSION_ID** | The exact flow version that ran. |
| **FLOW_LOAD_TIME** | Time to load the flow definition, ms. |
| **TOTAL_EXECUTION_TIME** | End-to-end ms. |
| **NUMBER_OF_INTERVIEWS** | Interviews started in this run. |
| **NUMBER_OF_ERRORS** | Errors raised. |
| TIMESTAMP_DERIVED | common |

### 3.28 GroupMembership

A user / group was added to / removed from a Salesforce Group.

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, RUN_TIME, CPU_TIME, URI, SESSION_KEY, LOGIN_KEY | common |
| **OPERATION** | `Add` or `Remove`. |
| **GROUP_TYPE** | `Public`, `Queue`, `Regular`, `Role`, `RoleAndSubordinates`, etc. |
| **GROUP_ID** | The group. |
| **MEMBER_ID** | The user or group added/removed. |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP, URI_ID_DERIVED | common |

### 3.29 InsufficientAccess

A user attempted an operation they were not authorised to perform; the access denial was logged.

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID | common |
| **RECORD_ID** | The record the user tried to touch. |
| **ENTITY_TYPE** | sObject. |
| **ACCESS_ERROR** | The specific denial reason. |
| **REQUESTED_ACCESS_LEVEL** | `Read`, `Edit`, `Delete`, `All`, etc. |
| **ERROR_TIMESTAMP** | When the error fired. |
| **ERROR_DESCRIPTION** | Human-readable. |
| **ACTUAL_LOGGED_IN_USER_ID** | Useful when the action was performed as another user (LoginAs). |
| TIMESTAMP_DERIVED, USER_ID_DERIVED | common |

### 3.30 InvocableAction

An invocable action was invoked from Flow / Apex / API. Heavily used by Agentforce / Einstein Copilot.

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, BOT_ID, BOT_SESSION_ID, PLANNER_ID | common |
| **ACTION_TYPE** | `apex`, `flow`, `emailAlert`, etc. |
| **ACTION_NAME** | Action identifier. |
| **ACTION_VERSION** | Version number. |
| **REQUEST_COUNT** | Batched call count. |
| ORGANIZATION_ID, USER_ID | common |
| **INVOCATION_SOURCE** | `Flow`, `Apex`, `API`, `Bot`. |
| **FLOW_PROCESS_TYPE** | If invoked by Flow. |
| **FLOW_VERSION_ID** | If invoked by Flow. |
| **INVOKING_APEX_CLASS_NAME** | If invoked by Apex. |
| **PROMPT_TEMPLATE** | Prompt template Id, for AI / generative actions. |
| **AGENT_ACTION** | Agent action Id. |
| **INTERNAL_INVOKER** | `1` if internal-only call. |
| **DURATION** | ms. |
| TIMESTAMP_DERIVED | common |
| **API_CALLER** | Calling API client. |

### 3.31 KnowledgeArticleView

A knowledge article was viewed (e.g. via Communities, Service Console, Agentforce).

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID | common |
| **SESSION_ID** | Viewing session. |
| USER_ID, USER_TYPE | common |
| **CONTEXT** | Where the view happened (Console, Community, Agent, etc.). |
| **ENTITY** | Article sObject. |
| **LANGUAGE** | Article locale. |
| **LAST_VERSION** | `1` if viewed the latest version. |
| **ARTICLE_STATUS** | `Online`, `Draft`, `Archived`. |
| **ARTICLE_ID**, **ARTICLE_VERSION_ID**, **ARTICLE_VERSION** | Article identity. |
| **LARGE_LANGUAGE_MODEL** | Populated when an LLM surfaced the article (Agentforce). |
| TIMESTAMP_DERIVED, USER_ID_DERIVED | common |

### 3.32 LightningError

A JavaScript error thrown in the Lightning Experience or LWC client. Reported by the browser.

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, CLIENT_ID, SESSION_KEY, LOGIN_KEY, USER_TYPE | common |
| **APP_NAME** | Lightning app. |
| **DEVICE_PLATFORM**, **DEVICE_MODEL**, **DEVICE_ID** | Device fingerprint. |
| **SDK_APP_VERSION**, **SDK_VERSION**, **SDK_APP_TYPE** | Mobile SDK info. |
| **OS_NAME**, **OS_VERSION** | OS. |
| **USER_AGENT**, **BROWSER_NAME**, **BROWSER_VERSION** | Browser. |
| **CLIENT_GEO** | Coarse geolocation (country). |
| **CONNECTION_TYPE** | `wifi`, `4g`, etc. |
| **UI_EVENT_ID**, **UI_EVENT_TYPE**, **UI_EVENT_SOURCE**, **UI_EVENT_TIMESTAMP** | Browser-event identity. |
| **PAGE_START_TIME** | When the page started loading. |
| **DEVICE_SESSION_ID** | Per-device session. |
| **UI_EVENT_SEQUENCE_NUM** | Ordering within the page. |
| **PAGE_ENTITY_ID**, **PAGE_ENTITY_TYPE**, **PAGE_CONTEXT**, **PAGE_URL**, **PAGE_APP_NAME** | Page identity. |
| **COMPONENT_NAME** | Lightning component that threw. |
| **STACK_TRACE**, **MESSAGE** | Error detail. |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP | common |

### 3.33 LightningInteraction

A user clicked / navigated / interacted with a Lightning UI element.

| Column | Notes |
|---|---|
| (Most columns same as LightningError) | common |
| **DURATION** | Interaction duration, ms. |
| **PAGE_FLEXI_PAGE_NAME_OR_ID**, **PAGE_FLEXI_PAGE_TYPE** | (LightningPageView only; not here.) |
| **TARGET_UI_ELEMENT** | The element interacted with. |
| **PARENT_UI_ELEMENT**, **GRANDPARENT_UI_ELEMENT** | DOM ancestry. |
| **COMPONENT_NAME** | Component that handled the interaction. |
| **RECORD_TYPE**, **RECORD_ID**, **RELATED_LIST** | If the interaction targeted a record. |

(Common page/device/browser columns identical to LightningError; see 3.32.)

### 3.34 LightningPageView

A Lightning page was navigated to.

| Column | Notes |
|---|---|
| (Standard device / browser / page columns as in LightningError) | common |
| **DURATION** | Total render time, ms. |
| **EFFECTIVE_PAGE_TIME** | Effective page-time metric (Salesforce's normalised TTI). |
| **EFFECTIVE_PAGE_TIME_DEVIATION** / **_REASON** / **_ERROR_TYPE** | Why EPT is/is not trustworthy for this row. |
| **PREVPAGE_ENTITY_ID** / **_TYPE** / **_CONTEXT** / **_URL** / **_APP_NAME** | The page navigated *from*. |
| **PAGE_FLEXI_PAGE_NAME_OR_ID**, **PAGE_FLEXI_PAGE_TYPE** | Flexipage identity. |
| **TARGET_UI_ELEMENT**, **PARENT_UI_ELEMENT**, **GRANDPARENT_UI_ELEMENT** | Triggering element. |

### 3.35 LightningPerformance

Performance metrics for a Lightning interaction (RUM).

| Column | Notes |
|---|---|
| (Standard device / browser / page columns as in LightningError) | common |
| **DURATION** | ms. |
| (No UI-element-identity columns — this one is purely timing.) | |

### 3.36 Login

A login attempt (successful or failed). The richest of the security events.

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, RUN_TIME, CPU_TIME, URI, SESSION_KEY, LOGIN_KEY, USER_TYPE, REQUEST_STATUS, DB_TOTAL_TIME | common |
| **LOGIN_TYPE** | `Application`, `RemoteAccess20`, `SAML`, `OAuthRefresh`, `Partner`, `MyDomain`, etc. |
| **BROWSER_TYPE** | UA-derived. |
| **API_TYPE**, **API_VERSION** | If logged in via an API. |
| **USER_NAME** | Username supplied. |
| **TLS_PROTOCOL**, **CIPHER_SUITE** | Transport security. |
| **USE_API_TOKEN** | `1` if a security token was used. |
| **HTTP_REFERER** | If browser login. |
| **LOGIN_URL** | The MyDomain or org-specific login URL. |
| **COUNTRY_CODE** | ISO 2-letter, derived from IP. |
| **AUTHENTICATION_METHOD_REFERENCE** | OIDC `amr` value (`pwd`, `mfa`, `sms`, `email`, `u2f`, etc.). |
| **LOGIN_SUB_TYPE** | Finer-grained login subtype. |
| **AUTHENTICATION_SERVICE_ID** | Auth provider Id. |
| **AUTHENTICATION_CONTEXT_CLASS_REFERENCE** | OIDC `acr`. |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP, URI_ID_DERIVED | common |
| **LOGIN_STATUS** | Standard Salesforce login status string. |
| **SOURCE_IP**, **FORWARDED_FOR_IP** | Direct client IP and X-Forwarded-For header. |

### 3.37 LoginAs

An admin used "Login As" to impersonate another user (within the same org).

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, RUN_TIME, CPU_TIME, URI, SESSION_KEY, LOGIN_KEY | common |
| **DELEGATED_USER_NAME**, **DELEGATED_USER_ID** | The user being impersonated. |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP, URI_ID_DERIVED, DELEGATED_USER_ID_DERIVED | common |

### 3.38 Logout

A logout event (user-initiated or session expiry).

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, USER_TYPE | common |
| **SESSION_TYPE** | `UI`, `API`, `OAuth2`, etc. |
| **SESSION_LEVEL** | `Standard` / `HighAssurance`. |
| **BROWSER_TYPE**, **PLATFORM_TYPE**, **RESOLUTION_TYPE** | Client fingerprint. |
| **APP_TYPE**, **CLIENT_VERSION** | App / SDK info. |
| **API_TYPE**, **API_VERSION** | If API logout. |
| **USER_INITIATED_LOGOUT** | `1` user clicked logout, `0` session expired. |
| SESSION_KEY, LOGIN_KEY, TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP | common |

### 3.39 MetadataApiOperation

A Metadata API operation (`deploy`, `retrieve`, `listMetadata`, etc.).

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, RUN_TIME, CPU_TIME, URI, SESSION_KEY, LOGIN_KEY | common |
| **CLIENT_ID** | OAuth client. |
| **OPERATION** | The metadata operation name. |
| **API_VERSION** | API version. |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP, URI_ID_DERIVED | common |

### 3.40 MultiBlockReport

A joined / multi-block report was run.

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, RUN_TIME, CPU_TIME, URI, SESSION_KEY, LOGIN_KEY, USER_TYPE, REQUEST_STATUS, DB_TOTAL_TIME | common |
| **MASTER_REPORT_ID** | The container report Id. |
| **HAS_CHART** | `1` / `0`. |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP, URI_ID_DERIVED | common |

### 3.41 NamedCredential

Authenticated callout via a Named Credential (or External Credential).

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, RUN_TIME, CPU_TIME, URI, SESSION_KEY, LOGIN_KEY | common |
| **NAMED_CREDENTIAL_NAME** | The credential developer name. |
| **CALLER_PACKAGE_NAMESPACE** | Namespace of the package that issued the callout. |
| BOT_ID, BOT_SESSION_ID, PLANNER_ID | common |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP, URI_ID_DERIVED | common |

### 3.42 OneCommerceUsage

B2B Commerce / OneCommerce service usage event.

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, RUN_TIME, CPU_TIME, URI, SESSION_KEY, LOGIN_KEY, USER_TYPE, REQUEST_STATUS, DB_TOTAL_TIME | common |
| **CORRELATION_ID** | Cross-system correlation. |
| **WEBSTORE_ID** | The WebStore. |
| **WEBSTORE_TYPE** | B2B / B2C / etc. |
| **EFFECTIVE_ACCOUNT_ID** | Buyer account context. |
| **SERVICE_NAME** | Commerce service hit. |
| **OPERATION** / **OPERATION_TIME** / **OPERATION_STAGE** / **OPERATION_STATUS** / **OPERATION_STATE** | Operation telemetry. |
| **CONTEXT_ID** | Context identifier. |
| **COUNT** | Volume metric. |
| **IS_RETRY** | `1` / `0`. |
| **CONTEXT_MAP** | JSON-ish blob of contextual key/value pairs. |
| **ERROR_CODE**, **ERROR_MESSAGE** | On failure. |
| **B2B_EDITION**, **B2B_VERSION** | Commerce edition / version. |
| **BROWSER_DEVICE_TYPE**, **OS_VERSION** | Client device. |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP, URI_ID_DERIVED | common |

### 3.43 PackageInstall

Installation, upgrade, or uninstall of a managed/unmanaged package.

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, RUN_TIME, CPU_TIME, URI, SESSION_KEY, LOGIN_KEY | common |
| **OPERATION_TYPE** | `Install`, `Upgrade`, `Uninstall`. |
| **IS_SUCCESSFUL** | `1` / `0`. |
| **IS_PUSH** | `1` if push upgrade. |
| **IS_MANAGED** | `1` for managed packages. |
| **IS_RELEASED** | `1` for released versions (vs beta). |
| **PACKAGE_NAME** | Package name. |
| **FAILURE_TYPE** | Failure reason on `IS_SUCCESSFUL=0`. |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP, URI_ID_DERIVED | common |

### 3.44 PermissionUpdate

A permission was granted / revoked (profile, permission set, custom perm).

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID | common |
| **FEATURE_ID** | The feature / permission Id. |
| **UPDATE_TYPE** | `Add`, `Remove`, `Modify`. |
| **PERMISSION_TYPE** | `Profile`, `PermissionSet`, `PermissionSetGroup`, `CustomPermission`, `Setting`, etc. |
| **CONTEXT** | Where the change was made. |
| **DESCRIPTION** | Human-readable summary. |
| SESSION_KEY, LOGIN_KEY, TIMESTAMP_DERIVED | common |

### 3.45 PlatformEncryption

A Shield Platform Encryption key-management action (tenant secret creation, rotation, export, destroy).

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, RUN_TIME, CPU_TIME, URI, SESSION_KEY, LOGIN_KEY | common |
| **KEY_ID** | Tenant Secret / Key Id. |
| **ACTION** | `Create`, `Rotate`, `Archive`, `Destroy`, `Export`, `Import`, etc. |
| **KEY_TYPE** | `Data`, `EventBus`, `Search`, `Analytics`, etc. |
| **METHOD** | The API/UI path that triggered the action. |
| BOT_ID, BOT_SESSION_ID, PLANNER_ID | common |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP, URI_ID_DERIVED, KEY_ID_DERIVED | common |

### 3.46 QueuedExecution

A Queueable / Future / Batch / Scheduled Apex job was enqueued and ran asynchronously.

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, RUN_TIME, CPU_TIME, URI, SESSION_KEY, LOGIN_KEY, USER_TYPE, REQUEST_STATUS, DB_TOTAL_TIME | common |
| **JOB_ID** | AsyncApexJob Id. |
| **ENTRY_POINT** | Class that ran. |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP, URI_ID_DERIVED | common |

### 3.47 Report

A synchronous report run (small to medium reports).

| Column | Notes |
|---|---|
| Same shape as AsyncReportRun (3.8), minus `DASHBOARD_ID`. | |
| **ORIGIN** | Trigger source. |

### 3.48 ReportExport

A report was exported (CSV / XLSX / printable). A high-signal data-exfiltration indicator.

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, RUN_TIME, CPU_TIME, URI, SESSION_KEY, LOGIN_KEY | common |
| **CLIENT_INFO** | User agent / client info. |
| **REPORT_DESCRIPTION** | Report name (and sometimes folder). |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP, URI_ID_DERIVED | common |

### 3.49 RestApi

A standard REST API call hitting `/services/data/...`. Distinct from `ApexRestApi` (custom Apex endpoints) and `API` (older API event).

| Column | Notes |
|---|---|
| Same column set as ApexRestApi (3.4) — includes METHOD, MEDIA_TYPE, STATUS_CODE, USER_AGENT, ROWS_PROCESSED, NUMBER_FIELDS, REQUEST/RESPONSE_SIZE, ENTITY_NAME, CONNECTED_APP_ID, CLIENT_NAME, EXCEPTION_MESSAGE, QUERY, BOT_ID, BOT_SESSION_ID, PLANNER_ID. | |

### 3.50 SalesforceLoginAs

Salesforce Support engineer used Subscriber Support / "Salesforce LoginAs" to access the org.

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID | common |
| **ACTUAL_USER_ID** | The Support user identity. |
| **OPERATION** | `Login`, `Logout`. |
| **IP_ADDRESS** | Support engineer's IP. |
| **CASE_ID** | The associated support case (when granted via case). |
| TIMESTAMP_DERIVED | common |

### 3.51 Sandbox

Sandbox lifecycle event (creation, refresh, deletion, activation).

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID | common |
| **SANDBOX_ID** | Sandbox Id. |
| ORGANIZATION_ID | common |
| **PENDING_SANDBOX_ORG_ID** | Target org Id pre-activation. |
| **CURRENT_SANDBOX_ORG_ID** | Active sandbox org Id. |
| **STATUS** | `Pending`, `Activating`, `Active`, `Failed`, `Deleting`. |
| USER_ID, TIMESTAMP_DERIVED, USER_ID_DERIVED | common |

### 3.52 Search

A global search was executed.

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID | common |
| **QUERY_ID** | Search query Id (joins to SearchClick). |
| **NUM_RESULTS** | Result count. |
| **SEARCH_QUERY** | Verbatim search text. |
| **PREFIXES_SEARCHED** | Comma-separated 3-char key prefixes searched. |
| TIMESTAMP_DERIVED | common |

### 3.53 SearchClick

A user clicked a result from a Search. Joins to Search via QUERY_ID.

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID | common |
| **QUERY_ID** | The originating Search row. |
| **CLICKED_RECORD_ID** | The record clicked. |
| **RANK** | 1-indexed position in the result list. |
| TIMESTAMP_DERIVED | common |

### 3.54 Sites

A request to an Experience Cloud / Force.com Sites page (public-facing).

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, RUN_TIME, CPU_TIME, URI, SESSION_KEY, LOGIN_KEY, USER_TYPE, REQUEST_STATUS, DB_TOTAL_TIME | common |
| **PAGE_NAME** | Visualforce / Site page name. |
| **REQUEST_TYPE** | Page / asset / api. |
| **IS_FIRST_REQUEST** | `1` if first request of the session. |
| **QUERY** | Query string. |
| **SITE_ID** | Site Id. |
| **IS_SECURE** | `1` if HTTPS. |
| **RESPONSE_SIZE** | Bytes. |
| **IS_GUEST** | `1` if guest user. |
| **IS_API** | `1` if an API hit (not a page). |
| **IS_ERROR** | `1` on error page. |
| **HTTP_METHOD** | Verb. |
| **HTTP_HEADERS** | Truncated headers. |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP, URI_ID_DERIVED | common |

### 3.55 TimeBasedWorkflow

An entry was added to or removed from a time-based workflow queue.

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, RUN_TIME, CPU_TIME, URI, SESSION_KEY, LOGIN_KEY | common |
| **TYPE** | `Add`, `Remove`, `Modify`. |
| **DATA** | Workflow rule identifier / context. |
| **NUMBER_OF_RECORDS** | Records affected. |
| **LOG_GROUP_ID** | Internal grouping Id. |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP, URI_ID_DERIVED | common |

### 3.56 URI

A page-style HTTP request to `*.salesforce.com` (Classic + Lightning chrome).

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, RUN_TIME, CPU_TIME, URI, SESSION_KEY, LOGIN_KEY, USER_TYPE, REQUEST_STATUS, DB_TOTAL_TIME, DB_BLOCKS, DB_CPU_TIME | common |
| **REFERRER_URI** | HTTP Referer. |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP, URI_ID_DERIVED | common |

### 3.57 UiTelemetryNavigationTiming

Browser `PerformanceNavigationTiming` API output for a Lightning page load. One row per navigation.

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID | common |
| **DEVICE_SESSION_ID** | Per-device session. |
| **UI_EVENT_TIMESTAMP** | Browser-side timestamp. |
| **UI_EVENT_RELATIVE_TIMESTAMP** | Offset from page start. |
| **UI_ROOT_ACTIVITY_ID** | Root span Id. |
| USER_TYPE, CLIENT_ID, SESSION_KEY, LOGIN_KEY | common |
| **CLIENT_GEO**, **CONNECTION_TYPE** | Network context. |
| **APP_NAME**, **SDK_APP_VERSION**, **DEVICE_PLATFORM**, **DEVICE_MODEL**, **SDK_VERSION**, **BROWSER_NAME**, **BROWSER_VERSION**, **OS_NAME**, **OS_VERSION** | Client fingerprint. |
| **PAGE_URL**, **PAGE_ENTITY_TYPE**, **PAGE_CONTEXT**, **PAGE_ENTITY_ID**, **SDK_APP_TYPE** | Page identity. |
| **DURATION** | Total navigation duration, ms. |
| **URL** | Resource URL. |
| **START_TIME** | Performance.now() relative start. |
| **INITIATOR_TYPE** | `navigation`, `script`, `link`, etc. |
| **NEXT_HOP_PROTOCOL** | e.g. `h2`. |
| **RENDER_BLOCKING_STATUS** | `blocking` / `non-blocking`. |
| **WORKER_START** | Service-worker start time. |
| **REDIRECT_START** / **REDIRECT_END** | Redirect phase. |
| **FETCH_START**, **DOMAIN_LOOKUP_START/END**, **CONNECT_START/END**, **SECURE_CONNECTION_START**, **REQUEST_START**, **RESPONSE_START**, **FIRST_INTERIM_RESPONSE_START**, **RESPONSE_END** | Full RUM timeline. |
| **TRANSFER_SIZE**, **ENCODED_BODY_SIZE**, **DECODED_BODY_SIZE** | Response sizes. |
| **RESPONSE_STATUS** | HTTP status. |
| **SERVER_REQUEST_ID** | Salesforce-side request Id (joins to URI / API events). |
| **UI_THREAD_RESPONSE_DELAY** | Main-thread response delay. |
| **DOM_COMPLETE**, **DOM_CONTENT_LOADED_EVENT_START/END**, **DOM_INTERACTIVE**, **LOAD_EVENT_START/END** | DOM lifecycle. |
| **REDIRECT_COUNT** | Redirect chain length. |
| **NAVIGATION_TYPE** | `navigate`, `reload`, `back_forward`, `prerender`. |
| **UNLOAD_EVENT_START/END** | Unload phase. |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP | common |

### 3.58 UiTelemetryResourceTiming

Browser `PerformanceResourceTiming` API output for individual sub-resources loaded by a Lightning page.

| Column | Notes |
|---|---|
| Same columns as UiTelemetryNavigationTiming (3.57), minus the DOM lifecycle / load-event / unload columns. One row per sub-resource (script, stylesheet, image, XHR, fetch). | |

### 3.59 UniqueQuery

A deduplicated SOQL query fingerprint. Salesforce hashes SOQL text and emits one of these per unique query observed.

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, USER_ID, SESSION_KEY, LOGIN_KEY, ORGANIZATION_ID | common |
| **SQL_ID** | Internal SQL fingerprint Id. |
| **QUERY_IDENTIFIER** | Salesforce-side query identifier. |
| **QUERY_TYPE** | `SOQL`, `SOSL`, etc. |
| BOT_ID, BOT_SESSION_ID, PLANNER_ID, TIMESTAMP_DERIVED | common |

### 3.60 VisualforceRequest

A page request to a Visualforce page (classic UI / VF in LEX).

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, RUN_TIME, CPU_TIME, URI, SESSION_KEY, LOGIN_KEY, USER_TYPE, REQUEST_STATUS, DB_TOTAL_TIME | common |
| **PAGE_NAME** | Visualforce page. |
| **REQUEST_TYPE** | `page`, `action`, `remote`. |
| **IS_FIRST_REQUEST** | `1` for the initial GET. |
| **QUERY** | URL query string. |
| **HTTP_METHOD** | Verb. |
| **USER_AGENT** | UA. |
| **REQUEST_SIZE**, **RESPONSE_SIZE** | Bytes. |
| **VIEW_STATE_SIZE** | Bytes. |
| **CONTROLLER_TYPE** | `Standard`, `Custom`, `Extension`. |
| **MANAGED_PACKAGE_NAMESPACE** | If the page is from a managed package. |
| **IS_AJAX_REQUEST** | `1` for partial postback. |
| DB_BLOCKS, DB_CPU_TIME | common |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP, URI_ID_DERIVED | common |

### 3.61 WaveChange

CRM Analytics (Wave / Tableau CRM): an asset was changed in the analytics workspace.

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, RUN_TIME, CPU_TIME, URI, SESSION_KEY, LOGIN_KEY | common |
| **WAVE_SESSION_ID** | CRMA session. |
| **WAVE_TIMESTAMP** | CRMA-side timestamp. |
| **TYPE** | Change type (`Create`, `Edit`, `Delete`, `Run`). |
| **RECORD_ID** | The asset Id. |
| **VIEW_MODE** | `Edit`, `View`, etc. |
| **TAB_ID** | Browser tab Id (CRMA-scoped). |
| **PAGE_ID** | Dashboard / lens page Id. |
| **SAVED_VIEW_ID** | Saved view Id. |
| **IS_NEW** | `1` if newly created. |
| **REOPEN_COUNT** | Times reopened in session. |
| **ANALYTICS_MODE** | `Embedded`, `Standalone`. |
| **PAGE_CONTEXT** | Where the asset is embedded. |
| **IS_MOBILE** | `1` if on mobile. |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP, URI_ID_DERIVED | common |

### 3.62 WaveDownload

CRM Analytics: an asset (dataset, dashboard, lens) was downloaded.

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, RUN_TIME, CPU_TIME, URI, SESSION_KEY, LOGIN_KEY | common |
| **WAVE_SESSION_ID**, **WAVE_TIMESTAMP** | CRMA session. |
| **ASSET_ID**, **ASSET_TYPE** | Downloaded asset. |
| **DATASET_IDS** | Source datasets. |
| USER_TYPE | common |
| **DOWNLOAD_FORMAT** | `csv`, `xlsx`, `image`, etc. |
| **NUMBER_OF_RECORDS** | Rows in the export. |
| **DOWNLOAD_ERROR** | Error text on failure. |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP, URI_ID_DERIVED | common |

### 3.63 WaveInteraction

CRM Analytics: a user clicked / filtered / drilled into a dashboard or lens.

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, RUN_TIME, CPU_TIME, URI, SESSION_KEY, LOGIN_KEY | common |
| **WAVE_SESSION_ID**, **WAVE_TIMESTAMP** | CRMA session. |
| **TYPE** | Interaction type. |
| **RECORD_ID** | Asset interacted with. |
| **VIEW_MODE**, **TAB_ID** | UI state. |
| **TOTAL_TIME**, **READ_TIME** | Engagement timing, ms. |
| **NUM_SESSIONS**, **NUM_CLICKS** | Engagement counts. |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP, URI_ID_DERIVED | common |

### 3.64 WavePerformance

CRM Analytics: rendering performance metrics for a dashboard / lens.

| Column | Notes |
|---|---|
| EVENT_TYPE, TIMESTAMP, REQUEST_ID, ORGANIZATION_ID, USER_ID, RUN_TIME, CPU_TIME, URI, SESSION_KEY, LOGIN_KEY | common |
| **WAVE_SESSION_ID**, **WAVE_TIMESTAMP** | CRMA session. |
| **TYPE** | Performance event type. |
| **RECORD_ID** | Asset measured. |
| **VIEW_MODE**, **TAB_ID** | UI state. |
| **NAME** | Named timing phase. |
| **EPT** | Effective Page Time, ms. |
| **IS_INITIAL** | `1` if this is the first render. |
| TIMESTAMP_DERIVED, USER_ID_DERIVED, CLIENT_IP, URI_ID_DERIVED | common |

---

## 4. Notes on cross-event joins

- **REQUEST_ID** is the strongest join key. A single user action can fan out into one URI row, one ApexExecution row, several ApexCallout rows, several DatabaseSave rows, several UniqueQuery rows, and several UiTelemetryResourceTiming rows — all sharing REQUEST_ID.
- **LOGIN_KEY** correlates everything done in one login session (across requests). **SESSION_KEY** is per session token.
- **DEVICE_SESSION_ID** correlates browser activity across navigations within the same browser tab/session for Lightning events.
- **QUERY_ID** joins Search ↔ SearchClick.
- **JOB_ID** joins BulkApi/BulkApi2/BulkApiRequest rows for one Bulk API job; **JOB_ID** in QueuedExecution joins to the `AsyncApexJob` table.
- **WAVE_SESSION_ID** joins the four Wave* events for a single CRMA session.
- Derived columns (`*_DERIVED`) are computed by Salesforce: ISO timestamps, 18-char Ids. Always prefer derived for analysis; raw forms are kept for fidelity to the original Salesforce internal record.

## 5. Caveats

- **Schema drift:** Salesforce adds and very occasionally removes columns each release. Headers here reflect what's on disk today; an older / newer file may differ.
- **DatabaseSave is sampled:** multiply NUM_ROWS by SAMPLE_FACTOR to estimate true row counts.
- **EventLogFile retention:** 30 days on orgs with the Event Monitoring add-on; 1 day without. Files older than that on local disk are local copies only.
- **Hourly vs daily:** some EventTypes (Login, API, BulkApi, BulkApi2, ReportExport, URI) can be downloaded as hourly files in addition to the daily roll-up; the column schema is identical.
- **CLIENT_IP nuance:** for events that pass through a load balancer or proxy, CLIENT_IP may be the proxy; `FORWARDED_FOR_IP` on Login is the most reliable client identifier when available.

---

*Schema reference only. Treat the row-level data in actual EventLogFile downloads as containing user-level activity (identifiers, IP addresses, session tokens, URIs, query text) and govern its handling accordingly.*
