# 03 — Metadata Export under Limited Permissions: Goals and Requirements

**Status:** Ideation. Input to a future `03-design-2.1.md`.
**Governed by:** [`00-design-principles.md`](00-design-principles.md) — read it first.
**Companions:** [`01-metadata-ideation.md`](01-metadata-ideation.md) and the v1 contract [`../01-design-v1.md`](../01-design-v1.md). The change targets `get_metadata`; it does not affect `get_records`.

This document sits one altitude above a future design. The design will say *what the v2.1 tool does and how*; this says *what problem v2.1 solves, for whom, and which requirements that design must satisfy*. It exists so a later reader can judge whether a proposed change still serves the original goals.

---

## 1. The problem

`get_metadata` v1 assumes a full-permission operator. In practice, the operator's authenticated Salesforce user is often a **limited-permission identity** chosen by the customer's admin — read on most things, blocked on a long tail of metadata types. The tool's current behaviour on the first per-type enumeration error is to **abort the whole run**. The result: every limited-permission operator must escalate back to a maintainer or to the customer's admin to obtain access to a type they may not need anyway. This is a B2 anti-pattern (forcing a human decision when the tool could resolve safely).

The failure modes are not exotic — they appear within minutes of pointing v1 at a real customer prod org:

1. **`INSUFFICIENT_ACCESS` on enumeration.** `describeMetadata` advertises a type the user cannot `listMetadata` on (e.g. `DecisionTable` for users without Business Rules Engine access).
2. **`INVALID_TYPE: Cannot use X in this organization`.** Returned for types the org doesn't license or the user can't see (e.g. `ApexClass`, `ApexTrigger` for users without "Author Apex" — they are hidden from `describeMetadata` AND `listMetadata`).
3. **CLI registry mismatch** (observed in the CLI-based POC; **does not occur on sf-clean-room's SOAP path**). The `sf` CLI's `project retrieve start` validates against a local static type registry and fails with `Missing metadata type definition in registry for id 'X'` for new/rare types. sf-clean-room POSTs to the SOAP Metadata API directly, which has no such client-side registry — so this failure mode is out of scope for the implementation, though the `registry_miss` bucket is reserved in the published schema (see §4.1).
4. **Folder-mounted enumeration gap.** `Report`, `Dashboard`, `EmailTemplate` need a two-step `listMetadata` (folder type → per-folder listing). A single-step enumeration returns zero components and the type is silently absent from the publish.
5. **Hidden types absent from `describeMetadata`.** `ApexClass` and `ApexTrigger` simply don't appear in the describe output for users without view-source permissions, so they never enter the enumeration plan and the tool has no way of knowing they exist.
6. **Partial retrieve.** SF returns fewer components than the manifest requested (FLS / record-type / object-permission filters drop them). The retrieve succeeds; the published folder is quietly incomplete.

Each of these is the *same shape of harm*: the run either aborts when it could have continued, or silently under-publishes when it should have surfaced the gap. The unit of failure is **the type**, not the run; the response should match the unit.

The job: make `get_metadata` resilient to per-type permission and capability gaps **without weakening the deny list or any other A3-zero-judgment safety property**. The full-permission operator's experience does not change; the limited-permission operator gets a usable artefact with a self-describing gap report instead of a wall.

## 2. Who the actors are

Same as v1 ([`01-metadata-ideation.md`](01-metadata-ideation.md) §2). The new twist is the **authenticated identity** the operator uses:

- **Full-permission identity.** Sysadmin-or-equivalent. Today's expected case, still supported with zero behaviour change.
- **Limited-permission identity.** Custom profile / permission set with a narrowed metadata surface — e.g. Modify Metadata granted, but no view on a handful of types (DecisionTable, Apex source, etc.). The new supported case.

The operator/maintainer split (v1 §2) is unchanged: the operator runs the tool, never weakens it; the deny list and other source-controlled lists remain source-only.

## 3. Goals

1. **Per-type fault tolerance.** A failure on one type's enumeration or retrieve must not abort the whole run. The run continues, records the failure, publishes the rest.
2. **Self-describing publishes.** The artefact carries a complete account of what was attempted, what succeeded, and what was skipped — so a consumer never has to guess what is missing.
3. **No safety drift.** The deny list, the publish-sentinel discipline, and the prohibition on operator-overridable safety surfaces are unchanged. Tolerance is added; no safety property is weakened (principle A3).
4. **Full-permission identical behaviour.** A full-permission run produces the same published folder it produced under v1 (modulo the new self-describing artefacts). Limited permissions are a *graceful degradation*, not a new mode.
5. **Symmetric coverage gains.** While the resilience work is in flight, close the gaps a careful v1 run would also benefit from — folder-mounted enumeration, always-probe types `describeMetadata` may hide, partial-retrieve detection. These are not limited-permission features; they are correctness fixes.
6. **No new operator-tunable safety surfaces.** Per-type tolerance is automatic (B2). There is no `--skip-errors` flag, no `--strict` flag, no override list of types-to-tolerate-or-not. The operator does not choose between "abort" and "continue"; the tool resolves to "continue, recorded".

## 4. Requirements

### 4.1 Functional

- **Skip-and-log on per-type enumeration errors.** `listMetadata` failures classified into known buckets — `INSUFFICIENT_ACCESS`, `INVALID_TYPE`, and a catch-all `unknown` — are recorded (verbatim SOAP message to the audit log) and the run continues. No bucket aborts.
- **Always-probe list.** A source-controlled set of metadata types known to be hidden from `describeMetadata` for users lacking view-source permissions (`ApexClass`, `ApexTrigger`, `StandardValueSet`, and any future addition). The list is unioned with the `describeMetadata` output before filtering. Like the deny list, it is **source-only** — no CLI flag, no config entry, no env var. Adding to it is a maintainer change with review.
- **Folder-mounted enumeration.** For each type advertised by `describeMetadata` with `inFolder=true` (currently `Report`, `Dashboard`, `Document` [denied], `EmailTemplate`), call `listMetadata` for the folder type first, then `listMetadata` per folder for the inner type. The folder names themselves are also retrieved (folders are metadata too). The mapping inner → folder type is a documented constant.
- **Registry-miss is a CLI-only concern (reserved bucket).** The `Missing metadata type definition in registry` failure is raised by the `sf` CLI's `project retrieve start`, which validates against a local static type registry. sf-clean-room retrieves via the SOAP Metadata API directly, where any type the org's `describeMetadata` advertises is known to that org's API — so there is no registry to miss and no pre-flight strip is needed. The `registry_miss` bucket stays in the published schema, reserved and forward-compatible, but is never populated on the SOAP path. (Design §3.4.)
- **Partial-retrieve detection (component-accurate).** A SOAP retrieve returns a zip whose own `package.xml` lists the components actually included. Compare the **returned** members to the **requested** members, per type — the same unit on both sides, immune to the file-per-component ratio. Any per-type shortfall is recorded as `partial_retrieve` (with both counts) in the audit and the published `_skipped-types.csv`, not as a fatal error. The published `package.xml` is built from the retrieved members, so it never overstates.
- **Published skip log.** A new sentinel-published artefact, `_skipped-types.csv`, listing every non-denied type the run attempted but did not fully include, with the bucket and (for partial retrieves) the requested/retrieved counts. **Verbatim error detail goes to the audit log, not this published file** (v1 §9: diagnostics live in the audit, not the consumer folder). Written even when empty (header-only) so a consumer can distinguish "nothing skipped" from "no skip information published".

### 4.2 Non-functional / safety invariants (unchanged from v1, restated)

- **Deny list is source-only.** Unchanged. No new flag widens it.
- **Always-probe list is source-only.** Treat with the same rigor as the deny list — adding a type is a maintainer change, not an operator choice (principle A3).
- **No CLI surface widening.** `get_metadata`'s flags stay exactly as v1: `--org-alias`, `--path`, `--dry-run`. Resilience is automatic; no `--skip-errors` knob (B2).
- **Help reflects the new behaviour.** Per-command help text documents the skip-and-log discipline and points at the new `_skipped-types.csv`. Help text is still generated from source constants — drift between help and behaviour remains a correctness bug.
- **Sentinel rule unchanged.** `package.xml` is still the last file moved into `--path`. Consumers' acceptance rule is unchanged: see `package.xml`, you may read.
- **Fail-closed for genuine blockers.** Authentication failure, complete `describeMetadata` failure, complete retrieve failure (every batch errored), publish-step failure, and any attempted bypass of the deny list still abort. Only **per-type** errors degrade gracefully.
- **Regression testing is part of the change (principle C7).** v2.1 ships with offline tests for every new path (skip-and-log buckets, always-probe union, folder fault tolerance, partial-retrieve diff, skip-log CSV, publish-before-sentinel) and a live full-permission run against the configured test org; `regression-testing.md` is updated in the same change with the `_skipped-types.csv` artefact and its checks. The existing v1/v2 suite stays green.

### 4.3 The output contract (extension to v1 §9)

A consumer reading a `--path` containing `package.xml` may assume **everything v1 already promises**, plus:

- A `_skipped-types.csv` exists at the publish root. Its header is fixed: `type,bucket,components_requested,components_retrieved`.
  - `bucket ∈ {insufficient_access, invalid_type, registry_miss, partial_retrieve, unknown}` (`registry_miss` reserved; never populated on the SOAP path).
  - `components_requested`/`components_retrieved` populated only for `partial_retrieve` rows; empty otherwise.
  - **No deny-listed type ever appears here** — denied types are filtered before enumeration, so they are never attempted and never recorded (preserves v1 §9's "don't advertise excluded sensitive types").
  - Verbatim error detail is in the audit log, not this file.
- `package.xml` reflects what was **retrieved successfully** (including partial-retrieve types, at the retrieved member count). It does not list members of types in `_skipped-types.csv` that produced zero retrieved components.
- No type from the v1 §6 deny list is present (unchanged).

The consumer does not need new logic to read the folder — if it ignores `_skipped-types.csv`, behaviour is identical to v1 for the components that did make it. The file is there for consumers that *do* care to know what is missing.

## 5. Out of scope for v2.1 (and why)

- **Per-type retry / backoff for transient errors.** A `429` or transient `UNABLE_TO_LOCK_ROW` is different from a permission gap and warrants different handling; defer to a future iteration if the limited-permission path proves stable.
- **Selective access escalation.** The tool does not propose "if you grant X, you'd get Y more components." That would be a wrapper / report concern; staying out of it keeps the tool single-purpose.
- **Allow-listing within deny-listed types.** Out of scope here exactly as it is for v1 (`CustomMetadata` namespace allow-list etc.). Resilience to permission gaps is orthogonal to relaxing the deny list.
- **Resilience for `get_records`.** v2 (records) has a fundamentally different safety model (field-level classification, not type-level denial) and is governed by [`02-data-download.md`](02-data-download.md). Its tolerance to limited permissions is its own design question.

## 6. How a v2.1 design will satisfy the goals (traceability)

| Goal | Mechanism the future design will use |
|---|---|
| Per-type fault tolerance | Skip-and-log enumeration; component-accurate partial-retrieve detection (§4.1) |
| Self-describing publishes | `_skipped-types.csv` as a published artefact; audit log captures the same with more detail (§4.1, §4.3) |
| No safety drift | Always-probe list source-controlled like the deny list; sentinel unchanged; no new flags (§4.2) |
| Full-permission identical behaviour | A full-permission run produces an empty `_skipped-types.csv` and an unchanged `package.xml` |
| Symmetric coverage gains | Folder enumeration; always-probe list; partial-retrieve detection — all benefit any operator (§4.1) |
| No new operator-tunable safety surfaces | Tolerance is automatic; the CLI surface is unchanged (§4.2) |

## 7. Open questions

1. **Always-probe list scope.** The minimum useful set is `ApexClass`, `ApexTrigger`, `StandardValueSet`. Beyond that, what is the test we apply before adding a type? Proposal: a type is added only if a documented Salesforce permission gap is known to hide it from `describeMetadata` for a profile other tools are routinely run as. Anything speculative stays out — bloat in this list costs a per-run probe and dilutes the signal in `_skipped-types.csv`.
2. *(Resolved.)* **Registry-miss handling.** Originally proposed as a CLI strip-and-retry pre-flight. Resolved: sf-clean-room retrieves via SOAP, which has no client-side registry, so the pre-flight is unnecessary and omitted; the `registry_miss` bucket is reserved for forward-compatibility (§4.1, design §3.4).
3. **Partial-retrieve attribution.** The returned `package.xml` gives an exact per-type member diff, so naming *which* members dropped is now feasible (returned vs requested member sets). The current contract records the gap at the type level (`components_requested` vs `components_retrieved`); per-member naming is deferred until a consumer asks, but the data is available cheaply if wanted.
4. **Skip log naming.** `_skipped-types.csv` aligns with the underscore-prefixed metadata-of-the-publish convention already used by `_path_renames.csv`. Confirm this is the right name before any contract is shipped — renames after publication are expensive.
5. **Folder-mounted retrieval for newly added foldered types.** `describeMetadata` advertises `inFolder=true`, but does the mapping inner → folder type need to be hardcoded forever? Salesforce has not added a foldered type in several API versions, but if one appeared, the constant would silently miss it. Proposal: derive the folder type name as `<inner>Folder` and fall back to the constant only on disagreement; surface the disagreement in the audit.
