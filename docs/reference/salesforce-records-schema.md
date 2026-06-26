# Salesforce sObject Describe and SOQL Query — Records Schema Reference

A field-level reference for the two Salesforce REST API responses that `get_records` consumes: the **sObject Describe** response (field metadata) and the **SOQL query** response (record values).

- **Source of schema:** Salesforce SOAP API WSDL (via jsforce TypeScript definitions, which are generated from the WSDL); cross-validated against the Salesforce Lightning API Developer Guide.
- **Source of response structure:** official Salesforce REST API Developer Guide (resource definitions at `developer.salesforce.com`).
- **Scope:** this document covers the data shapes that the classifier (`classify.py`) and extractor consume. It does not attempt to document every REST API feature.

---

## 1. Source APIs

`get_records` makes two categories of Salesforce API call, both read-only:

| Call | REST path | Purpose |
|---|---|---|
| sObject Describe | `GET /services/data/vXX.X/sobjects/<Name>/describe/` | Returns full metadata for one sObject type: label, field list, relationship definitions, capabilities. |
| SOQL Query | `GET /services/data/vXX.X/query/?q=<SELECT …>` | Returns records matching a SOQL SELECT statement, paginated in batches of up to 2000 records per response. |

Both calls require an authenticated Salesforce session. Neither call modifies data. The extractor issues them via `sf sobject describe` and `sf data query --json` (the Salesforce CLI, which wraps the REST API).

---

## 2. sObject Describe response

### 2.1 Endpoint

```
GET /services/data/vXX.X/sobjects/<ObjectApiName>/describe/
```

The response is a JSON object with top-level object-capability properties and a `fields` array.

### 2.2 Top-level DescribeSObjectResult properties

The following properties are returned at the root of the describe response. Properties marked * are used by `get_records` directly; the rest are available but not currently consumed by the classifier.

| Property | Type | Description |
|---|---|---|
| `name` * | string | The API name of the object (e.g. `"Contact"`, `"Account"`). |
| `label` | string | The human-readable singular label (e.g. `"Contact"`). |
| `labelPlural` | string | The human-readable plural label (e.g. `"Contacts"`). |
| `keyPrefix` | string \| null | The 3-character prefix used in record Ids for this object (e.g. `"003"` for Contact). Null for objects without record pages. |
| `custom` | boolean | `true` if this is a custom object (API name ends in `__c`). |
| `customSetting` | boolean | `true` if this is a Custom Setting object. |
| `queryable` * | boolean | `true` if records of this type can be retrieved via SOQL SELECT. `get_records` only targets queryable objects. |
| `createable` | boolean | `true` if records can be created via the API. |
| `updateable` | boolean | `true` if records can be updated via the API. |
| `deletable` | boolean | `true` if records can be deleted via the API. |
| `mergeable` | boolean | `true` if records can be merged. |
| `undeletable` | boolean | `true` if deleted records can be undeleted from the Recycle Bin. |
| `replicateable` | boolean | `true` if records can be retrieved using the Replication API. |
| `retrieveable` | boolean | `true` if records can be retrieved using the Metadata API retrieve call. |
| `searchable` | boolean | `true` if this object can appear in SOSL search results. |
| `triggerable` | boolean | `true` if Apex triggers can be defined on this object. |
| `feedEnabled` | boolean | `true` if Chatter feed is enabled on the object. |
| `mruEnabled` | boolean | `true` if the object appears in Most Recently Used lists. |
| `activateable` | boolean | `true` if this object supports the Activate action. |
| `deprecatedAndHidden` | boolean | `true` if this object is deprecated and hidden from most API users. |
| `layoutable` | boolean | `true` if this object supports Salesforce Lightning and Classic page layouts. |
| `compactLayoutable` | boolean | `true` if this object supports compact layouts. |
| `searchLayoutable` | boolean | `true` if this object supports search result layouts. |
| `fields` * | Field[] | Array of field metadata objects. One element per field. See §2.3. |
| `childRelationships` | ChildRelationship[] | Array describing parent–child relationships from this object to child objects. |
| `recordTypeInfos` | RecordTypeInfo[] | Array of record type definitions for this object. |
| `supportedScopes` | ScopeInfo[] | Filter scopes supported for this object (e.g. `Mine`, `Team`). |
| `urls` | object | Map of named URL templates for this object (e.g. `rowTemplate`, `describe`, `sobject`). |

### 2.3 Field interface properties

Each element of the `fields` array describes one field on the object. Properties marked * are extracted by `FieldMeta.from_describe()` in `classify.py` and used by the classifier.

| Property | Type | Description |
|---|---|---|
| `name` * | string | The field's API name (e.g. `"FirstName"`, `"BillingCity"`, `"CustomScore__c"`). |
| `label` * | string | The human-readable label shown in the UI (e.g. `"First Name"`, `"Billing City"`). |
| `type` * | FieldType | The field's data type. See §3 for the complete enum. |
| `length` * | integer | Maximum character length of the field value. For number types, this is the total character length including digits and separators. For `textarea`, this is the character cap for the stored value. |
| `custom` * | boolean | `true` if this is a custom field (API name ends in `__c`). |
| `calculated` * | boolean | `true` if this is a formula field whose value is computed by Salesforce at read time. |
| `calculatedFormula` * | string \| null | The formula source text, present only when `calculated` is `true`. The classifier uses this to detect formula fields that re-expose PII fields. |
| `inlineHelpText` * | string \| null | Help text entered by an admin in the field definition. Included in the classifier's haystack so PII-shaped help text causes the field to be classified conservatively. |
| `soapType` | string | The SOAP-API type name for this field (e.g. `"xsd:string"`, `"tns:ID"`). Different casing and namespace convention from `type`. |
| `autoNumber` | boolean | `true` if the field is an auto-number field (formatted incrementing integer, read-only). |
| `byteLength` | integer | Maximum byte length of the stored value (relevant for multi-byte character sets). |
| `createable` | boolean | `true` if a value can be set when creating a record. |
| `updateable` | boolean | `true` if the value can be changed after record creation. |
| `nillable` | boolean | `true` if the field accepts null (blank) values. |
| `defaultedOnCreate` | boolean | `true` if Salesforce auto-populates a default value when a record is created. |
| `unique` | boolean | `true` if a uniqueness constraint is enforced on this field. |
| `externalId` | boolean | `true` if this field is marked as an External ID — used as an upsert key for data loads. |
| `idLookup` | boolean | `true` if this field can be used in record lookup operations. |
| `nameField` | boolean | `true` if this is the name field for the object (typically `Name` on standard objects, or the field that provides the record's display name). |
| `namePointing` | boolean | `true` if this is a polymorphic name-pointing reference field. |
| `filterable` | boolean | `true` if this field can appear in a SOQL WHERE clause. |
| `sortable` | boolean | `true` if this field can appear in a SOQL ORDER BY clause. |
| `groupable` | boolean | `true` if this field can appear in a SOQL GROUP BY clause. |
| `aggregatable` | boolean | `true` if this field can appear in a SOQL aggregate function (COUNT, SUM, etc.). |
| `searchPrefilterable` | boolean | `true` if this field supports search pre-filtering. |
| `queryByDistance` | boolean | `true` if this is a geolocation field that supports DISTANCE/GEOLOCATION query functions. |
| `permissionable` | boolean | `true` if field-level security can be configured for this field. |
| `htmlFormatted` | boolean | `true` if the field value may contain HTML (e.g. rich text areas). |
| `highScaleNumber` | boolean | `true` if this is a high-precision decimal field. |
| `caseSensitive` | boolean | `true` if string comparisons on this field are case-sensitive. |
| `restrictedPicklist` | boolean | `true` if only values from the defined picklist are valid (no freeform entry). |
| `dependentPicklist` | boolean | `true` if this picklist's available values depend on the value of a controlling field. |
| `controllerName` | string \| null | API name of the controlling field, when `dependentPicklist` is `true`. |
| `picklistValues` | PicklistEntry[] \| null | Array of defined picklist entries, present for `picklist` and `multipicklist` fields. Each entry has `value`, `label`, `active`, `defaultValue`. |
| `referenceTo` | string[] | Array of object API names this field can point to. Non-empty for `reference` fields. Single-element for standard lookups; multi-element for polymorphic (e.g. `WhoId`, `WhatId`). |
| `relationshipName` | string \| null | The relationship name used in dot-notation SOQL traversal (e.g. `"Account"` for `AccountId`). |
| `relationshipOrder` | integer \| null | For master-detail fields, `0` for the primary, `1` for the secondary master. |
| `cascadeDelete` | boolean | `true` if deleting the master record cascades to delete this record. |
| `writeRequiresMasterRead` | boolean | `true` if creating/editing this detail record requires read access to the master. |
| `polymorphicForeignKey` | boolean | `true` if this reference field can point to multiple object types. |
| `referenceTargetField` | string \| null | For indirect lookup fields, the field on the target object used as the join key. |
| `filteredLookupInfo` | object \| null | Filter conditions applied to lookup searches on this field, when a filter has been configured. |
| `defaultValue` | any \| null | The default value applied when creating a record, if one has been configured. |
| `defaultValueFormula` | string \| null | Formula used to compute the default value, if a formula-based default is configured. |
| `digits` | integer \| null | Number of digits to the left of the decimal point for numeric fields. |
| `precision` | integer \| null | Total number of digits (left + right of decimal) for double and currency fields. |
| `scale` | integer | Number of digits to the right of the decimal point for double, currency, and percent fields. |
| `displayLocationInDecimal` | boolean \| null | For location fields, `true` if coordinates are displayed in decimal degrees rather than DMS. |
| `encrypted` | boolean \| null | `true` if this is a Classic Encryption field (type `encryptedstring`). See §3 note on `encryptedstring`. |
| `mask` | string \| null | The masking pattern applied to Classic Encryption fields for users without "View Encrypted Data" permission (e.g. `"XXXXXXXXXXXXXXXX"`). |
| `maskType` | string \| null | The type of mask applied (e.g. `"all"`, `"lastFour"`, `"creditCard"`, `"ssn"`, `"nino"`, `"sin"`, `"ein"`). |
| `extraTypeInfo` | ExtraTypeInfo \| null | Secondary type qualifier providing additional type context for certain field types. See §4 for the complete enum. |
| `compoundFieldName` | string \| null | For component fields of a compound field (e.g. `BillingStreet`, `BillingCity`), the API name of the compound field they belong to (e.g. `"BillingAddress"`). |
| `formula` | string \| null | Alias for `calculatedFormula` in some API versions. See `calculatedFormula`. |

---

## 3. FieldType enum

The `type` property of a field takes one of the following string values. These are returned as lowercase strings in the REST API describe response.

Source: Salesforce SOAP API WSDL (via jsforce TypeScript definitions); cross-validated against the Salesforce Lightning API Developer Guide.

| Value | Description |
|---|---|
| `string` | Variable-length text field. Length constrained by the `length` property. |
| `boolean` | True/false checkbox field. |
| `int` | Integer numeric field. |
| `double` | Floating-point numeric field. Scale and precision defined by the `scale` and `precision` properties. |
| `date` | Date only (no time component). Format `YYYY-MM-DD` in API results. |
| `datetime` | Date and time. Format `YYYY-MM-DDThh:mm:ss.sssZ` (UTC) in API results. |
| `base64` | Binary data encoded as base64. Used by the `Body` field on objects such as `Attachment` and `Document`. |
| `id` | The Salesforce record Id field (`Id`). 15-character case-sensitive or 18-character case-safe string. |
| `reference` | A lookup or master-detail relationship field storing a foreign record Id. The `referenceTo` property lists the target object(s). |
| `currency` | Currency amount. Numeric value; associated currency code stored separately in multi-currency orgs. |
| `textarea` | Long text field. The `length` property gives the character cap. Short text areas use `length` ≤ 255; long text areas can reach 131,072 characters. |
| `percent` | Percentage value. Stored and returned as a decimal number (e.g. `50` for 50%). |
| `phone` | Phone number. Stored as a string; no canonical format enforced by the platform. |
| `url` | URL string. |
| `email` | Email address string. |
| `combobox` | A combination field that accepts both picklist values and freeform text. |
| `picklist` | Single-select picklist. Valid values enumerated in `picklistValues`. |
| `multipicklist` | Multi-select picklist. Selected values are stored as a semicolon-delimited string. |
| `anyType` | Polymorphic value field (used by certain standard fields such as `Value` on `CustomField`). |
| `location` | Geolocation compound field storing latitude and longitude as a unit. Component `latitude` and `longitude` sub-fields are separately queryable. |
| `time` | Time of day (no date component). Format `hh:mm:ss.SSS` in API results. |
| `encryptedstring` | A Classic Encryption field. Values are encrypted at rest using AES-128. Users with the "View Encrypted Data" permission receive the decrypted value in API responses; users without it receive a masked value (asterisks). Cannot be used in SOQL WHERE, ORDER BY, GROUP BY, or aggregate functions. Distinct from Salesforce Shield Platform Encryption, which operates transparently at the database layer and does not change the field type. |
| `address` | Compound address field aggregating component address sub-fields (Street, City, State, PostalCode, Country, Latitude, Longitude, GeocodeAccuracy). The compound field itself is not directly queryable; its component fields are. |
| `complexvalue` | A structured complex value used by certain Salesforce platform objects. Not a user-facing custom field type. |

---

## 4. ExtraTypeInfo enum

The `extraTypeInfo` property provides a secondary type qualifier. It is present on certain field types to distinguish subtypes that share the same `type` value.

Source: Salesforce SOAP API WSDL (via jsforce TypeScript definitions); cross-validated against the Salesforce Lightning API Developer Guide.

| Value | Applies to | Description |
|---|---|---|
| `plaintextarea` | `textarea` | A plain-text area field. Values contain no formatting markup. |
| `richtextarea` | `textarea` | A rich text area field. Values may contain HTML markup generated by the Salesforce rich text editor. |
| `imageurl` | `url` | A URL field that references an image. |
| `personname` | `string` | A name component field (e.g. `FirstName`, `LastName`) on a Person Account object. |
| `switchablepersonname` | `string` | A name field that can switch between business-name and person-name display. |
| `externallookup` | `reference` | An external lookup relationship field that joins to an External Object via an External ID. |
| `indirectlookup` | `reference` | An indirect lookup relationship field that joins to a standard or custom object via a custom External ID field rather than the record `Id`. |

---

## 5. SOQL query response

### 5.1 Endpoint

```
GET /services/data/vXX.X/query/?q=<SOQL SELECT statement>
GET /services/data/vXX.X/query/<queryLocator>   (subsequent pages)
```

### 5.2 Query result structure

The response is a JSON object with the following top-level properties:

| Property | Type | Description |
|---|---|---|
| `totalSize` | integer | Total number of records matching the query, across all pages. |
| `done` | boolean | `true` if all matching records are included in this response. `false` if there are additional pages. |
| `nextRecordsUrl` | string | Present only when `done` is `false`. A relative URL to retrieve the next batch of records. Format: `/services/data/vXX.X/query/<queryLocator>`. |
| `records` | object[] | Array of record objects for this page. Each page contains up to 2000 records. |

### 5.3 Record object structure

Each element of `records` is a JSON object with the following structure:

| Property | Type | Description |
|---|---|---|
| `attributes` | object | Salesforce REST API envelope metadata for this record. |
| `attributes.type` | string | The API name of the sObject type (e.g. `"Contact"`, `"Account"`). |
| `attributes.url` | string | Relative REST URL to this record (e.g. `/services/data/vXX.X/sobjects/Contact/003…`). |
| *field name* | *field type* | One key per field in the SELECT clause. The key is the field's API name. The value is the field's current value in the type appropriate to the field's `type` property (string, boolean, integer, decimal, null, or nested object for compound/relationship fields). |

Null field values are returned as JSON `null`. Compound fields (`address`, `location`) that appear in the SELECT are returned as nested JSON objects containing their component sub-fields.

Relationship traversal fields (e.g. `SELECT Account.Name FROM Contact`) are returned as nested objects with their own `attributes.type`, `attributes.url`, and field properties.

---

## 6. Classifier-relevant field properties

`classify.py` extracts the following subset of the Field interface via `FieldMeta.from_describe()`. These are the only properties the classifier reads:

| Describe key | FieldMeta field | Used for |
|---|---|---|
| `name` | `name` | Primary pattern matching (haystack); Jigsaw-name check; standard `Name` field detection. |
| `label` | `label` | Included in the haystack for pattern matching. |
| `type` | `type` | Type-based rules: `id`/`reference` → RAW; `textarea` + length → essay-DROP; `email` → HASH_EMAIL; text-type gate for name-based email rule. |
| `length` | `length` | Essay-size thresholds: `textarea` ≥ 30,000 chars → DROP; essay-named ≥ 1,000 chars → DROP. |
| `custom` | `custom` | Available in FieldMeta but not currently used in a classifier rule. |
| `calculated` | `calculated` | Formula-leak detection: only formula fields are checked against FORMULA_LEAK_SOURCES. |
| `calculatedFormula` | `formula` | The formula source text scanned for PII-field references (FirstName, LastName, Email, etc.). |
| `inlineHelpText` | `help_text` | Included in the haystack; admin-supplied help text that names a PII concept triggers conservative classification. |

The haystack is `"{name}\n{label}\n{help_text}".lower()`. All pattern matches run against the haystack.

---

## 7. Sources

- Salesforce REST API Developer Guide — sObject Describe: <https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/resources_sobject_describe.htm>
- Salesforce REST API Developer Guide — Execute a SOQL Query: <https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/dome_query.htm>
- Salesforce REST API Developer Guide — Query resource reference: <https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/resources_query.htm>
- jsforce TypeScript definitions (WSDL-derived) — Field and DescribeSObjectResult interfaces: <https://github.com/salto-io/jsforce-types/blob/master/describe-result.d.ts>
- Salesforce SOAP API Developer Guide — DescribeSObjectResult: <https://developer.salesforce.com/docs/atlas.en-us.api.meta/api/sforce_api_calls_describesobjects_describesobjectresult.htm>
- Salesforce Help — Classic Encryption and "View Encrypted Data" permission: <https://help.salesforce.com/s/articleView?id=sf.fields_about_encrypted_fields.htm>
- Salesforce Help — Encrypted field masking: <https://help.salesforce.com/s/articleView?language=en_US&id=sf.security_pe_masking.htm&type=5>
