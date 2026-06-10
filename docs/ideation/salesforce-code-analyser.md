# Salesforce Code Analyzer — Output Reference

A field-level reference for the artefacts produced by running the **Salesforce Code Analyzer** (`sf code-analyzer run`) over a local Salesforce metadata folder.

For each field, this document gives:

- The data type.
- A factual description of what the field stores.
- A "Data content to inspect" note where the field carries free text or content derived from the analysed source.

The intent is to let a reader classify the content themselves. Where the tool emits enumerated values, those are listed verbatim.

---

## 1. Source and format

- **Source command:** `sf code-analyzer run --target <metadata-folder> --output-file <out>.html --output-file <out>.csv --output-file <out>.json` — a single invocation of the Salesforce CLI plug-in **Code Analyzer**, run against a directory containing previously-retrieved Salesforce metadata (Apex classes, triggers, LWC, Aura, Visualforce, flows, static resources, etc.).
- **What the tool does:** wraps multiple underlying static-analysis engines and emits a consolidated report. The engines run by default are:
  - **PMD** — Apex / Java-family static analysis (most violations on a typical Salesforce codebase).
  - **retire-js** — known-vulnerability scan against JavaScript dependencies in static resources.
  - **ESLint** — JavaScript / TypeScript linting (LWC, Aura controllers).
  - **Flow** — Salesforce Flow analyser (analyses `.flow` definitions).
  - **CPD** — Copy-Paste Detector (PMD's duplicate-code finder).
  - **regex** — Salesforce-shipped pattern checks (e.g. old-API-version detection).
- **Output files (three, written side-by-side):**
  - `code_analyser_results_<org_alias>.html` — interactive UI rendering of the same data the JSON contains.
  - `code_analyser_results_<org_alias>.csv` — flat, one-row-per-violation table.
  - `code_analyser_results_<org_alias>.json` — full structured report including run metadata, engine versions, severity counts, and the violation list.
- **Authoritative reference:** Salesforce Code Analyzer documentation — <https://developer.salesforce.com/docs/platform/salesforce-code-analyzer/overview>.

The Code Analyzer plug-in version determines the available engines and the exact schema; the reference below corresponds to plug-in 5.x (`code-analyzer` 0.33+).

## 2. What the tool reports

The analyser walks the target folder, classifies each file by language (Apex, JavaScript, TypeScript, Visualforce, Aura, LWC, Flow XML, static resource), runs the relevant engines, and emits one violation row per finding. Violations are scored on a Salesforce-defined severity scale **1–5** where 1 is highest severity.

A single run can produce tens of thousands of violations on a mature Salesforce codebase (the sampled run for this reference contained 44,189 violations).

---

## 3. Schema — CSV

One header row plus one row per violation. Columns:

| Column | Type | What it stores |
|---|---|---|
| `rule` | string | The rule name fired (e.g. `LibraryWithKnownHighSeverityVulnerability`, `AvoidOldSalesforceApiVersions`, `no-unused-vars`, `ApexDoc`, `DetectCopyPasteForVisualforce`, `PreventPassingUserDataIntoElementWithSharing`). |
| `engine` | string | One of: `pmd`, `retire-js`, `eslint`, `flow`, `cpd`, `regex`. |
| `severity` | int | 1–5. (Per the sampled run, 1 was unused; 2–5 were populated.) |
| `tags` | string | Comma-separated tag list. Observed values include: `Apex`, `BestPractices`, `CodeStyle`, `Design`, `Documentation`, `ErrorProne`, `HTML`, `JavaScript`, `Javascript`, `LWC`, `Performance`, `Recommended`, `SLDS`, `Security`, `TypeScript`. |
| `file` | string | Path of the analysed file, **relative to the directory from which `sf` was invoked**. The path encodes the analysed-folder layout (typically `<analysed-folder>/<metadata-type>/<component>/<file>`). |
| `startLine` | int | 1-indexed line where the violation starts. |
| `startColumn` | int | 1-indexed column. |
| `endLine` | int | Empty for single-point violations; populated for block violations (PMD/CPD/regex). |
| `endColumn` | int | Same as endLine. |
| `message` | string | Free-text message from the engine. May embed source-derived identifiers (variable names, API versions, library names, file paths inside zipped static resources). May contain embedded JSON for richer engines (`retire-js` includes a CVE / GHSA-ID JSON blob inside the message string). May span multiple lines (CSV-escaped). |
| `resources` | string | Comma- or semicolon-separated list of URLs pointing to the rule's documentation page (Salesforce, PMD, retire.js, ESLint, etc.). |

## 4. Schema — JSON

Single top-level object. Keys:

| Key | Type | What it stores |
|---|---|---|
| `runDir` | string | Absolute path of the working directory from which the analyser was invoked. Identifies the machine layout. |
| `violationCounts` | object | Aggregate counts. Keys: `total` (int), `sev1`, `sev2`, `sev3`, `sev4`, `sev5` (int each). |
| `versions` | object | Engine versions used in this run. Keys observed: `code-analyzer`, `retire-js`, `regex`, `eslint`, `flow`, `pmd`, `cpd`. Values are semver strings. |
| `violations` | array | One element per finding. Schema below. |

### 4.1 `violations[]` element

| Key | Type | What it stores |
|---|---|---|
| `rule` | string | Rule name (same vocabulary as CSV `rule`). |
| `engine` | string | One of: `pmd`, `retire-js`, `eslint`, `flow`, `cpd`, `regex`. |
| `severity` | int | 1–5. |
| `tags` | array of string | Tag list. |
| `primaryLocationIndex` | int | Index into `locations[]` identifying the primary location (relevant for multi-location findings such as CPD duplicates). |
| `locations` | array | One or more locations (see below). PMD/ESLint/regex/Flow typically emit one; CPD emits multiple (one per duplicate block); retire-js emits one. |
| `message` | string | Free-text engine message. See §5 for content nature. |
| `resources` | array of string | URLs to the rule's documentation. |

### 4.2 `locations[]` element

| Key | Type | What it stores |
|---|---|---|
| `file` | string | Relative file path, same convention as the CSV `file` column. |
| `startLine` | int | 1-indexed start line. |
| `startColumn` | int | 1-indexed start column. |
| `endLine` | int | Optional — end line for block findings. |
| `endColumn` | int | Optional — end column. |
| `comment` | string | Optional — engine-supplied annotation about the location. Observed on Flow violations: short labels naming the Flow element involved (e.g. `cartId.cartId: Initialization`). |

## 5. Content of the `message` field

Message content varies markedly by engine. Across all engines the message reports *what was found*, not *what the source code is* — that is, the engine describes the violation in prose and may reference an identifier from the source, but does not embed the source body. Observed patterns:

| Engine | Average message length | What the message contains |
|---|---|---|
| `pmd` | ~50 chars | Short labels — `Missing ApexDoc comment`, `Avoid using global modifier`, `Cyclomatic complexity exceeds…`. May embed the Apex class / method name in some rules. |
| `eslint` | ~40 chars | Short labels embedding identifier names — `'component' is defined but never used.`, `'data' is assigned a value but never used.`. The variable / function name from the source is quoted. |
| `regex` | ~75 chars | Short narrative — `Found the use of a Salesforce API version that is 3 or more years old. Avoid using an API version that is <= 56.0.`. May embed the offending value (API version number). |
| `flow` | ~95 chars | Short narrative referencing Flow elements — `User controlled data flows into recordLookups element selector in run mode: SystemModeWithSharing`. Element names appear here and in the `comment` field of the location. |
| `cpd` | ~145 chars | Narrative + counts — `Duplicate code detected for language 'visualforce'. Found 2 code locations containing the same block of code consisting of 3161 tokens across 364 lines.`. No source body is quoted, but multiple `locations[]` are emitted pointing at the duplicated regions. |
| `retire-js` | ~360 chars (up to ~670) | Library name + version + a vulnerability description, plus an **embedded JSON blob** carrying `summary`, `CVE`, `githubID`, and references — e.g. `'DOMPurify v2.2.6' was found inside of the zipped archive in '<internal-zip-path>' which contains a known vulnerability. … {"summary": "…", "CVE": ["CVE-2024-…"], "githubID": "GHSA-…-…"}`. The internal path inside the zipped static resource is quoted verbatim. |

What the message field *does* contain, across engines:

- Identifier names from the analysed source (variables, methods, classes, Flow elements, Lightning components).
- Numeric values from the source where the rule checks against a threshold (API versions, complexity numbers, token counts).
- Library names and versions detected inside static resources.
- Vulnerability identifiers (CVE, GHSA-ID) and short vulnerability summaries from public vulnerability databases.
- File paths *inside* zipped static resources (e.g. `webruntime/view/<hash>/prod/<locale>/<viewname>`).

What the message field *does not* contain:

- Multi-line source-code bodies. Engines reference source via `(file, line, column)`, not by quoting the source.
- Customer record data — these are static-analysis tools that read code on disk; they do not execute it.
- Authenticated secrets — the analyser reads source; if the source itself contains a literal secret, the message does not quote it, although the rule's reference to a line and column lets a reader locate it in the source.

## 6. HTML output

The HTML file is a self-contained interactive renderer of the same data the JSON contains — tabular violation list, filters by engine / severity / tag, links into the source files relative to `runDir`. It does not introduce content beyond what the JSON has; it carries the same `file` paths, the same `message` strings, and the same `runDir`.

## 7. Volume

| Engine | Order of magnitude (sampled run with ~44k total violations) |
|---|---|
| `pmd` | tens of thousands (≈25k) — dominates total count on a typical Salesforce codebase. |
| `eslint` | tens of thousands (≈11k) — proportional to LWC / Aura JS volume. |
| `regex` | thousands (≈6k). |
| `retire-js` | thousands (≈1.7k) — per detected library × known vulnerability. |
| `cpd` | hundreds (≈530). |
| `flow` | hundreds (≈130) — proportional to Flow count. |
| **Total** | tens of thousands on a mature org; can exceed 100k. |

File sizes scale with violation count. The JSON is the largest (each violation carries `locations[]`, `message`, `resources[]`, `tags[]`); the CSV is smaller per-row; the HTML embeds the same data plus the renderer assets.

---

## 8. Sources

- Salesforce Code Analyzer documentation: <https://developer.salesforce.com/docs/platform/salesforce-code-analyzer/overview>
- Salesforce CLI Code Analyzer command reference: <https://developer.salesforce.com/docs/platform/salesforce-code-analyzer/guide/cli-reference.html>
- Engine sources:
  - PMD: <https://pmd.github.io/>
  - retire.js: <https://retirejs.github.io/retire.js/>
  - ESLint: <https://eslint.org/>
  - Salesforce Flow Scanner: <https://github.com/Force-DI/lightning-flow-scanner-core>
