# Salesforce Security Health Check — Output Reference

A field-level reference for the JSON artefact produced by extracting a Salesforce org's **Security Health Check** via the Tooling API.

For each field, this document gives:

- The data type.
- A factual description of what Salesforce stores in it.
- A "Data content to inspect" note where the field content depends on the target org or carries free text.

The intent is to let a reader classify the content themselves. Where Salesforce supplies enumerated values, those are listed verbatim.

---

## 1. Source and format

- **Source APIs:** the Tooling API, via two SOQL queries:
  - `SELECT Id, Score FROM SecurityHealthCheck` — returns exactly **one row** describing the org's overall health-check score.
  - `SELECT RiskType, Setting, SettingGroup, OrgValue, StandardValue FROM SecurityHealthCheckRisks` — returns one row per setting evaluated. The number of rows depends on which feature areas the org has enabled.
- **Output format:** a single UTF-8 JSON file named `securityhealthcheck_<org_alias>.json`. Structure:

  ```json
  {
    "SecurityHealthCheck": { "Id": "…", "Score": 68 },
    "Risks": [ { … }, … ],
    "risk_count": 37
  }
  ```

- **One file per org.** No timestamp roll-up — the file represents the score *as of the moment the extractor ran*. Re-running overwrites the prior file.
- **Authoritative reference:** the `SecurityHealthCheck` and `SecurityHealthCheckRisks` objects in the Salesforce Tooling API Reference (`https://developer.salesforce.com/docs/atlas.en-us.api_tooling.meta/api_tooling/`).

## 2. What Security Health Check is

Security Health Check is a Salesforce-shipped, admin-facing feature that compares an org's security settings against a Salesforce-defined **baseline standard**. Salesforce provides the default *Salesforce Baseline Standard*; orgs may also import customer-authored baselines.

The check covers ~50 settings spread across nine Setting Groups: `SessionSettings`, `PasswordPolicies`, `LoginAccessPolicies`, `SharingSettings`, `RemoteSiteSettings`, `FileUploadAndDownloadSecurity`, `CertificateAndKeyManagement`, `GuestUserAccess`, `UserPIISettings` (the exact list varies with Salesforce release and with features enabled in the org).

For every setting the check produces a row stating the **value the org has** (`OrgValue`) and the **value the baseline requires** (`StandardValue`), classified into a risk tier (`RiskType`). The overall `Score` is an integer 0–100 weighted by setting impact.

---

## 3. Schema

### 3.1 Top-level object

| Key | Type | What it stores |
|---|---|---|
| `SecurityHealthCheck` | object | Container for the org-level score row. |
| `Risks` | array | One element per evaluated setting. Length is org-specific. |
| `risk_count` | int | `len(Risks)` — added by the extractor for convenience. Not a Salesforce-side field. |

### 3.2 `SecurityHealthCheck` object

| Key | Type | What it stores |
|---|---|---|
| `Id` | id | Salesforce-internal Id of the SecurityHealthCheck record. Always present in the org; format is the standard 15-/18-char Salesforce Id, but for this singleton object it is typically the placeholder `000000000000000AAA`. No personal data. |
| `Score` | numeric (string in JSON, integer value) | Overall health-check score, **0–100**. Higher = closer to the baseline. The score is a weighted aggregate of the per-setting risk tiers. |

### 3.3 `Risks[]` array element

| Key | Type | What it stores |
|---|---|---|
| `attributes.type` | string | Always `"SecurityHealthCheckRisks"` — the Salesforce REST envelope's sObject-type field. |
| `attributes.url` | string | The Tooling-API URL of the row, of the form `/services/data/vXX.X/tooling/sobjects/SecurityHealthCheckRisks/<SettingGroup>.<settingKey>` — embeds the Setting Group and an internal setting key (e.g. `SessionSettings.clickjackVisualForceNoHeaders`, `PasswordPolicies.maxLoginAttempts`). The leading version segment reflects the API version the extractor used. |
| `RiskType` | picklist | One of: `HIGH_RISK`, `MEDIUM_RISK`, `LOW_RISK`, `INFORMATIONAL`, `MEETS_STANDARD`. (Salesforce-defined.) |
| `Setting` | string | Human-readable label of the setting evaluated (e.g. `"Enable clickjack protection for customer Visualforce pages with headers disabled"`, `"Maximum invalid login attempts"`, `"Number of Objects with Default External Access Set to Public"`). Sourced from Salesforce's baseline catalogue — not admin-supplied. |
| `SettingGroup` | picklist | The category the setting belongs to (e.g. `SessionSettings`, `PasswordPolicies`, `LoginAccessPolicies`, `SharingSettings`, `RemoteSiteSettings`, `FileUploadAndDownloadSecurity`, `CertificateAndKeyManagement`, `GuestUserAccess`, `UserPIISettings`). The full list is fixed by Salesforce per release. |
| `OrgValue` | string | The setting's current value **in this org**. Form varies by setting: numeric (`"52"`, `"10"`), boolean (`"Enabled"`, `"Disabled"`), short label (`"0 security risk file types with Hybrid behavior"`), or a comma-list (for multi-valued settings). |
| `StandardValue` | string | The baseline value the setting is compared against — same string form as `OrgValue`. |

---

## 4. Data content to inspect

The fields of this artefact contain the following classes of content. None are user-row data; all are org-configuration data.

| Field | Content nature |
|---|---|
| `SecurityHealthCheck.Score` | Numeric aggregate. Reveals how close the org is to the baseline. |
| `Risks[].RiskType` | Salesforce-defined enum value. No org-supplied content. |
| `Risks[].Setting` | Salesforce-defined catalogue text. No org-supplied content. |
| `Risks[].SettingGroup` | Salesforce-defined category name. No org-supplied content. |
| `Risks[].OrgValue` | **The org's actual configuration value for that setting.** This field carries the org-specific information: which protections are on/off, how many objects are publicly shared externally, how many invalid login attempts are permitted, whether certificate expiry is being tolerated, etc. For most settings the value is short (a number or `"Enabled"`/`"Disabled"`); for some it is a brief composed string. |
| `Risks[].StandardValue` | Salesforce-defined baseline value. No org-supplied content. |
| `attributes.url` | Setting Group + internal setting key — fixed by Salesforce per setting. |
| `attributes.type` | Constant `"SecurityHealthCheckRisks"`. |

What the artefact *does* contain about an org:

- The **overall security posture score**.
- For every setting in the catalogue, **the current org value vs the baseline value**, classified into HIGH/MEDIUM/LOW/INFO/MEETS_STANDARD.
- Implicit fingerprint of **which feature areas are enabled** in the org (settings only appear in the list when the relevant feature area is active).

What the artefact *does not* contain:

- No user identifiers.
- No IP addresses.
- No session tokens, OAuth tokens, or API keys.
- No customer record data.
- No Apex source, page source, or component source.
- No counts of records, users, or storage usage.
- No org name, domain, or sandbox-name identifier — those are not part of the Health Check schema. The org is identified only by the filename suffix (the org alias the extractor was pointed at).

---

## 5. Volume

One JSON file per org per extraction. Each file is small — typically 5–60 KB depending on how many settings are evaluated and how long the human-readable `Setting` labels are. The `Risks` array length is typically 30–60 elements; the SHC sample observed for this reference contained 37.

## 6. Retention / freshness

The artefact is a **point-in-time snapshot** of the org's Security Health Check at the moment of extraction. Salesforce does not version the SecurityHealthCheckRisks object server-side; re-extracting overwrites the file with the current state. There is no built-in change-log inside the file.

To track posture over time, the artefact would need to be copied or committed before re-extraction.

---

## 7. Sources

- Salesforce Tooling API Reference — `SecurityHealthCheck`: <https://developer.salesforce.com/docs/atlas.en-us.api_tooling.meta/api_tooling/tooling_api_objects_securityhealthcheck.htm>
- Salesforce Tooling API Reference — `SecurityHealthCheckRisks`: <https://developer.salesforce.com/docs/atlas.en-us.api_tooling.meta/api_tooling/tooling_api_objects_securityhealthcheckrisks.htm>
- Salesforce Help — Health Check overview: <https://help.salesforce.com/s/articleView?id=sf.security_health_check.htm>
