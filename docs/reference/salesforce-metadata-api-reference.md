# Salesforce Metadata API — Reference

A schema and behaviour reference for the Salesforce **Metadata API** (SOAP) as used by the `get_metadata` command.

For each response type, this document gives:

- The field names and types as documented by Salesforce.
- A description of what Salesforce stores in each field.
- Enumerated values where the field has a documented closed set.

Every claim in this document is taken from official Salesforce documentation and cross-referenced against a second official source before inclusion. Where Salesforce documentation is ambiguous or the cross-reference could not be completed, the point is omitted.

**Authoritative sources used:**
- Salesforce Metadata API Developer Guide — `describeMetadata` (`developer.salesforce.com/docs/atlas.en-us.api_meta.meta/api_meta/meta_describe.htm`)
- Salesforce Metadata API Developer Guide — `listMetadata` (`developer.salesforce.com/docs/atlas.en-us.api_meta.meta/api_meta/meta_listmetadata.htm`)
- Salesforce Metadata API Developer Guide — `retrieve` and `RetrieveResult` (`developer.salesforce.com/docs/atlas.en-us.api_meta.meta/api_meta/meta_retrieve.htm`, `meta_retrieveresult.htm`)
- Salesforce Metadata API Developer Guide — Package manifest (`developer.salesforce.com/docs/atlas.en-us.api_meta.meta/api_meta/meta_deploy_package_xml.htm`)
- Salesforce Metadata API Developer Guide — Metadata types index (`developer.salesforce.com/docs/atlas.en-us.api_meta.meta/api_meta/meta_objects_intro.htm`)
- Salesforce DX Developer Guide — Source file format (`developer.salesforce.com/docs/atlas.en-us.sfdx_dev.meta/sfdx_dev/sfdx_dev_source_file_format.htm`)
- Salesforce Help — Metadata API limits (`help.salesforce.com/s/articleView?id=sf.code_builder_metadata_api_limits.htm`)
- Salesforce official Metadata API WSDL/XSD — `FileProperties` type definition (forcedotcom/idecore, `com.salesforce.ide.api/schema/metadata.xsd`)
- Salesforce App Limits Cheat Sheet (`developer.salesforce.com/docs/atlas.en-us.salesforce_app_limits_cheatsheet`)

**Corrections from cross-reference pass:** A second independent research pass against the official Metadata API XSD found that `managedByPackageName` does not exist in the `FileProperties` schema — `FileProperties` has 12 fields, not 13. The §3.2 table below reflects the verified 12-field set. The "~600 MB compressed-zip limit" referenced in `sf-clean-room/src/sf_clean_room/constants.py` has no official Salesforce documentation backing; the two documented limits are: 39 MB compressed (SOAP message ceiling of 50 MB after base-64 encoding overhead) and 400 MB uncompressed extraction. Both are documented in §8.

---

## 1. API endpoint and protocol

- **Protocol:** SOAP over HTTPS.
- **Endpoint pattern:** `https://<instance>/services/Soap/m/<apiVersion>` — e.g. `https://myorg.my.salesforce.com/services/Soap/m/61.0`.
- **Namespace (SOAP envelope body and types):** `http://soap.sforce.com/2006/04/metadata`
- **Authentication:** `SessionHeader` SOAP header containing a `sessionId`.
- **API version pinned at:** `61.0` (the version used by `get_metadata`).

---

## 2. `describeMetadata`

Returns the full set of metadata types available in the org at the requested API version.

### 2.1 Request

```xml
<describeMetadata xmlns="http://soap.sforce.com/2006/04/metadata">
  <asOfVersion>61.0</asOfVersion>
</describeMetadata>
```

### 2.2 Response — `MetadataObject` fields

The response contains a `metadataObjects` array. Each element has these fields:

| Field | Type | What it stores |
|---|---|---|
| `xmlName` | string | The metadata type name. Used in `package.xml` `<name>` elements and in `listMetadata` queries. |
| `directoryName` | string | The subdirectory name used for this type inside a retrieved zip. For example, `classes` for `ApexClass`, `objects` for `CustomObject`. |
| `inFolder` | boolean | Whether this type is stored in folders (`true` for `Dashboard`, `Report`, `Document`, `EmailTemplate`; `false` for all other types). Foldered types require a two-step `listMetadata` enumeration. |
| `metaFile` | boolean | Whether each component of this type has a corresponding `-meta.xml` companion file alongside its main content file. `true` for code types (`ApexClass`, `ApexTrigger`, `ApexPage`); `false` for types that are pure metadata XML. |
| `suffix` | string | The file extension of components of this type — e.g. `cls` for `ApexClass`, `trigger` for `ApexTrigger`, `object` for `CustomObject`. Not all types have a suffix (some produce only the `-meta.xml` file). |
| `childXmlNames` | string[] | Array of metadata type names that are children of this type: they can only be retrieved as part of the parent and are not independently enumerable. Example: `CustomField`, `ValidationRule`, `RecordType`, `BusinessProcess` are children of `CustomObject`. |

---

## 3. `listMetadata`

Lists all components of a given metadata type available to the authenticated identity.

### 3.1 Request

```xml
<listMetadata xmlns="http://soap.sforce.com/2006/04/metadata">
  <queries>
    <type>ApexClass</type>
  </queries>
  <asOfVersion>61.0</asOfVersion>
</listMetadata>
```

For foldered types, a `<folder>` element is added inside `<queries>`:

```xml
<queries>
  <type>Report</type>
  <folder>MyReportFolder</folder>
</queries>
```

A single `listMetadata` call accepts up to **3 queries** per call.

### 3.2 Response — `FileProperties` fields

The response contains a `result` array. Each element has these fields:

| Field | Type | What it stores |
|---|---|---|
| `createdById` | ID | Salesforce ID of the user who created the component. |
| `createdByName` | string | Full name of the user who created the component. |
| `createdDate` | dateTime | Date and time the component was created. |
| `fileName` | string | Path of the component within a retrieve zip. For example: `unpackaged/classes/MyClass.cls`. |
| `fullName` | string | API name of the component. This is the value used in `package.xml` `<members>` elements. |
| `id` | ID | Salesforce ID of the component record. |
| `lastModifiedById` | ID | Salesforce ID of the user who last modified the component. |
| `lastModifiedByName` | string | Full name of the user who last modified the component. |
| `lastModifiedDate` | dateTime | Date and time of the last modification. |
| `manageableState` | string (optional) | Whether the component is part of a managed package. Optional (`minOccurs=0`). Documented values listed in §3.3. |
| `namespacePrefix` | string (optional) | Namespace prefix of the component's managing package. Optional (`minOccurs=0`). Empty string for unmanaged components. |
| `type` | string | The metadata type name of the component. Matches the `xmlName` from `describeMetadata`. |

> **Note:** `managedByPackageName` is **not** a field in the `FileProperties` schema. The official Salesforce Metadata API XSD (`forcedotcom/idecore`) defines exactly these 12 fields; no 13th field exists.

### 3.3 `manageableState` documented values

| Value | Meaning |
|---|---|
| `beta` | Component is in a beta-version managed package. |
| `deleted` | Component has been deleted but remains accessible via the API. |
| `deprecated` | Component has been deprecated in the installed managed package. |
| `deprecatedEditable` | Component is deprecated in a managed package but may be edited in the subscriber org. |
| `installed` | Component belongs to an installed managed package (as seen from a subscriber org). |
| `installedEditable` | Component belongs to an installed managed package and may be edited by the subscriber. |
| `released` | Component is in a released managed package (as seen from the package developer's org). |
| `unmanaged` | Component is not part of any managed package. |

---

## 4. `package.xml` manifest format

`package.xml` is the metadata manifest used both as a retrieve request body and as the output sentinel written to the published folder.

### 4.1 XML structure

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>MyApexClass</members>
        <members>AnotherApexClass</members>
        <name>ApexClass</name>
    </types>
    <types>
        <members>MyObject__c</members>
        <name>CustomObject</name>
    </types>
    <version>61.0</version>
</Package>
```

### 4.2 Rules

- The XML namespace is `http://soap.sforce.com/2006/04/metadata` (the same as the SOAP endpoint namespace).
- Each `<types>` block contains one `<name>` element (the metadata type `xmlName`) and one or more `<members>` elements (component `fullName` values).
- The `<name>` element must appear **after** all `<members>` elements within a `<types>` block.
- The `<version>` element at the package level specifies the API version.
- To retrieve all components of a type, use `<members>*</members>` (wildcard). Not all types support wildcard retrieval — notably `Profile` does not support wildcard.
- The file must be valid UTF-8 encoded XML.

---

## 5. Retrieve — async operation

The `retrieve` call is asynchronous. The documented flow is:

1. Submit `retrieve` → server returns an `asyncProcessId`.
2. Poll `checkRetrieveStatus` with the `asyncProcessId` until the status is terminal.
3. On `Succeeded`, the `checkRetrieveStatus` response includes a `zipFile` field (base64-encoded zip).

### 5.1 `retrieve` request fields

| Field | Description |
|---|---|
| `apiVersion` | API version for the retrieve. |
| `singlePackage` | Boolean. `true` puts all retrieved components in a single `unpackaged/` directory in the zip. |
| `unpackaged` | The manifest body (equivalent to `package.xml` contents: `<types>` blocks + `<version>`). |

### 5.2 `checkRetrieveStatus` terminal status values

| Status | Meaning |
|---|---|
| `Succeeded` | Retrieve completed; zip is available in `zipFile`. |
| `Failed` | Retrieve failed. `errorMessage` contains detail. |
| `Canceled` | Retrieve was cancelled. |

Non-terminal values include `Pending`, `InProgress`, `Queued`.

---

## 6. Retrieve ZIP structure

For a `singlePackage=true` retrieve, the decoded zip has this layout:

```
unpackaged/
    package.xml
    classes/
        MyClass.cls
        MyClass.cls-meta.xml
    triggers/
        MyTrigger.trigger
        MyTrigger.trigger-meta.xml
    objects/
        MyObject__c.object
    flows/
        MyFlow.flow-meta.xml
    layouts/
        MyObject__c-My_Layout.layout-meta.xml
    reports/
        MyFolder/
            MyReport.report-meta.xml
        MyFolder-meta.xml
    ...
```

### 6.1 Layout rules

- The root directory for `singlePackage=true` is always `unpackaged/`.
- Each metadata type has a subdirectory matching the `directoryName` from `describeMetadata`.
- Types with `metaFile=true` (Apex code) produce two files per component: the code file (e.g. `.cls`) and a companion `-meta.xml` file.
- Types with `metaFile=false` produce a single `-meta.xml` file per component.
- `package.xml` is always at `unpackaged/package.xml`.

### 6.2 Foldered type layout

Foldered types add a folder-name level between the type directory and the component file:

```
unpackaged/
    reports/
        FolderName/
            ComponentName.report-meta.xml
        FolderName-meta.xml        ← the folder object itself
```

The folder objects (`ReportFolder`, `DashboardFolder`, `DocumentFolder`, `EmailFolder`) are retrievable metadata in their own right, produced as `-meta.xml` files at the type directory level.

---

## 7. Foldered types — enumeration

The four foldered types and their corresponding folder types (per `describeMetadata`):

| Inner type | Folder type |
|---|---|
| `Dashboard` | `DashboardFolder` |
| `Document` | `DocumentFolder` |
| `EmailTemplate` | `EmailFolder` |
| `Report` | `ReportFolder` |

**Enumeration procedure:**
1. Call `listMetadata` with the **folder type** (e.g. `DashboardFolder`) to retrieve the list of folder names.
2. For each folder name, call `listMetadata` with the **inner type** and the `<folder>` parameter.

Wildcard `<members>*</members>` does not work for foldered types; folder-by-folder enumeration is required.

**`unfiled$public`:** A special folder name used for components not placed in any named folder. It is not returned by `listMetadata(DashboardFolder)` or `listMetadata(ReportFolder)` as a folder record, but components placed there must be fetched by calling `listMetadata` with `<folder>unfiled$public</folder>`.

---

## 8. Limits

Per Salesforce Metadata API Developer Guide and Salesforce Help:

| Limit | Documented value | Source |
|---|---|---|
| Maximum components per `retrieve` request | 10,000 | Salesforce App Limits Cheat Sheet; Salesforce developer blog (2025-10) |
| Maximum compressed ZIP per `retrieve` (SOAP) | ~39 MB | Derived from 50 MB SOAP message ceiling with base-64 encoding overhead (~22%). Salesforce App Limits Cheat Sheet documents the 50 MB SOAP limit. |
| Maximum uncompressed extraction size | 400 MB | Salesforce Help — Metadata API limits |
| Maximum queries per `listMetadata` call | 3 | Salesforce Metadata API Developer Guide — `listMetadata` |

**Note on the ~600 MB figure in `sf-clean-room/src/sf_clean_room/constants.py`:** The comment `# Weight ceiling targets Salesforce's ~600 MB compressed-zip limit per retrieve` has no official documentation backing. The two actual documented limits are 39 MB compressed (SOAP) and 400 MB uncompressed. `MAX_WEIGHT_PER_BATCH = 50_000` is a dimensionless proxy weight, not a byte count. The comment should be corrected.

---

## 9. Metadata type taxonomy

The Salesforce Metadata API Developer Guide organises types into the following documented categories. This is a representative selection of types from each category, not an exhaustive list.

### 9.1 Code

| Type | `directoryName` | `suffix` | Notes |
|---|---|---|---|
| `ApexClass` | `classes` | `cls` | Apex class; `.cls-meta.xml` companion. |
| `ApexTrigger` | `triggers` | `trigger` | Apex trigger; `.trigger-meta.xml` companion. |
| `ApexPage` | `pages` | `page` | Visualforce page. |
| `ApexComponent` | `components` | `component` | Visualforce component. |
| `LightningComponentBundle` | `lwc` | none | Multi-file bundle directory. Heavy (weight 20 in sf-clean-room). |
| `AuraDefinitionBundle` | `aura` | none | Multi-file bundle directory. Heavy (weight 15). |

### 9.2 Object model

| Type | Notes |
|---|---|
| `CustomObject` | Object definition; child types include `CustomField`, `ValidationRule`, `RecordType`, `BusinessProcess`, `WebLink`, `ListView`. |
| `CustomField` | Child of `CustomObject`; not independently retrievable. |
| `Layout` | Page layout definitions. |
| `RecordType` | Record type definitions; child of `CustomObject`. |
| `ValidationRule` | Validation rules; child of `CustomObject`. |
| `GlobalValueSet` | Shared global picklist definitions. |
| `StandardValueSet` | Standard picklist values. May not appear in `describeMetadata` output for all org types. |

### 9.3 Automation

| Type | Notes |
|---|---|
| `Flow` | Flow definitions (Screen Flows, Auto-launched Flows, Scheduled Flows, etc.). |
| `FlowDefinition` | Tracks which version of a Flow is active. |
| `WorkflowRule` | Legacy workflow rules. Child types include `WorkflowAlert`, `WorkflowFieldUpdate`, `WorkflowTask`, `WorkflowOutboundMessage`. |
| `ApprovalProcess` | Approval process definitions. |

### 9.4 Analytics

| Type | Notes |
|---|---|
| `Report` | Report definitions. Foldered type. |
| `Dashboard` | Dashboard definitions. Foldered type. |
| `WaveApplication` | CRM Analytics (Tableau CRM) application. Heavy (weight 50). |
| `WaveDashboard` | CRM Analytics dashboard. |
| `WaveDataflow` | CRM Analytics dataflow definition. |
| `WaveLens` | CRM Analytics lens. |
| `WaveRecipe` | CRM Analytics recipe. |

### 9.5 Security and identity (denied types)

These types are on the sf-clean-room deny list. They are documented here to explain what each contains.

| Type | Category | What the metadata contains |
|---|---|---|
| `Profile` | Operational deny | Per-object/field/permission settings for a user profile. Wildcard retrieve is not supported. |
| `PermissionSet` | Operational deny | Additive permission grants. |
| `PermissionSetGroup` | Operational deny | Groups of permission sets. |
| `Role` | Operational deny | User role hierarchy definitions. |
| `ConnectedApp` | Sensitivity deny | OAuth Consumer Key (Client ID), callback URLs, contact email, OAuth policy settings. Consumer secret is not in the metadata but Consumer Key is. |
| `AuthProvider` | Sensitivity deny | IdP endpoint URLs, consumer key/secret for SSO providers (values vary by provider type), registration handler Apex class reference. |
| `NamedCredential` | Sensitivity deny | Integration endpoint URL, authentication type and credential parameter name references. |
| `ExternalCredential` | Sensitivity deny | Authentication parameter graph for external services; includes principal and permission set mappings. |
| `CustomMetadata` | Sensitivity deny | Custom metadata type records as XML files. The DeveloperName (which becomes part of the filename) can itself be a credential value. Field values are in the XML body. |
| `Certificate` | Operational deny | Certificate body (PEM-encoded public certificate). Private keys are not included in the metadata. |
| `SamlSsoConfig` | Operational deny | SAML SSO configuration including IdP endpoint URLs and certificate references. |
| `Document` | Sensitivity deny | Arbitrary uploaded files (binary content, foldered type). Content type is unrestricted. |
| `StaticResource` | Sensitivity deny | Arbitrary uploaded archives and binary assets. Retrieved as a `.resource` binary plus `-meta.xml`. |
| `ContentAsset` | Sensitivity deny | CMS content asset metadata. Retrieved as binary content. |

### 9.6 Configuration

| Type | Notes |
|---|---|
| `CustomLabel` | Custom label definitions. |
| `CustomPermission` | Custom permission definitions. |
| `RemoteSiteSetting` | Remote site whitelist entries (endpoint URLs). |
| `Group` | Public group definitions. |
| `Queue` | Queue definitions. |
| `EmailTemplate` | Email templates. Foldered type. |
| `SharingRules` | Sharing rule definitions per object. |
| `Network` | Experience Cloud (Community) site configuration. On operational deny list (fragile, partial-retrieve prone). |
| `ExperienceBundle` | Full Experience Cloud site bundle. Heavy (weight 500). |
| `SiteDotCom` | Salesforce Sites bundle. Heavy (weight 200). |

---

## 10. Published artefacts from `get_metadata`

After a successful run, the `--path` directory contains:

| Artefact | Description |
|---|---|
| `package.xml` | The published manifest. Lists every component type and API name that was successfully retrieved. Moved into `--path` **last** — its presence signals a complete publish. Also serves as the `<types>/<version>` source of truth for what the folder contains. |
| `<directoryName>/` | One subdirectory per retrieved metadata type, matching the Salesforce `directoryName`. Contents mirror the retrieve zip layout described in §6. |
| `_skipped-types.csv` | One row per type that could not be enumerated or retrieved due to a permission gap. Columns: `type`, `bucket`, `components_requested`, `components_retrieved`. Header-only when no types were skipped. Never contains deny-listed types. |
| `_path_renames.csv` | One row per file whose path was rewritten during extraction (illegal characters, trailing dots/spaces, over-long components). Columns: `original`, `extracted`. Not written if no renames occurred. |
