# Salesforce Technical Objects — Schema, Format, and Data-Content Reference

A field-level reference for 40 Salesforce technical objects (system tables, Tooling-API entities, and a pair of REST pseudo-endpoints) that are commonly exported in bulk for org analysis. For each object, this document gives:

- The Salesforce API used to download it (SObject SOQL, Bulk API, Tooling API, or REST pseudo-endpoint).
- The columns observed in the on-disk CSV header for that object.
- For each column: data type and a factual description of what Salesforce stores in it.
- A "Data content to inspect" note where the column content depends on org data (free text, blobs, user identifiers, IPs, etc.). These notes describe **what is in the field**, not a classification verdict.

The intent is to give a reader the facts needed to classify the contents themselves. Where Salesforce supplies a list of picklist values or enumerated states, those are listed verbatim; where a field holds free text or a generated artefact, that is stated.

## Notes on schema and format

- **Column list source:** the headers of one exported CSV per object. The typical extractor pattern (and the one assumed throughout this reference) downloads via the SObject API (SOQL or Bulk) or the Tooling API, and for Tooling-API objects explicitly skips the field types `address`, `location`, `base64`, `complexvalue`, `textarea`, `anyType` and the field names `SymbolTable`, `Metadata`, `Body`, `HtmlValue`, `Content`, `FullName`. So the CSV column lists below are the *queryable, non-skipped* subset, not the complete sObject schema.
- **Field-type vocabulary:** `id` (15- or 18-char Salesforce Id), `reference` (foreign-key Id to another sObject), `picklist`, `string` (free text or short token), `textarea` (long text — note: not downloaded by this tool), `int`/`double`/`currency`, `boolean`, `datetime`, `date`, `email`, `phone`, `url`, `address` (compound — also skipped by this tool).
- **CSV format:** one header row, one record per row, double-quoted text fields, commas as separators, UTF-8 encoding.
- **Common audit columns:** `Id`, `IsDeleted`, `CreatedDate`, `CreatedById`, `LastModifiedDate`, `LastModifiedById`, `SystemModstamp` recur across almost every sObject. They store object provenance and timestamps; their content is org-internal Ids and timestamps.
- **Authoritative references:** Salesforce Platform Object Reference (`https://developer.salesforce.com/docs/atlas.en-us.object_reference.meta/object_reference/`), Salesforce Tooling API Reference (`https://developer.salesforce.com/docs/atlas.en-us.api_tooling.meta/api_tooling/`), Salesforce Platform REST API Reference for the two pseudo-endpoints.

---

## Index

| # | Object | API | Category |
|---|---|---|---|
| 1 | ApexClass | Tooling | Apex tooling |
| 2 | ApexCodeCoverage | Tooling | Apex tooling |
| 3 | ApexCodeCoverageAggregate | Tooling | Apex tooling |
| 4 | ApexExecutionOverlayResult | Tooling | Apex tooling |
| 5 | ApexLog | Tooling | Apex tooling |
| 6 | ApexTestQueueItem | Tooling | Apex tooling |
| 7 | ApexTestResult | Tooling | Apex tooling |
| 8 | ApexTestResultLimits | Tooling | Apex tooling |
| 9 | ApexTestRunResult | Tooling | Apex tooling |
| 10 | AsyncApexJob | SObject (Bulk) | Async / job machinery |
| 11 | AuthSession | SObject (SOQL) | Identity / session |
| 12 | BackgroundOperation | SObject (Bulk) | Async / job machinery |
| 13 | CronJobDetail | SObject (Bulk) | Async / job machinery |
| 14 | CronTrigger | SObject (Bulk) | Async / job machinery |
| 15 | DebugLevel | Tooling | Debug & tracing |
| 16 | EntityDefinition | SObject (SOQL paged) | Schema metadata |
| 17 | EventLogFile | SObject (SOQL) | Event monitoring |
| 18 | FlowInterview | SObject (SOQL) | Flow |
| 19 | Group | SObject (Bulk) | Groups |
| 20 | GroupMember | SObject (Bulk) | Groups |
| 21 | IdpEventLog | SObject (Bulk) | Identity / SSO |
| 22 | LightningUsageByAppTypeMetrics | SObject (Bulk) | Lightning telemetry |
| 23 | LightningUsageByBrowserMetrics | SObject (Bulk) | Lightning telemetry |
| 24 | LightningUsageByFlexiPageMetrics | SObject (Bulk) | Lightning telemetry |
| 25 | LightningUsageByPageMetrics | SObject (Bulk) | Lightning telemetry |
| 26 | LoginGeo | SObject (SOQL) | Identity / geolocation |
| 27 | LoginHistory | SObject (Bulk) | Identity / login |
| 28 | Organization | SObject (SOQL) | Organization |
| 29 | PermissionSet | SObject (Bulk) | Authorization |
| 30 | PermissionSetAssignment | SObject (Bulk) | Authorization |
| 31 | Profile | SObject (Bulk) | Authorization |
| 32 | RecordType | SObject (Bulk) | Schema metadata |
| 33 | SessionPermSetActivation | SObject (Bulk) | Identity / session |
| 34 | SetupAuditTrail | SObject (SOQL) | Audit |
| 35 | TraceFlag | Tooling | Debug & tracing |
| 36 | UserLogin | SObject (SOQL) | Identity / user-state |
| 37 | UserRole | SObject (Bulk) | Authorization |
| 38 | VerificationHistory | SObject (SOQL) | Identity / MFA |
| 39 | limits | REST pseudo-endpoint | Org metrics |
| 40 | recordCount | REST pseudo-endpoint | Org metrics |

---

# Apex tooling

## 1. ApexClass

**API:** Tooling.
**What it represents:** every Apex class definition stored in the org. One row per class.
**Note:** the `Body`, `FullName`, `SymbolTable`, and `Metadata` fields exist on the sObject but are explicitly **excluded** by the downloader, so the on-disk CSV contains class metadata only — not source code.

| Column | Type | What it stores |
|---|---|---|
| Id | id | 15-char Apex class Id (`01p…` key prefix). |
| NamespacePrefix | string | Managed-package namespace if the class is from a managed package; empty for org-local classes. |
| Name | string | Apex class name (developer-chosen identifier). |
| ApiVersion | double | API version the class is bound to (e.g. `61.0`). |
| Status | picklist | `Active`, `Inactive`, `Deleted`. |
| IsValid | boolean | `true` if the class compiles. |
| BodyCrc | double | CRC32 of the source body. A number; the body itself is not present. |
| LengthWithoutComments | int | Source-body length excluding comments, in characters. |
| CreatedDate, CreatedById, LastModifiedDate, LastModifiedById, SystemModstamp | datetime / id | Provenance. |
| ManageableState | picklist | `unmanaged`, `installed`, `released`, `deleted`, `deprecated`, `beta`, `installedEditable`, `deprecatedEditable`. |

**Data content to inspect:** class names. Naming patterns can reveal product or feature names (e.g. `OrderProcessingController`, `InvoiceXMLGenerator`).

## 2. ApexCodeCoverage

**API:** Tooling.
**What it represents:** Apex code coverage from the last full test run, broken down per test method × class/trigger.

| Column | Type | What it stores |
|---|---|---|
| Id | id | Coverage row Id. |
| IsDeleted, CreatedDate, CreatedById, LastModifiedDate, LastModifiedById, SystemModstamp | — | Provenance. |
| ApexTestClassId | reference | Apex class Id of the test class. |
| TestMethodName | string | Test-method name. |
| ApexClassOrTriggerId | reference | Id of the class or trigger that was covered. |
| NumLinesCovered | int | Count of executable lines covered. |
| NumLinesUncovered | int | Count of executable lines not covered. |

**Data content to inspect:** test-method names. These often encode feature intent (e.g. `testRefundsForCancelledOrders`).

## 3. ApexCodeCoverageAggregate

**API:** Tooling.
**What it represents:** the aggregate (latest) code coverage per class/trigger, summed across all tests.

| Column | Type | What it stores |
|---|---|---|
| Id, IsDeleted, CreatedDate, CreatedById, LastModifiedDate, LastModifiedById, SystemModstamp | — | Provenance. |
| ApexClassOrTriggerId | reference | The class or trigger Id. |
| NumLinesCovered, NumLinesUncovered | int | Aggregate line counts. |
| CoverageLastModifiedDate | datetime | When coverage was last recomputed. |

**Data content to inspect:** numeric only; class Ids reference org-local Apex.

## 4. ApexExecutionOverlayResult

**API:** Tooling.
**What it represents:** the result of an Apex execution-overlay action set by a developer in the Developer Console (heap dump or Apex snippet executed when a checkpoint fires).
**Note:** the heap-dump payload itself lives in a separate object (`ApexExecutionOverlayAction.HeapDump`); this row records the *result metadata*. The downloader skips the `ActionScript` body field where applicable.

| Column | Type | What it stores |
|---|---|---|
| Id, IsDeleted, CreatedDate, CreatedById, LastModifiedDate, LastModifiedById, SystemModstamp | — | Provenance. |
| UserId | reference | User in whose context the overlay fired. |
| RequestedById | reference | Developer who set the overlay action. |
| OverlayResultLength | int | Length of the captured result. |
| Line | int | Source line in the target class. |
| Iteration | int | Iteration count at firing. |
| ExpirationDate | datetime | When the result expires. |
| IsDumpingHeap | boolean | `true` if the action captures a heap dump. |
| ActionScriptType | picklist | `None`, `Apex`, `SOQL`. |
| ClassName | string | Apex class targeted. |
| Namespace | string | Namespace of the class. |

**Data content to inspect:** developer/user identifiers; class names. The actual captured heap or Apex result lives in another object and is not in this CSV.

## 5. ApexLog

**API:** Tooling.
**What it represents:** debug-log headers for Apex transactions captured under a TraceFlag.
**Note:** the log body (`Body` field) is on a separate REST endpoint (`/services/data/vXX.X/tooling/sobjects/ApexLog/{id}/Body`) and is **not** in this CSV — this row carries the header only.

| Column | Type | What it stores |
|---|---|---|
| Id | id | Log Id (`07L…`). |
| LogUserId | reference | User whose activity produced the log. |
| LogLength | int | Body length in bytes. |
| LastModifiedDate, SystemModstamp | datetime | Provenance. |
| Request | picklist | `API`, `Application`. |
| Operation | string | URL path / Apex entry point that triggered the request (e.g. `/apex/MyPage`, `/services/Soap/u/61.0`, `MyClass.myMethod`). |
| Application | string | The app that ran the transaction (e.g. `Browser`, `Unknown`, `sfdx`). |
| Status | string | Free-text terminal status (e.g. `Success`, fault message text). |
| DurationMilliseconds | int | Total transaction duration. |
| StartTime | datetime | Transaction start. |
| Location | picklist | `SystemLog`, `MonitoringTraceFlag`, `HeapDump`. |
| RequestIdentifier | string | Salesforce request identifier (joins to other monitoring rows). |

**Data content to inspect:** `Operation` and `Status` are free text and can contain class/method names, page names, and fault messages. `LogUserId` ties the log to a real user.

## 6. ApexTestQueueItem

**API:** Tooling.
**What it represents:** queued items in the asynchronous Apex test queue.
*(Not always present in on-disk samples — the queue is transient.)*

Documented fields (per Tooling API reference):

| Column | Type | What it stores |
|---|---|---|
| Id | id | Queue item Id. |
| ParentJobId | reference | The `AsyncApexJob` for the test run. |
| ApexClassId | reference | Test class. |
| Status | picklist | `Holding`, `Queued`, `Preparing`, `Processing`, `Aborted`, `Completed`, `Failed`. |
| ExtendedStatus | string | Free-text status, e.g. an error message. |
| ShouldSkipCodeCoverage | boolean | Coverage-collection flag. |
| TestRunResultId | reference | `ApexTestRunResult` produced. |

**Data content to inspect:** test-class identifiers and any free text in `ExtendedStatus`.

## 7. ApexTestResult

**API:** Tooling.
**What it represents:** one row per Apex test method execution.

| Column | Type | What it stores |
|---|---|---|
| Id | id | Result Id. |
| SystemModstamp, TestTimestamp | datetime | When run / last modified. |
| Outcome | picklist | `Pass`, `Fail`, `CompileFail`, `Skip`. |
| ApexClassId | reference | Test class. |
| MethodName | string | Test method name. |
| Message | string | Failure message, if any (free text). |
| StackTrace | string | Apex stack trace text, if failed. |
| AsyncApexJobId | reference | Container job. |
| QueueItemId | reference | `ApexTestQueueItem` parent. |
| ApexLogId | reference | Linked `ApexLog`. |
| ApexTestRunResultId | reference | Container test-run-result. |
| RunTime | int | Method duration in ms. |

**Data content to inspect:** `Message` and `StackTrace` are free text; if a test asserts on customer data (e.g. expected name strings), those strings can appear here.

## 8. ApexTestResultLimits

**API:** Tooling.
**What it represents:** governor-limit usage snapshot per test method.

| Column | Type | What it stores |
|---|---|---|
| Id, IsDeleted, CreatedDate, CreatedById, LastModifiedDate, LastModifiedById, SystemModstamp | — | Provenance. |
| ApexTestResultId | reference | The test result this snapshot relates to. |
| Soql | int | SOQL queries used. |
| QueryRows | int | Rows returned. |
| Sosl | int | SOSL queries. |
| Dml | int | DML statements. |
| DmlRows | int | Rows DMLed. |
| Cpu | int | CPU time, ms. |
| Callouts | int | Callout count. |
| Email | int | Single email sends. |
| AsyncCalls | int | Async invocations. |
| MobilePush | int | Mobile-push notifications. |
| LimitContext | picklist | `Synchronous`, `Asynchronous`. |
| LimitExceptions | string | Free-text governor-limit exception text, if any. |

**Data content to inspect:** numeric; `LimitExceptions` is free text but typically reports limit names.

## 9. ApexTestRunResult

**API:** Tooling.
**What it represents:** the container for one entire Apex test run (covers many `ApexTestResult` rows).

| Column | Type | What it stores |
|---|---|---|
| Id, IsDeleted, CreatedDate, CreatedById, LastModifiedDate, LastModifiedById, SystemModstamp | — | Provenance. |
| AsyncApexJobId | reference | Backing AsyncApexJob. |
| UserId | reference | User that triggered the run. |
| JobName | string | Free-text job name (often the developer-supplied label). |
| IsAllTests | boolean | `true` if "Run All Tests" was used. |
| Source | string | Free text identifying who/what kicked off the run (e.g. `UI`, `Toolingapi`, `sfdx`, deployment client name). |
| StartTime, EndTime | datetime | Window. |
| TestTime | int | Duration in ms. |
| Status | picklist | `Queued`, `Processing`, `Aborted`, `Completed`, `Failed`. |
| ClassesEnqueued, ClassesCompleted, MethodsEnqueued, MethodsCompleted, MethodsFailed | int | Counts. |

**Data content to inspect:** `JobName` and `Source` are free text and may reveal automation tool names or CI job identifiers.

---

# Async / job machinery

## 10. AsyncApexJob

**API:** SObject (Bulk-supported per metadata file).
**What it represents:** the asynchronous Apex execution queue — `@future`, Queueable, Batchable, Scheduled, and the test-run jobs.

| Column | Type | What it stores |
|---|---|---|
| Id | id | Job Id (`707…`). |
| CreatedDate, CreatedById | datetime / id | Provenance and the user who enqueued the job. |
| JobType | picklist | `Future`, `Queueable`, `BatchApex`, `BatchApexWorker`, `ScheduledApex`, `ApexToken`, `TestRequest`, `TestWorker`, `SharingRecalculation`, plus several internal types. |
| ApexClassId | reference | Class being executed. |
| Status | picklist | `Queued`, `Holding`, `Preparing`, `Processing`, `Aborted`, `Completed`, `Failed`. |
| JobItemsProcessed | int | Items processed so far. |
| TotalJobItems | int | Total items planned. |
| NumberOfErrors | int | Error count. |
| CompletedDate | datetime | When job terminated. |
| MethodName | string | For `@future`, the method invoked. |
| ExtendedStatus | string | Free-text status / error message. |
| ParentJobId | reference | Parent batch / chained job. |
| LastProcessed, LastProcessedOffset | string / int | Batch checkpoint pointer. |
| CronTriggerId | reference | If launched on a schedule, the `CronTrigger`. |

**Data content to inspect:** `ExtendedStatus` is free text and can carry exception messages including string values from the data being processed.

## 12. BackgroundOperation

**API:** SObject (Bulk-supported).
**What it represents:** Platform Event / Change Data Capture background processing operations.

| Column | Type | What it stores |
|---|---|---|
| Id, IsDeleted, Name, CreatedDate, CreatedById, LastModifiedDate, LastModifiedById, SystemModstamp | — | Provenance. |
| SubmittedAt, StartedAt, FinishedAt, ExpiresAt, ProcessAfter | datetime | Lifecycle timestamps. |
| Status | picklist | `Queued`, `Holding`, `Running`, `Complete`, `Failed`, `Stuck`, `Cancelled`, plus internal states. |
| ExecutionGroup, SequenceGroup, SequenceNumber | string / int | Grouping for ordered processing. |
| GroupLeaderId | reference | Leader operation in the group. |
| WorkerUri | string | Internal URI of the worker that picked the operation up. |
| Timeout | int | Seconds. |
| NumFollowers | int | Count. |
| ParentKey | string | Parent correlation key (developer-supplied). |
| RetryLimit, RetryCount | int | Retry policy. |
| RetryBackoff | int | Backoff in seconds. |
| Error | string | Free-text error message. |
| Type | picklist | Salesforce-defined operation type (e.g. `PlatformEvent`, `AsyncTrigger`). |

**Data content to inspect:** `Error`, `Name`, and `ParentKey` are free text and can carry developer-defined keys or messages including data values when an error surfaces them.

## 13. CronJobDetail

**API:** SObject (Bulk-supported).
**What it represents:** the *name and type* of every scheduled job in the org.

| Column | Type | What it stores |
|---|---|---|
| Id | id | Detail row Id. |
| Name | string | Developer- or admin-supplied schedule name. |
| JobType | picklist | `Scheduled Apex` (`7`), `Reporting Snapshot` (`8`), `Dashboard Refresh` (`3`), `Analytic Snapshot` (`4`), `Auto Response Rules` (`B`), `Batch Job` (`A`), plus other single-character codes documented in the reference. |

**Data content to inspect:** `Name` is free text — admins often encode purpose (e.g. `Nightly_AR_Aging_Sync`).

## 14. CronTrigger

**API:** SObject (Bulk-supported).
**What it represents:** scheduled-job triggers (the cron-style scheduler entries).

| Column | Type | What it stores |
|---|---|---|
| Id | id | Trigger Id. |
| CronJobDetailId | reference | The CronJobDetail describing the job. |
| NextFireTime, PreviousFireTime | datetime | Schedule. |
| State | picklist | `WAITING`, `ACQUIRED`, `EXECUTING`, `COMPLETE`, `ERROR`, `DELETED`, `PAUSED`, `PAUSED_BLOCKED`, `BLOCKED`. |
| StartTime, EndTime | datetime | Window. |
| CronExpression | string | Cron string in Salesforce's seven-field format. |
| TimeZoneSidKey | string | TZ id (e.g. `Europe/London`). |
| OwnerId | reference | User the job runs as. |
| LastModifiedById, CreatedById, CreatedDate | id / datetime | Provenance. |
| TimesTriggered | int | Total fires to date. |

**Data content to inspect:** owner Ids, cron expressions, time zones. No free-text payload beyond `CronExpression`.

---

# Debug & tracing

## 15. DebugLevel

**API:** Tooling.
**What it represents:** debug-logging level definitions (used by `TraceFlag`).

| Column | Type | What it stores |
|---|---|---|
| Id, IsDeleted, CreatedDate, CreatedById, LastModifiedDate, LastModifiedById, SystemModstamp | — | Provenance. |
| DeveloperName | string | Developer-name of the level. |
| Language | string | Locale. |
| MasterLabel | string | Display label. |
| Workflow, Validation, Callout, ApexCode, ApexProfiling, Visualforce, System, Database, Wave, Nba | picklist | Per-category log level: `NONE`, `ERROR`, `WARN`, `INFO`, `DEBUG`, `FINE`, `FINER`, `FINEST`. |

**Data content to inspect:** developer-chosen names and labels.

## 35. TraceFlag

**API:** Tooling.
**What it represents:** active debug-log traces — which user/class/trigger to capture logs for, when, and at what level.

| Column | Type | What it stores |
|---|---|---|
| Id, IsDeleted, CreatedDate, CreatedById, LastModifiedDate, LastModifiedById, SystemModstamp | — | Provenance. |
| TracedEntityId | reference | The entity being traced (user, class, trigger). |
| ExpirationDate | datetime | When the trace stops. |
| Workflow, Validation, Callout, ApexCode, ApexProfiling, Visualforce, System, Database, Wave, Nba | picklist | Per-category overrides on top of the DebugLevel. |
| DebugLevelId | reference | The DebugLevel applied. |
| LogType | picklist | `USER_DEBUG`, `CLASS_TRACING`, `DEVELOPER_LOG`, `PROFILING`, `PROFILING_DEBUG`. |
| StartDate | datetime | Trace start. |

**Data content to inspect:** `TracedEntityId` reveals which user identities or Apex classes are under active observation; correlate with ApexLog if log capture is in scope.

---

# Schema metadata

## 16. EntityDefinition

**API:** SObject (SOQL, paged on `QualifiedApiName`).
**What it represents:** every sObject visible to the API user, custom or standard. The downloader uses a custom paged SOQL because `EntityDefinition` does not support `queryMore`.

| Column | Type | What it stores |
|---|---|---|
| Id | id | Definition Id. |
| DurableId | string | Stable cross-deploy Id of the entity. |
| LastModifiedDate, LastModifiedById | datetime / id | Provenance of the definition. |
| QualifiedApiName | string | API name including namespace (e.g. `npsp__Allocation__c`). |
| NamespacePrefix | string | Namespace. |
| DeveloperName | string | Developer name (without namespace). |
| MasterLabel, Label, PluralLabel | string | Display labels (localised). |
| DefaultCompactLayoutId | reference | Default compact layout. |
| IsCustomizable, IsApexTriggerable, IsWorkflowEnabled, IsProcessEnabled, IsCompactLayoutable, IsCustomSetting, IsDeprecatedAndHidden, IsReplicateable, IsRetrieveable, IsSearchLayoutable, IsSearchable, IsTriggerable, IsIdEnabled, IsEverCreatable, IsEverUpdatable, IsEverDeletable, IsFeedEnabled, IsQueryable, IsMruEnabled, IsLayoutable, IsAutoActivityCaptureEnabled, IsInterface, IsSubtype | boolean | Capability bits. |
| DeploymentStatus | picklist | `InDevelopment`, `Deployed`. |
| KeyPrefix | string | 3-char Id prefix. |
| DetailUrl, EditUrl, NewUrl, EditDefinitionUrl, HelpSettingPageName, HelpSettingPageUrl | url / string | Setup URLs and help pointers. |
| RunningUserEntityAccessId | reference | Joins to access info for the running user. |
| PublisherId | string | Salesforce-internal publisher. |
| RecordTypesSupported | string | Encoded list of supported record-type Ids. |
| InternalSharingModel, ExternalSharingModel | picklist | `Private`, `Read`, `ReadWrite`, `ReadWriteTransfer`, `FullAccess`, `ControlledByParent`, `ControlledByCampaign`, `ControlledByLeadOrContact`. |
| HasSubtypes, ImplementsInterfaces, ImplementedBy, ExtendsInterfaces, ExtendedBy, DefaultImplementation | string | Inheritance / polymorphism metadata. |

**Data content to inspect:** all custom-object names and their labels. Custom field names are *not* here (use `FieldDefinition` for that). Label and API-name patterns can reveal business domain (Customer, Contract, Payment, Patient, etc.).

## 32. RecordType

**API:** SObject (Bulk-supported).
**What it represents:** record types per object (variant of an sObject with its own page layout / picklist values / business process).

| Column | Type | What it stores |
|---|---|---|
| Id | id | RecordType Id. |
| Name | string | Display name. |
| DeveloperName | string | API name. |
| NamespacePrefix | string | Managed-package namespace. |
| Description | string | Free-text description (admin-supplied). |
| BusinessProcessId | reference | Linked BusinessProcess (Lead/Opportunity/Case sales/support process). |
| SobjectType | picklist | The sObject this record type belongs to. |
| IsActive | boolean | Active flag. |
| CreatedById, CreatedDate, LastModifiedById, LastModifiedDate, SystemModstamp | — | Provenance. |

**Data content to inspect:** `Description` is admin-supplied free text. Names can reveal business segmentation.

---

# Identity, session, login

## 11. AuthSession

**API:** SObject (SOQL).
**What it represents:** authenticated sessions currently or recently active in the org. **Active sessions only by default** — Salesforce evicts ended sessions.

| Column | Type | What it stores |
|---|---|---|
| Id | id | Session Id (Salesforce-internal — not the session cookie). |
| UsersId | reference | The user (note the field name has the trailing `s`). |
| CreatedDate, LastModifiedDate | datetime | Session window. |
| NumSecondsValid | int | Seconds of validity left at creation. |
| UserType | picklist | `Standard`, `Guest`, `CustomerPortal`, `CustomerSuccess`, `CSPLitePortal`, `PowerCustomerSuccess`, `PowerPartner`, `Partner`, `CsnOnly`, plus internal types. |
| SourceIp | string | Source IP address of the request that created the session. IPv4 dotted-quad or IPv6 string. |
| LoginType | picklist | Same vocabulary as `LoginHistory.LoginType` — `Application`, `RemoteAccess20`, `SAML`, `OAuthRefresh`, `Partner`, `Application Server`, `LoginAs`, `MyDomain`, `SocialSignOn`, `External`, `OauthExternalApp`, plus others. |
| SessionType | picklist | `UI`, `API`, `Visualforce`, `Content`, `ChatterNetworks`, `OauthApprovalUI`, `OauthClient`, `SitePreview`, `SiteStudio`, `SubstituteUser`, `TempContentExchange`, `TempUIFrontdoor`, `TempVisualforceExchange`, `WDC_API`. |
| SessionSecurityLevel | picklist | `STANDARD`, `HIGH_ASSURANCE`. |
| LogoutUrl | url | Configured logout URL for the session. |
| ParentId | reference | Parent session if substituted. |
| LoginHistoryId | reference | Join key to `LoginHistory`. |
| LoginGeoId | reference | Join key to `LoginGeo`. |
| IsCurrent | boolean | Whether this is the caller's current session. |

**Data content to inspect:** every row identifies a real user (`UsersId`) and the public IP that authenticated them (`SourceIp`). The `LogoutUrl` may contain customer-domain URLs configured in the org.

## 21. IdpEventLog

**API:** SObject (Bulk-supported).
**What it represents:** SSO / federated authentication events when the Salesforce org acts as an Identity Provider (e.g. SAML to a service provider, OIDC flows).

| Column | Type | What it stores |
|---|---|---|
| Id | id | Log row Id. |
| InitiatedBy | picklist | `IDP`, `SP` (who started the flow). |
| Timestamp | datetime | Event time. |
| ErrorCode | string | Error code if the event failed (free text from the protocol). |
| SamlEntityUrl | url | SAML EntityID URL of the relying party. |
| UserId | reference | Salesforce user authenticated. |
| AuthSessionId | reference | Resulting session, if any. |
| SsoType | picklist | `SAML_IDP`, `SAML_SP`, `OPENID_CONNECT`, etc. |
| AppId | reference | The connected app / service-provider configuration. |
| IdentityUsed | string | The federation identifier sent (e.g. federation ID, email used as NameID). Often a user-identifying string used by the SP. |
| OptionsHasLogoutUrl | boolean | Logout-URL configuration flag. |

**Data content to inspect:** `IdentityUsed` can be a federation Id, username, or email used in the assertion. `SamlEntityUrl` is the target SP URL. Both reveal which downstream systems the org federates with.

**Retention:** IdpEventLog rows are retained for **30 days**.

## 26. LoginGeo

**API:** SObject (SOQL).
**What it represents:** geolocation derived from each login's IP (one row per login; joined to LoginHistory).

| Column | Type | What it stores |
|---|---|---|
| Id | id | LoginGeo row Id. |
| CreatedDate, CreatedById, LastModifiedById, LastModifiedDate, IsDeleted, SystemModstamp | — | Provenance. |
| LoginTime | datetime | Login event time. |
| CountryIso | string | 2-letter ISO country code. |
| Country | string | Country name. |
| Latitude | double | IP-derived latitude. |
| Longitude | double | IP-derived longitude. |
| City | string | City name (IP-derived; can be imprecise). |
| PostalCode | string | Postcode (IP-derived). |
| Subdivision | string | State / province / subdivision. |

**Data content to inspect:** every row pinpoints where a real user logged in from. Lat/lon and postcode resolution is IP-based — accuracy is at city/postcode level rather than premises level.

## 27. LoginHistory

**API:** SObject (Bulk-supported, REST-queryable).
**What it represents:** every login attempt (success and failure) for the org.

| Column | Type | What it stores |
|---|---|---|
| Id | id | LoginHistory row Id. |
| UserId | reference | The user that attempted to log in (15-char). |
| LoginTime | datetime | Login time. |
| LoginType | picklist | `Application`, `RemoteAccess20`, `SAML`, `Application Server`, `Partner`, `LoginAs`, `MyDomain`, `OAuthRefresh`, `SocialSignOn`, `External`, `Guest`, `OauthExternalApp`, plus others. |
| SourceIp | string | Public IP of the client. |
| LoginUrl | string | The MyDomain or org login host hit (e.g. `mydomain.my.salesforce.com`). |
| NetworkId | reference | If logging into an Experience Cloud site, the Network Id. |
| AuthenticationServiceId | reference | Auth provider used. |
| LoginGeoId | reference | Joined LoginGeo row. |
| TlsProtocol | string | TLS version negotiated (e.g. `TLS 1.3`). |
| CipherSuite | string | TLS cipher suite. |
| OptionsIsGet, OptionsIsPost | boolean | HTTP method bits. |
| Browser | string | Browser name. |
| Platform | string | OS / platform string. |
| Status | string | `Success`, or free-text failure reason (e.g. `Invalid Password`, `Restricted IP`). |
| Application | string | Calling application name (e.g. `Browser`, `sfdx`, `Workbench`, a managed-package client). |
| ClientVersion | string | Client version string. |
| ApiType | string | If API login, the API family. |
| ApiVersion | string | API version. |
| CountryIso | string | 2-letter country code. |
| AuthMethodReference | string | OIDC `amr` — authenticator method (`pwd`, `mfa`, `swk`, `hwk`, `sms`, `mca`, etc.). |
| LoginSubType | string | Finer-grained login sub-classification (e.g. `OAuth Refresh Token`, `OAuth Bearer Token`). |

**Data content to inspect:** each row pairs a user identity with a public IP, a TLS fingerprint, a UA fingerprint, and a country. `Status` on failures can contain reason strings that include the attempted username.

**Retention:** LoginHistory retains the **last 6 months** of logins (per Salesforce documented limit).

## 33. SessionPermSetActivation

**API:** SObject (Bulk-supported).
**What it represents:** session-scoped permission-set activations (a permission set with `HasActivationRequired=true` that has been activated for the current session).

| Column | Type | What it stores |
|---|---|---|
| Id | id | Row Id. |
| IsDeleted, CreatedDate, CreatedById, LastModifiedDate, LastModifiedById, SystemModstamp | — | Provenance. |
| AuthSessionId | reference | The session. |
| PermissionSetId | reference | The activated permission set. |
| UserId | reference | The user. |
| Description | string | Free text. |
| PermissionSetGroupId | reference | If activated via a permission-set group. |

**Data content to inspect:** which users elevated privileges and when. `Description` is free text.

## 36. UserLogin

**API:** SObject (SOQL).
**What it represents:** per-user login-state flags (account-level — not per-login events).

| Column | Type | What it stores |
|---|---|---|
| Id | id | UserLogin row Id. |
| UserId | reference | The user. |
| IsFrozen | boolean | `true` if the user account is frozen. |
| IsPasswordLocked | boolean | `true` if the password is locked due to failed-login policy. |
| LastModifiedDate, LastModifiedById | datetime / id | Last state change. |

**Data content to inspect:** ties user identities to current freeze/lock state.

## 38. VerificationHistory

**API:** SObject (SOQL).
**What it represents:** identity-verification events (MFA challenges, device activations, password resets, identity confirmations).

| Column | Type | What it stores |
|---|---|---|
| Id | id | Row Id. |
| EventGroup | string | Verification event group identifier. |
| VerificationTime | datetime | When the verification happened. |
| VerificationMethod | picklist | `U2F`, `WebAuthn`, `Salesforce Authenticator`, `One-Time Password Generator`, `Email`, `SMS`, `Phone`, `Temporary Code`, `Password`, etc. |
| UserId | reference | The user verified. |
| Activity | picklist | What triggered the challenge — `Login`, `Identity Verification`, `Two-Factor Auth Setup`, `Password Reset`, etc. |
| Status | picklist | `Success`, `Failure`. |
| LoginHistoryId | reference | Linked login event, if any. |
| SourceIp | string | Public IP at verification. |
| LoginGeoId | reference | Linked LoginGeo row. |
| Remarks | string | Free-text comments (admin-visible). |
| ResourceId | string | The resource (e.g. specific authenticator device id, recovery code id). |
| Policy | string | Verification policy name applied. |
| CreatedDate, CreatedById, LastModifiedById, LastModifiedDate, IsDeleted, SystemModstamp | — | Provenance. |

**Data content to inspect:** each row pairs a user with a verification factor used and the source IP. `Remarks` can be free text from admins. `ResourceId` may include device identifiers.

---

# Groups

## 19. Group

**API:** SObject (Bulk-supported).
**What it represents:** Public Groups, Queues, Role groups, and other Salesforce sharing groups.

| Column | Type | What it stores |
|---|---|---|
| Id | id | Group Id (`00G…`). |
| Name | string | Display name. |
| DeveloperName | string | API name. |
| RelatedId | reference | For Queues, the linked queue; for Role groups, the role; etc. |
| Type | picklist | `Regular`, `Queue`, `Role`, `RoleAndSubordinates`, `RoleAndSubordinatesInternal`, `Organization`, `PRMOrganization`, `AllCustomerPortal`. |
| Email | email | Email address (for Queues used as case email targets). |
| OwnerId | reference | Owner. |
| DoesSendEmailToMembers | boolean | Queue-email flag. |
| DoesIncludeBosses | boolean | Role hierarchy flag. |
| CreatedDate, CreatedById, LastModifiedDate, LastModifiedById, SystemModstamp | — | Provenance. |

**Data content to inspect:** `Email` can contain a working-context mailbox address; `Name` reveals organisational structure (teams, regions, queues).

## 20. GroupMember

**API:** SObject (Bulk-supported).
**What it represents:** the membership join between Groups and Users (or other Groups).

| Column | Type | What it stores |
|---|---|---|
| Id | id | Membership row Id. |
| GroupId | reference | Group. |
| UserOrGroupId | reference | User or Group that is a member. |
| SystemModstamp | datetime | Last modification. |

**Data content to inspect:** the full who-is-in-which-group map for the org. Volume scales with user count.

## 37. UserRole

**API:** SObject (Bulk-supported).
**What it represents:** the role hierarchy (a tree of roles used for sharing).

| Column | Type | What it stores |
|---|---|---|
| Id | id | Role Id (`00E…`). |
| Name | string | Role display name. |
| ParentRoleId | reference | Parent in hierarchy. |
| RollupDescription | string | Forecast rollup description (free text). |
| OpportunityAccessForAccountOwner, CaseAccessForAccountOwner, ContactAccessForAccountOwner | picklist | Implicit-access settings: `None`, `Read`, `Edit`, `ReadWriteTransfer`. |
| ForecastUserId | reference | User receiving forecasts. |
| MayForecastManagerShare | boolean | Forecast-sharing flag. |
| LastModifiedDate, LastModifiedById, SystemModstamp | — | Provenance. |
| DeveloperName | string | API name of the role. |
| PortalAccountId, PortalAccountOwnerId | reference | If this is a Partner / Customer portal role, the linked account. |
| PortalType | picklist | `None`, `CustomerPortal`, `PartnerPortal`. |
| PortalRole | string | Portal role classification. |

**Data content to inspect:** role names and the hierarchy reveal organisation structure and reporting lines.

---

# Authorization

## 29. PermissionSet

**API:** SObject (Bulk-supported).
**What it represents:** every permission set in the org, including system permission sets and the implicit permission sets that back Profiles. ~500 boolean `PermissionsXxx` columns plus structural columns.

| Structural columns | Type | What it stores |
|---|---|---|
| Id | id | Permission Set Id. |
| Name, Label | string | API name and display label. |
| LicenseId | reference | The associated `UserLicense` if license-scoped. |
| ProfileId | reference | Set only if the permission set backs a Profile (`IsOwnedByProfile=true`). |
| IsOwnedByProfile | boolean | `true` for profile-backed permission sets. |
| IsCustom | boolean | `true` if admin-created (vs Salesforce-provided). |
| Description | string | Free text. |
| CreatedDate, CreatedById, LastModifiedDate, LastModifiedById, SystemModstamp | — | Provenance. |
| NamespacePrefix | string | Managed-package namespace. |
| HasActivationRequired | boolean | If activation per session is required. |
| PermissionSetGroupId | reference | If part of a permission-set group. |
| Type | picklist | `Regular`, `Session`, `Standard`, `Group`. |

| Permissions columns (~500) | Type | What they store |
|---|---|---|
| `PermissionsEmailSingle`, `PermissionsModifyAllData`, `PermissionsViewAllData`, `PermissionsManageUsers`, `PermissionsExportReport`, `PermissionsApiEnabled`, `PermissionsBulkApiHardDelete`, `PermissionsViewSetup`, `PermissionsManageSandboxes`, `PermissionsViewEncryptedData`, `PermissionsViewEventLogFiles`, `PermissionsViewClientSecret`, `PermissionsViewHealthCheck`, `PermissionsManageHealthCheck`, `PermissionsAuthorApex`, `PermissionsDebugApex`, `PermissionsViewUserPII`, `PermissionsManageNamedCredentials`, `PermissionsManageIpAddresses`, `PermissionsManagePasswordPolicies`, `PermissionsManageProfilesPermissionsets`, … (full list per `PermissionSet` reference) | boolean | Each is a discrete permission bit; `true` = granted by this permission set. |

**Data content to inspect:** which permissions exist and which permission sets carry the high-privilege bits (`ModifyAllData`, `ViewAllData`, `ManageUsers`, `ManageSandboxes`, `ViewEncryptedData`, `ViewUserPII`, `BulkApiHardDelete`, etc.). The column list itself is metadata; the contents (which permission set has which bit) describe the org's privilege topology.

## 30. PermissionSetAssignment

**API:** SObject (Bulk-supported).
**What it represents:** the join between users and permission sets / permission-set groups.

| Column | Type | What it stores |
|---|---|---|
| Id | id | Assignment Id. |
| PermissionSetId | reference | The permission set. |
| PermissionSetGroupId | reference | The permission-set group (if assigned via a group). |
| AssigneeId | reference | The user. |
| SystemModstamp | datetime | Last modification. |
| ExpirationDate | datetime | Optional expiry. |
| IsActive | boolean | Active flag. |
| IsRevoked | boolean | Revocation flag. |

**Data content to inspect:** the complete map of *which user has which elevated permission set*. Scales with user count × assignments.

## 31. Profile

**API:** SObject (Bulk-supported per metadata file — note Profile is documented as both SObject and Tooling).
**What it represents:** every Profile in the org. Same wide schema as `PermissionSet` for the permissions columns, plus Profile-specific structural columns.

| Distinctive columns | Type | What it stores |
|---|---|---|
| Id | id | Profile Id (`00e…`). |
| Name | string | Profile name. |
| UserLicenseId | reference | Backing user license. |
| UserType | picklist | `Standard`, `PowerPartner`, `CustomerSuccess`, `Guest`, `CsnOnly`, etc. |
| Description | string | Free text. |
| LastViewedDate, LastReferencedDate | datetime | UI usage stats. |
| (plus ~500 `PermissionsXxx` boolean columns identical to PermissionSet) | boolean | Permission bits granted by the Profile. |

**Data content to inspect:** profile names (often reveal job functions: `System Administrator`, `Sales Operations`, `Finance Read-Only`) and which profiles carry the high-privilege bits. The Profile's permissions form the *base* of every assigned user's effective privilege.

## 25. (No object 25 in this section — see Lightning telemetry)

---

# Audit

## 34. SetupAuditTrail

**API:** SObject (SOQL).
**What it represents:** the org's Setup audit log — every administrative change made in Setup, plus selected system events.

| Column | Type | What it stores |
|---|---|---|
| Id | id | Audit row Id. |
| Action | string | Salesforce-defined action token (e.g. `changedProfile`, `PermSetAssign`, `loginAsGrantedToPartnerBT`, `deleteCustomField`). |
| Section | string | Setup section the action occurred in (`Manage Users`, `Customize Accounts`, `Apex Class`, `Connected Apps`, `Security Controls`, etc.). |
| CreatedDate, CreatedById | datetime / id | When and by whom. |
| SystemModstamp | datetime | Last modification. |
| Display | string | Free-text human-readable description of the change. May embed the names of fields, users, classes, profiles, picklist values, etc. that were modified. |
| DelegateUser | string | If the change was performed by a delegated administrator, identifies them. |
| ResponsibleNamespacePrefix | string | Namespace of the package responsible, if the change came from a managed package install. |
| CreatedByContext | string | Context (e.g. `Apex`, `UI`, `API`, `MetadataAPI`). |
| CreatedByIssuer | string | The OAuth client or issuer behind the change. |

**Data content to inspect:** `Display` is the high-information field — it is free text describing each change and frequently embeds field names, picklist labels, user names/usernames, profile names, and other org-internal identifiers.

**Retention:** SetupAuditTrail rows are retained for **180 days**.

---

# Flow

## 18. FlowInterview

**API:** SObject (SOQL).
**What it represents:** in-progress or paused Flow interviews (instances of a running Flow that have not yet completed).

| Column | Type | What it stores |
|---|---|---|
| Id | id | Interview Id. |
| OwnerId | reference | Interview owner. |
| IsDeleted | boolean | Soft-delete flag. |
| Name | string | System-supplied name (often `Interview-{Id}`). |
| CreatedDate, CreatedById, LastModifiedDate, LastModifiedById, SystemModstamp | — | Provenance. |
| CurrentElement | string | The Flow element currently waiting (developer-named, e.g. `Screen_CustomerDetails`). |
| InterviewLabel | string | Admin- or developer-supplied interview label. May embed merge-field values from the running flow context. |
| PauseLabel | string | The label the user chose when pausing. |
| Guid | string | Globally-unique identifier. |
| WasPausedFromScreen | boolean | Whether the user paused from a screen flow. |
| FlowVersionViewId | reference | Backing FlowDefinitionView / FlowVersionView. |
| InterviewStatus | picklist | `Started`, `Paused`, `WaitingOnUser`, `Completed`, `Error`. |

**Data content to inspect:** `InterviewLabel` is the field most likely to embed customer data — Flow developers commonly format the label with merge fields (`{!Account.Name}`, `{!Contact.Email}`). The Flow's *variable values* are not in this CSV (they are in a separate object, `FlowVariableView`).

---

# Event monitoring

## 17. EventLogFile

**API:** SObject (SOQL).
**What it represents:** the *header* rows for Event Monitoring log files. The actual log file contents are downloaded by a different tool (`salesforce_download_eventlog_files`); the rows here describe the metadata, not the body.

| Column | Type | What it stores |
|---|---|---|
| Id | id | EventLogFile Id. |
| IsDeleted, CreatedDate, CreatedById, LastModifiedDate, LastModifiedById, SystemModstamp | — | Provenance. |
| EventType | picklist | One of ~65 event types — `Login`, `URI`, `API`, `ApexExecution`, `ReportExport`, `LightningInteraction`, `BulkApi2`, etc. (Full list documented separately.) |
| LogDate | datetime | The 24-hour window this log file represents. |
| LogFileLength | int | Body length in bytes. |
| LogFileContentType | string | `text/csv`. |
| ApiVersion | double | API version of the schema. |
| Sequence | int | Sequence number for the log when split. |
| Interval | picklist | `Hourly`, `Daily`. |
| LogFileFieldNames | string | Comma-separated column-name list of the log's body schema. |
| LogFileFieldTypes | string | Parallel comma-separated type list. |
| LogFile | blob | Body field — the downloader skips this; bodies are fetched via the separate `/sobjects/EventLogFile/{Id}/LogFile` REST endpoint. |

**Data content to inspect:** the rows here are metadata only — file lengths, event types, timestamps. Row-level user activity is in the *bodies*, which are downloaded by the other tool.

**Retention:** 30 days for orgs with the Event Monitoring add-on; 1 day for orgs without it.

---

# Lightning telemetry

## 22. LightningUsageByAppTypeMetrics

**API:** SObject (Bulk-supported).
**What it represents:** per-user-per-day Lightning Experience usage roll-up by application type.

| Column | Type | What it stores |
|---|---|---|
| Id | id | Row Id. |
| MetricsDate | date | The day. |
| UserId | reference | The user. |
| AppExperience | picklist | `Lightning Experience`, `Mobile`, `Classic`. |
| SystemModstamp | datetime | Last modification. |

**Data content to inspect:** ties each user identity to per-day app-type usage.

## 23. LightningUsageByBrowserMetrics

**API:** SObject (Bulk-supported).
**What it represents:** per-page-per-day usage roll-up by browser. No user dimension.

| Column | Type | What it stores |
|---|---|---|
| Id | id | Row Id. |
| MetricsDate | date | Day. |
| PageName | string | Lightning page identifier. |
| Browser | string | Browser name. |
| SystemModstamp | datetime | Last modification. |
| RecordCountEPT | int | Number of pageviews contributing to EPT (Experienced Page Time). |
| TotalCount | int | Total pageviews on that page+browser+day. |
| SumEPT | int | Sum of EPT (ms). |
| EptBinUnder3, EptBin3To5, EptBin5To8, EptBin8To10, EptBinOver10 | int | Histogram buckets of EPT in seconds. |

**Data content to inspect:** aggregate metrics — no user identifiers in this table.

## 24. LightningUsageByFlexiPageMetrics

**API:** SObject (Bulk-supported).
**What it represents:** per-FlexiPage-per-day usage and device-context histograms. No user dimension.

| Column | Type | What it stores |
|---|---|---|
| Id, MetricsDate, FlexiPageType, FlexiPageNameOrId, SystemModstamp | — | Page identity and date. |
| RecordCountEPT, TotalCount, MedianEPT, SumEPT | int | Usage counts and EPT aggregate. |
| EptBinUnder3, EptBin3To5, EptBin5To8, EptBin8To10, EptBinOver10 | int | EPT bins (s). |
| CoresBinUnder2, CoresBin2To4, CoresBin4To8, CoresBinOver8 | int | Device-CPU-cores histogram. |
| DownlinkBinUnder3, DownlinkBin3To5, DownlinkBin5To8, DownlinkBin8To10, DownlinkBinOver10 | int | Network downlink histogram (Mbps). |
| RttBinUnder50, RttBin50To150, RttBinOver150 | int | Network RTT histogram (ms). |

**Data content to inspect:** aggregate metrics only; no user identifiers.

## 25. LightningUsageByPageMetrics

**API:** SObject (Bulk-supported).
**What it represents:** per-user-per-page-per-day Lightning Experience performance roll-up.

| Column | Type | What it stores |
|---|---|---|
| Id, MetricsDate, UserId, PageName, SystemModstamp | — | User × page × day. |
| RecordCountEPT, TotalCount, SumEPT | int | Counts and EPT sums. |
| EptBinUnder3, EptBin3To5, EptBin5To8, EptBin8To10, EptBinOver10 | int | EPT bins. |
| CoresBinUnder2, CoresBin2To4, CoresBin4To8, CoresBinOver8 | int | CPU-cores bins. |
| DownlinkBinUnder3, DownlinkBin3To5, DownlinkBin5To8, DownlinkBin8To10, DownlinkBinOver10 | int | Downlink bins. |
| RttBinUnder50, RttBin50To150, RttBinOver150 | int | RTT bins. |

**Data content to inspect:** ties each user identity to per-day page usage and device/network-class fingerprint. Distinct from `LightningUsageByPageMetrics` aggregations because of the `UserId` dimension.

---

# Organization

## 28. Organization

**API:** SObject (SOQL). One row per org.
**What it represents:** the org's primary configuration record — address, locale, default access settings, signup info, usage counters.

| Column | Type | What it stores |
|---|---|---|
| Id | id | Org Id (`00D…`). |
| Name | string | Configured org name. |
| Division | string | Org division (if Divisions are enabled). |
| Street, City, State, PostalCode, Country | string | Org address — admin-supplied. |
| StateCode, CountryCode | string | ISO codes. |
| Latitude, Longitude, GeocodeAccuracy | double / string | Geocoded org address. |
| Address | address | Compound (skipped by the downloader). |
| Phone | phone | Org phone. |
| Fax | phone | Org fax. |
| PrimaryContact | string | Primary contact name. |
| DefaultLocaleSidKey, TimeZoneSidKey, LanguageLocaleKey | string | Locale defaults. |
| ReceivesInfoEmails, ReceivesAdminInfoEmails | boolean | Email-opt-in flags. |
| Preferences* (multiple) | boolean | Org-level feature flags. |
| FiscalYearStartMonth | int | Fiscal year start. |
| UsesStartDateAsFiscalYearName | boolean | Fiscal-year naming flag. |
| DefaultAccountAccess, DefaultContactAccess, DefaultOpportunityAccess, DefaultLeadAccess, DefaultCaseAccess, DefaultCalendarAccess, DefaultPricebookAccess, DefaultCampaignAccess | picklist | OWD (organization-wide default) sharing for each major object. |
| SystemModstamp | datetime | Last modification. |
| ComplianceBccEmail | email | Address that gets BCC of compliance-relevant emails. |
| UiSkin | picklist | `Theme3`, `Theme4`, etc. |
| SignupCountryIsoCode | string | Country the org was signed up from. |
| TrialExpirationDate | datetime | Trial-org expiry. |
| NumKnowledgeService | int | Knowledge-related count. |
| OrganizationType | picklist | Salesforce edition (`Enterprise Edition`, `Unlimited Edition`, `Developer Edition`, `Trial`, etc.). |
| NamespacePrefix | string | Org namespace, if it has been set. |
| InstanceName | string | Pod identifier (e.g. `EU17`). |
| IsSandbox | boolean | `true` for sandbox orgs. |
| WebToCaseDefaultOrigin | string | Default origin for Web-to-Case. |
| MonthlyPageViewsUsed, MonthlyPageViewsEntitlement | int | Sites page-view usage. |
| IsReadOnly | boolean | Org-wide read-only mode. |
| CreatedDate, CreatedById, LastModifiedDate, LastModifiedById | — | Provenance. |

**Data content to inspect:** the org's postal address, phone, fax, `PrimaryContact`, `ComplianceBccEmail`, and signup country are admin-supplied strings. Identifies the org, the pod, edition, and sandbox vs production.

---

# Pseudo-objects (REST endpoints)

## 39. limits

**API:** REST endpoint `/services/data/vXX.X/limits/`. Not an sObject.
**What it represents:** current consumption against every documented org limit (API calls, daily mass mail, data storage, file storage, async Apex executions, etc.).

| Column | Type | What it stores |
|---|---|---|
| LimitName | string | The Salesforce-defined limit name (e.g. `DailyApiRequests`, `DataStorageMB`, `DailyAsyncApexExecutions`, `MassEmail`, `DailyBulkApiBatches`). |
| Max | int | Allocated maximum for the org. |
| Remaining | int | Remaining quota. |

**Data content to inspect:** numeric only. Reveals org scale (how many user licences, how much storage allocated, daily API ceiling).

## 40. recordCount

**API:** REST endpoint `/services/data/vXX.X/limits/recordCount`. Not an sObject.
**What it represents:** estimated row count per sObject in the org (only objects with row-count tracking enabled, which excludes a handful of system objects).

| Column | Type | What it stores |
|---|---|---|
| ObjectName | string | sObject API name. |
| RecordCount | int | Estimated row count. |

**Data content to inspect:** numeric only; reveals the data volume per object — which entities the org uses heavily (Cases, Accounts, custom objects, etc.).

---

## Summary table — what kind of content each object contributes

| Object | Identifies users? | Identifies IPs / geolocation? | Contains free-text fields? | Contains potential customer-data echoes? | Volume scales with |
|---|---|---|---|---|---|
| ApexClass | indirectly (CreatedById) | no | no | no | class count |
| ApexCodeCoverage | no | no | no | no | test methods × classes |
| ApexCodeCoverageAggregate | no | no | no | no | classes |
| ApexExecutionOverlayResult | yes (UserId, RequestedById) | no | no | no | active debugging sessions |
| ApexLog | yes (LogUserId) | no | Operation, Status | possible (fault messages) | active TraceFlags |
| ApexTestQueueItem | indirectly | no | ExtendedStatus | possible | test runs |
| ApexTestResult | indirectly | no | Message, StackTrace | possible (asserted strings) | test methods |
| ApexTestResultLimits | no | no | LimitExceptions | no | test methods |
| ApexTestRunResult | yes (UserId) | no | JobName, Source | rarely | test runs |
| AsyncApexJob | yes (CreatedById) | no | ExtendedStatus | possible (error messages) | async jobs |
| AuthSession | **yes (UsersId)** | **yes (SourceIp)** | LogoutUrl | no | active sessions |
| BackgroundOperation | indirectly | no | Error, Name, ParentKey | possible | PE/CDC traffic |
| CronJobDetail | no | no | Name | no | scheduled jobs |
| CronTrigger | yes (OwnerId) | no | CronExpression | no | scheduled jobs |
| DebugLevel | indirectly | no | DeveloperName, MasterLabel | no | debug-level definitions |
| EntityDefinition | no | no | Labels | reveals object/label names | sObjects in org |
| EventLogFile | yes (CreatedById on row) | no | LogFileFieldNames | metadata only — body is elsewhere | event types × days |
| FlowInterview | yes (OwnerId) | no | InterviewLabel, PauseLabel | **likely (merge-field values)** | paused interviews |
| Group | indirectly | no | Name, Email | possible | groups |
| GroupMember | **yes (UserOrGroupId)** | no | no | no | users × groups |
| IdpEventLog | **yes (UserId, IdentityUsed)** | no | ErrorCode, IdentityUsed | external IdP identifiers | SSO events |
| LightningUsageByAppTypeMetrics | **yes (UserId)** | no | no | no | users × days |
| LightningUsageByBrowserMetrics | no | no | PageName, Browser | no | pages × browsers × days |
| LightningUsageByFlexiPageMetrics | no | no | FlexiPageNameOrId | no | flexipages × days |
| LightningUsageByPageMetrics | **yes (UserId)** | no | PageName | no | users × pages × days |
| LoginGeo | linked (LoginGeoId join) | **yes (lat/lon, city, postcode, country)** | City, Subdivision | no | logins |
| LoginHistory | **yes (UserId)** | **yes (SourceIp, country)** | Status, Application, LoginUrl | failure messages can include attempted usernames | logins (6-month window) |
| Organization | indirectly | no | address fields, PrimaryContact, ComplianceBccEmail | no | constant (1 row) |
| PermissionSet | indirectly | no | Description | no | permission sets |
| PermissionSetAssignment | **yes (AssigneeId)** | no | no | no | users × permission sets |
| Profile | no | no | Description, Name | no | profiles |
| RecordType | no | no | Description, Name | no | record types |
| SessionPermSetActivation | **yes (UserId)** | no | Description | no | session-activated perm sets |
| SetupAuditTrail | yes (CreatedById, DelegateUser) | no | **Display (free text)** | embeds field/user/profile names | admin changes (180 days) |
| TraceFlag | yes (TracedEntityId) | no | no | no | active traces |
| UserLogin | **yes (UserId)** | no | no | no | users |
| UserRole | indirectly (ForecastUserId) | no | Name, RollupDescription | no | roles |
| VerificationHistory | **yes (UserId)** | **yes (SourceIp)** | Remarks, ResourceId, Policy | no | verification events |
| limits | no | no | no | no | constant (~50 rows) |
| recordCount | no | no | no | no | objects with row-count tracking |

---

## Sources

- Salesforce Platform Object Reference: <https://developer.salesforce.com/docs/atlas.en-us.object_reference.meta/object_reference/>
- Salesforce Tooling API Reference: <https://developer.salesforce.com/docs/atlas.en-us.api_tooling.meta/api_tooling/>
- Salesforce REST API Developer Guide (for `limits` and `recordCount` endpoints): <https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/>
- Salesforce Field Reference Guide: <https://developer.salesforce.com/docs/atlas.en-us.sfFieldRef.meta/sfFieldRef/>
- Column lists cross-checked against the CSV headers produced by a bulk SObject/Tooling-API exporter using the field-skip conventions noted in §"Notes on schema and format".
