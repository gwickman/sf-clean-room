# SF Clean Room — Design (v2.1: `get_metadata` under limited permissions)

**Status:** Draft.
**Scope:** A minor evolution of the family. v2.1 extends `get_metadata` (v1) so that limited-permission identities produce a usable, self-describing publish instead of aborting on the first per-type permission gap. v2 (`get_records`) is unchanged; v1 (`get_metadata`) full-permission behaviour is unchanged except for the new self-describing artefacts in §8.
**Principles:** [`ideation/00-design-principles.md`](ideation/00-design-principles.md). **Goals/requirements rationale:** [`ideation/03-limited-permissions-metadata.md`](ideation/03-limited-permissions-metadata.md). **Authoritative v1 contract:** [`01-design-v1.md`](01-design-v1.md). **Decision history:** [`docs-change-log.md`](docs-change-log.md).
**Companion plan:** [`03-plan-2.1.md`](03-plan-2.1.md).

This document is the authoritative v2.1 contract. It states what the tool does; the ideation doc states why.

---

## 1. Purpose

`get_metadata` under v2.1 produces the same safe published folder it produced under v1, but when the authenticated identity lacks visibility on individual metadata types, the run continues, records each gap in a published `_skipped-types.csv`, and publishes the rest.

The change is structural, not policy. Tolerance applies only to **per-type** errors. The deny list (v1 §6), the publish sentinel, the prohibition on operator-tunable safety surfaces, and every other v1 invariant remain. A run that fails to authenticate, fails to describe metadata at all, fails every retrieve batch, or tries to bypass the deny list still aborts.

A full-permission identity sees no difference except the new `_skipped-types.csv` (empty, header-only). A limited-permission identity gets a usable artefact instead of a wall (principle B2).

## 2. Safety model

v2.1 is governed by the same principles as v1. The only delta is **A3 applied at finer granularity**: per-type enumeration / retrieve errors are *not* zero-judgment harms — they are signals about the identity's metadata visibility. The tool resolves them with a safe default ("skip the type, record it") and continues (B2, B4).

What is **mechanical and non-negotiable** (unchanged from v1):

- **Read-only.** The pipeline never mutates Salesforce. (A4)
- **Exclude at source.** Denied types are filtered before any `retrieve`. They never transit the network, never reach temp, never reach the published folder. (A2)
- **Deny list is source-only.** No CLI flag, env var, or config entry loosens it. (B4 floor)
- **Always-probe list is source-only.** New in v2.1. Joined to `describeMetadata` output before filtering. Treated with the same rigor as the deny list — a maintainer change with review, never an operator choice.
- **Sentinel publishes are last.** `package.xml` is still the consumer's go-signal. `_skipped-types.csv` is moved into `--path` *before* `package.xml`.

What is **automatic and self-resolving** (new in v2.1):

- A per-type `listMetadata` error in one of the recognised buckets (`INSUFFICIENT_ACCESS`, `INVALID_TYPE`, partial-retrieve, unknown) → skip the type, record the bucket (verbatim SOAP message to the audit log), continue.
- A retrieve that returns fewer components than the manifest asked for → record the gap as `partial_retrieve`, do not abort.

(The `registry_miss` bucket is part of the documented schema but is **inert under sf-clean-room's SOAP retrieve path** — see §3.4 — so it is reserved, not populated.)

There is no operator surface for any of this. Tolerance is the only behaviour; "abort on every per-type error" is not a configurable mode. (B2)

## 3. Behaviours added in v2.1

### 3.1 Per-type fault tolerance during enumeration

The pipeline's filter stage (v1 §5.2) was previously a wholesale operation on the enumeration map. In v2.1, **enumeration itself is fault-tolerant per type**:

- `listMetadata` returning `INSUFFICIENT_ACCESS` or `INVALID_TYPE` → record the bucket, drop the type from the plan, continue.
- `listMetadata` returning any other error → record under bucket `unknown`, drop the type, continue.

Recording uses the verbatim CLI/SOAP message (no paraphrasing), bounded to a documented length so the audit doesn't bloat on pathologically long error strings.

### 3.2 Always-probe list

A source-controlled set of metadata types known to be hidden from `describeMetadata` for users lacking specific view-source permissions. Initial members:

| Type | Why it can be hidden |
|---|---|
| `ApexClass` | "Author Apex" / "View All Data" required for visibility; `describeMetadata` omits the type entirely for users without these. |
| `ApexTrigger` | Same as `ApexClass`. |
| `StandardValueSet` | Hidden from some custom profiles even when value sets are queryable. |

The list is unioned with the `describeMetadata` output **before** filtering. Types that the identity also cannot enumerate fall into the §3.1 skip path; types it *can* enumerate are kept. The cost is one `listMetadata` per hidden type per run.

Maintenance: adding a type requires a documented permission gap and a maintainer change with review. The list is not runtime-overridable.

### 3.3 Folder-mounted enumeration (correctness fix)

Inner types whose `describeMetadata` entry carries `inFolder=true` need a two-step `listMetadata`: first to enumerate the folder type, then per folder to enumerate the inner type. The mapping is:

| Inner type | Folder type | Notes |
|---|---|---|
| `Report` | `ReportFolder` | Add synthetic `unfiled$public` so personal-folder reports are included. |
| `Dashboard` | `DashboardFolder` | As above. |
| `EmailTemplate` | `EmailFolder` | Folder names retrieved alongside inner names — folders are metadata too. |
| `Document` | `DocumentFolder` | **Deny-listed; not enumerated.** |

The mapping is currently hardcoded but cross-checked against `<inner>Folder` at runtime: a disagreement is recorded in the audit. This is a correctness gain that benefits any operator, not just limited-permission ones — under v1 a folder-mounted type would otherwise silently return zero components.

### 3.4 CLI registry-miss: not applicable to the SOAP path

The "registry-miss" failure (`Missing metadata type definition in registry for id 'X'`) is raised by the `sf` CLI's `project retrieve start`, which validates a manifest against its **local static type registry** before submitting to Salesforce. New or rare types absent from an older CLI version surface here. The proof-of-concept that motivated v2.1 used the CLI and hit this on six types.

**sf-clean-room does not use the CLI to retrieve.** It builds `package.xml` and POSTs to the SOAP Metadata API directly (`soap.py`, `retrieve.py`), using the CLI only to resolve the session token. There is no local type registry in that path: any type advertised by the org's own `describeMetadata` is, by construction, known to that org's Metadata API. A type the API genuinely cannot serve surfaces as `INVALID_TYPE` / `INSUFFICIENT_ACCESS` on `listMetadata` and is handled by §3.1.

Consequently there is **no strip-and-retry pre-flight** in sf-clean-room, and the `registry_miss` bucket is **reserved but never populated** under the SOAP path. It remains in the documented schema (§3.6) so the published contract is stable and forward-compatible: were a CLI-based retrieve ever added, registry-missed types would populate this bucket without a schema change.

### 3.5 Partial-retrieve detection

A SOAP `retrieve` returns a zip whose own `package.xml` lists the components Salesforce **actually** included — which, under a limited identity, can be far fewer than the manifest requested (FLS / object-permission / record-type filters drop members server-side). After each batch retrieve, the pipeline parses the **returned** `package.xml` from the zip and compares its members per type to the **requested** manifest members per type. The comparison is therefore *component-accurate*, not a raw file count: it counts the same unit on both sides and is immune to the file-per-component ratio (a class is two files, a bundle is many, an object is one) that would make a disk file-count misleading.

A per-type shortfall is recorded as a `partial_retrieve` row in `_skipped-types.csv`:

| Field | Meaning |
|---|---|
| `components_requested` | Member count for this type in the requested manifest. |
| `components_retrieved` | Member count for this type in the returned `package.xml`, summed across batches. |

Per-type partial retrieve is **not fatal**: it is the same shape of harm as the §3.1 per-type errors and resolves the same way (continue, record). It surfaces in the audit (with full detail) and in `_skipped-types.csv` (counts only — see §3.6) so consumers can detect it. The published `package.xml` is assembled from the *retrieved* members, so it never overstates what is present.

### 3.6 Published `_skipped-types.csv`

A new published artefact at the publish root. Fixed schema:

```
type,bucket,components_requested,components_retrieved
```

- `bucket ∈ { insufficient_access, invalid_type, registry_miss, partial_retrieve, unknown }`.
- `components_requested` / `components_retrieved` populated only for `partial_retrieve`; empty otherwise.

**Verbatim error detail is deliberately *not* in this published file.** Following v1 §9 (the published folder carries the artefacts a consumer reads; diagnostic detail lives in the audit log), the raw SOAP message for each skip is written to the **audit log** — at a fixed system location, for human review — not into the consumer-facing publish folder. The published CSV says *which* type was skipped and *which bucket* (enough for a consumer to know what is missing and why, categorically); the audit log says *exactly* what Salesforce returned. This keeps any incidental detail in an error string (an instance hint, a long server message) out of the folder that downstream automated consumers read.

Always written. An empty publish (header only) means "no types skipped" and is the expected state for a full-permission identity.

## 4. CLI surface

**Unchanged from v1.** `get_metadata` still has exactly three flags:

```
sf-clean-room get_metadata --org-alias <alias> --path <dir> [--dry-run]
```

No `--skip-errors`, no `--strict`, no `--include-hidden-types`, no override list. The tolerance discipline is the only behaviour; making it operator-tunable would re-introduce the B2 anti-pattern the change is designed to remove. Help text reflects the new behaviour; help is still generated from source constants so it cannot drift.

## 5. Pipeline

```
[1] enumerate  → [2] filter  → [3] batch  → [4] retrieve + extract (to temp)
       │              │                              │
       └ §3.1/§3.2/§3.3 (skip-and-log,              └ [4.b] partial-retrieve check
         always-probe, folder two-step)                   (returned vs requested package.xml)
                                 → [5] scrub stages (still no-op)
                                 → [6] publish (skip log before the sentinel)
```

The new and changed elements:

- **Enumerate** absorbs §3.1 (per-type skip-and-log), §3.2 (always-probe union), and §3.3 (folder-mounted two-step). The output is `metadata_type → [fullName, ...]` plus a `SkipLog`.
- **Partial-retrieve check (4.b)** is new: §3.5 compares the returned `package.xml` members to the requested members, per type per batch. Shortfalls are added to the `SkipLog` with bucket `partial_retrieve`.
- **Publish (6)** is extended: `_skipped-types.csv` is moved into `--path` *before* `package.xml`. `package.xml` remains the sentinel.

There is no pre-flight stage (§3.4: registry-miss is a CLI-only concern, N/A to the SOAP path). The scrub stage list, batch weighting, temp area, and audit log are otherwise unchanged.

## 6. Failure modes (fail-closed for genuine blockers, graceful for per-type)

| Failure | Behaviour |
|---|---|
| Authentication / session unavailable | Abort. Unchanged. |
| `describeMetadata` fails outright | Abort. The tool cannot produce a plan; this is a zero-judgment blocker. |
| A retrieve batch fails wholly | Abort. (Same as v1.) The unit is the batch, not the type — losing a batch loses the publishability of every type in it. The audit names the batch composition so a re-run can be narrowed if needed. |
| `_skipped-types.csv` move fails during publish | Abort. The sentinel rule depends on `package.xml` arriving last; `_skipped-types.csv` is a contract artefact too and must be present before `package.xml`. |
| Scrub stage returns findings (future) | Abort. Unchanged. |
| Publish step fails between empty and sentinel-placed | v1 §8 atomicity gap, unchanged. Sentinel absence is the consumer's signal. |
| `--dry-run` against a limited-permission identity | Print the planned batch composition AND the would-be `_skipped-types.csv` contents. Exit zero. |

The salient line: **per-type errors degrade; per-run errors abort.**

## 7. Exit codes (unchanged)

- `0` — completed publish. `_skipped-types.csv` may be non-empty; this is not a failure (B4).
- non-zero — any abort. Read `_skipped-types.csv` (if present) and the audit log for detail.

## 8. Output contract (extension of v1 §9)

A consumer reading a `--path` that contains `package.xml` may assume **everything v1 §9 promises**, plus:

- `_skipped-types.csv` exists at the publish root, header `type,bucket,components_requested,components_retrieved`.
- No `bucket` value outside the documented set appears.
- **No deny-listed type ever appears in `_skipped-types.csv`.** Deny-listed types (v1 §6) are filtered before enumeration, so they are never attempted, never error, and never recorded — the skip log only ever names *non-denied* types the identity could not fully retrieve. This preserves v1 §9's intent that the tool does not advertise which sensitive categories exist.
- `package.xml` reflects what was retrieved successfully (including partial-retrieve types, at the retrieved member count). Types listed in `_skipped-types.csv` with zero retrieved components do not appear in `package.xml`.
- Verbatim error detail for each skip is in the audit log, not in `_skipped-types.csv` (§3.6).

The consumer's read logic for the components themselves is unchanged. Reading `_skipped-types.csv` is optional; ignoring it still yields v1-compatible behaviour for the components that did make it.

## 9. Backwards compatibility

A run against a full-permission identity produces:

- A `package.xml` with the same components v1 would have produced, modulo the §3.3 folder-mounted correctness gain (newly included for any run, not just limited-permission).
- An empty `_skipped-types.csv` (header only).
- The same `_path_renames.csv` semantics as v1.
- The same audit log location and contents, with the additional skip-bucket detail.

A run against a limited-permission identity produces:

- A `package.xml` listing every component that was retrieved (including partial-retrieve types at their retrieved count).
- A non-empty `_skipped-types.csv` documenting every gap.
- Audit log and `_path_renames.csv` semantics unchanged.

No consumer that reads only `package.xml` and the metadata folders needs to change. A consumer that consults `_skipped-types.csv` gains visibility into the gaps without changing how it reads the rest.

## 10. Deliberate simplifications (v2.1-initial), with rationale

- **No retry / backoff for transient errors.** A `429` or `UNABLE_TO_LOCK_ROW` on `listMetadata` lands in bucket `unknown` and the type is skipped. Transient-vs-permanent distinction is a future iteration; conflating them under `unknown` is honest about the tool's current ability to tell them apart.
- **Skip log is a flat CSV, not a structured report.** A CSV with five columns covers every observed failure mode and stays trivially parseable. A richer structured log (e.g. JSON with per-type stack traces) belongs in the audit log, not the published artefact.
- **Folder-mapping is a constant, with runtime cross-check, not a runtime derivation.** Salesforce has not added a foldered type in several API versions; hardcoding is correct now. The runtime cross-check (`<inner>Folder` agreement) is the early-warning if that ever changes.
- **The always-probe list is short by design.** Three types in v2.1. Every addition is a per-run cost (one `listMetadata` probe) and a row of noise in `_skipped-types.csv` when the type is genuinely absent from the org. The bar for adding is the documented permission gap, not "might be useful".

---

## Appendix A — Implementation plan (summary)

Detailed step-by-step in [`03-plan-2.1.md`](03-plan-2.1.md). High-level:

1. **`constants.py`:** add `ALWAYS_PROBE_TYPES`, `SKIP_BUCKETS`, `MAX_SKIP_DETAIL_LEN`, `SYNTHETIC_FOLDERS`. (`FOLDERED` already exists for folder mapping; no `MAX_REGISTRY_MISS_STRIPS` — no pre-flight.)
2. **`enumerate_md.py`:** per-type `listMetadata` made fault-tolerant; bucket classification of errors; union with `ALWAYS_PROBE_TYPES`; folder two-step already present — add fault tolerance + synthetic folders + folder-as-type.
3. **`pipeline.py`:** post-retrieve partial-retrieve check (returned vs requested `package.xml`); thread the `SkipLog` through to publish. No pre-flight stage.
4. **`publish.py`:** generalise the sentinel-publish helper to accept non-sentinel artefacts written **before** the sentinel (so `_skipped-types.csv` lands before `package.xml`).
5. **`audit.py`/pipeline logging:** record `skip_bucket` (with full verbatim detail), `partial_retrieve`, and a folder-enum summary; one-line skip summary on the stderr tee.
6. **`cli.py` / help:** regenerate per-command help from source constants — `--help` for `get_metadata` documents `_skipped-types.csv` (its schema, detail-in-audit, empty-on-full-permission) and the skip-and-continue discipline.
7. **Tests (principle C7):** offline (mock the bucket-failure paths, partial-retrieve diff, folder enumeration, skip-log CSV, publish-before-sentinel); live against the configured test org (full-permission → header-only skip log, unchanged `package.xml`). **Update `regression-testing.md`** with the new artefact and checks in the same change.
8. **Docs:** add an entry to `docs-change-log.md`.

## Appendix B — Glossary additions

| Term | Meaning |
|---|---|
| Bucket | One of the documented categories a per-type failure resolves into: `insufficient_access`, `invalid_type`, `registry_miss` (reserved; CLI-only, never populated under SOAP), `partial_retrieve`, `unknown`. |
| Partial retrieve | A retrieve that succeeded but whose returned `package.xml` lists fewer members than the manifest requested for some type. |
| Always-probe list | The source-controlled set of metadata types unioned with `describeMetadata` output before filtering, covering types `describeMetadata` may hide from limited-permission identities. |
