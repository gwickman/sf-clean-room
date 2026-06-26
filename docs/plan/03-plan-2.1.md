# SF Clean Room — Implementation Plan (v2.1: limited-permissions metadata)

**Status:** Plan for the v2.1 implementation.
**Authoritative contract:** [`03-design-2.1.md`](../design/03-design-2.1.md). Where this plan and the design disagree, the design wins.
**Companion requirements:** [`03-limited-permissions-metadata.md`](../requirements/03-limited-permissions-metadata.md).

This is the executable plan for an implementation agent. It is ordered: each step builds on the previous. Where a step has a verification gate, the gate names the artefact the agent must inspect before moving on.

---

## 0. Pre-flight (one-time)

1. Confirm editable install (per [`regression-testing.md`](../regression-testing.md) §1) resolves to `src/`, not site-packages.
2. Run the full existing offline suite (`pytest -q`). **Gate:** every existing test passes before any v2.1 work begins. If any test is red on baseline, stop and surface to Grant — do not start on top of a broken tree.
3. Create the feature branch.

## 1. Constants (`src/sf_clean_room/constants.py`)

Add these as module-level constants, in the existing v2.1 comment block, source-only with the same rigor as the `DENY` frozenset. Note `FOLDERED` (inner → folder type) already exists and is reused; there is **no** `MAX_REGISTRY_MISS_STRIPS` (no pre-flight — see design §3.4).

```python
# v2.1 — limited-permissions metadata
ALWAYS_PROBE_TYPES = (
    "ApexClass",
    "ApexTrigger",
    "StandardValueSet",
)

# Synthetic folder names always included for foldered types
# (so personal / unfiled-public items are captured).
SYNTHETIC_FOLDERS = {
    "Report": ("unfiled$public",),
    "Dashboard": ("unfiled$public",),
}

# registry_miss is reserved (CLI-only; never populated on the SOAP path).
SKIP_BUCKETS = (
    "insufficient_access",
    "invalid_type",
    "registry_miss",
    "partial_retrieve",
    "unknown",
)

MAX_SKIP_DETAIL_LEN = 400  # chars; SOAP messages can be long (audit log only)
```

**Gate:** `pytest -q` still green (no behavioural change yet, just constants).

## 2. Skip-tracking type (new small module, e.g. `src/sf_clean_room/skip_log.py`)

A focused class holding the run's per-type skip events. Used by the enumerator, the pre-flight, the retrieve-checker, and the publisher.

```python
@dataclass(frozen=True)
class SkipRecord:
    type: str
    bucket: str  # must be in SKIP_BUCKETS
    detail: str  # verbatim SOAP message — for the AUDIT LOG, not the published CSV
    components_requested: int | None = None
    components_retrieved: int | None = None

class SkipLog:
    def __init__(self): self._records: list[SkipRecord] = []
    def add(self, *, type, bucket, detail="", requested=None, retrieved=None): ...
    def __iter__(self): ...
    def write_csv(self, path: Path) -> None:   # PUBLISHED: type,bucket,components_requested,components_retrieved (NO detail)
    def audit_lines(self) -> list[str]: ...    # full detail, for the audit log
```

`detail` is truncated to `MAX_SKIP_DETAIL_LEN` on add (it still only ever lands in the audit log, never the published CSV — design §3.6).

**Tests (offline):**
- bucket must be in `SKIP_BUCKETS` (raises otherwise).
- Published CSV header is exactly `type,bucket,components_requested,components_retrieved` (design §3.6 — **no `detail` column**).
- `detail` never appears in the published CSV; it does appear in `audit_lines()`.
- Empty log writes a header-only file.
- `components_requested`/`components_retrieved` populated only for `partial_retrieve` rows; empty otherwise.

**Gate:** new tests green; existing tests unchanged.

## 3. Enumerator (modify the current enumerate module — name verified against the existing tree)

Three changes:

### 3.1 Skip-and-log on per-type `listMetadata`

Wrap each per-type `listMetadata` call. Classify failures into `SKIP_BUCKETS`:

| Error fragment / pattern | Bucket |
|---|---|
| `INSUFFICIENT_ACCESS` | `insufficient_access` |
| `INVALID_TYPE: Cannot use:` | `invalid_type` |
| anything else | `unknown` |

On any bucket, append to the `SkipLog` and continue. **Do not raise.** Only the wholesale `describeMetadata` failure remains fatal.

### 3.2 Union with `ALWAYS_PROBE_TYPES`

Before applying `DENY`, take `set(describe_types) | set(ALWAYS_PROBE_TYPES)`. Log which always-probe types were not in `describe_types` (a maintenance signal — if none ever show up missing, the always-probe list is unnecessary work).

### 3.3 Folder-mounted enumeration

For each `inner` in `FOLDER_INNER_TYPES`:

1. Verify `describeMetadata` for `inner` carries `inFolder=True`. If not, log a warning to the audit (the constant disagreed with the org's describe).
2. `listMetadata(folder_type)` → folder fullNames. Append any `SYNTHETIC_FOLDERS[inner]` (no-op if not configured).
3. Add the folder type itself to the enumeration map (folders are metadata).
4. For each folder, `listMetadata(inner, folder=fullName)` — collect members.
5. The folder's `listMetadata` calls are individually subject to §3.1 (skip-and-log on failure), but folder-level failures within a type accumulate into a single `partial_retrieve`-shaped record at the inner type level rather than one row per folder. (A type-wide failure on the folder-listing step uses the normal bucket classification.)

**Tests (offline, with mocked `sf` runner):**
- `listMetadata` raising `INSUFFICIENT_ACCESS` → type recorded in `insufficient_access`, not raised.
- `listMetadata` raising `INVALID_TYPE: Cannot use: ApexClass in this organization` → type recorded in `invalid_type`.
- `listMetadata` raising an unrecognised error → type recorded in `unknown` with the message preserved.
- Always-probe types absent from `describeMetadata` are still probed; failures route to the appropriate bucket.
- Folder-mounted enumeration: 0 folders → empty inner; 3 folders × 2 members each → 6 members; one failing folder → 4 members + audit warning.
- `describeMetadata` complete failure → `RuntimeError` (still aborts).

**Gate:** enumerator tests green; the full existing suite green.

## 4. (No pre-flight strip-and-retry — N/A on the SOAP path)

The original plan had a CLI registry strip-and-retry pre-flight. sf-clean-room retrieves via the **SOAP Metadata API** (`soap.py`/`retrieve.py`), not `sf project retrieve start`, so there is no local CLI type registry to miss (design §3.4). **This step is intentionally omitted.** The `registry_miss` bucket stays in `SKIP_BUCKETS` (reserved, forward-compatible) but is never populated. No module, no constant (`MAX_REGISTRY_MISS_STRIPS`), no test for it.

## 5. Partial-retrieve detection (extend the retrieve+extract stage)

A SOAP `retrieve` returns a zip whose own `package.xml` lists the components Salesforce actually included. Compare **returned members vs requested members, per type** — the same unit on both sides, immune to the file-per-component ratio.

For each batch:

1. Read the returned `package.xml` from the retrieve zip (parse `result.zip_b64` in memory, or the extracted copy before the next batch overwrites it). Build `retrieved[type] = set(members)`.
2. From the batch's manifest build `requested[type] = set(members)`.
3. For each type: if `len(retrieved.get(type, [])) < len(requested[type])`, add a `partial_retrieve` record with `components_requested=len(requested)`, `components_retrieved=len(retrieved)`. A full miss (`retrieved=0`) is the same row with `0`.
4. Accumulate retrieved members across batches; the published `package.xml` is built from the union of retrieved members (never the requested manifest), so it does not overstate.

**Important:** partial retrieves are **not** errors — record and continue. Only a parse/filesystem error aborts here.

**Tests (offline):**
- All types fully retrieved → no `partial_retrieve` rows; published `package.xml` == requested.
- One type `requested=10, retrieved=3` → one row with the exact numbers; published `package.xml` lists the 3.
- One type `requested=10, retrieved=0` → one row, both numbers present; type absent from published `package.xml`.
- Returned `package.xml` parsing handles the real SOAP zip shape (a fixture zip).

**Gate:** partial-retrieve tests green.

## 6. Publish (modify `publish.py`)

The publisher already moves the sentinel last and takes a `sentinel_name` parameter (added for `get_records`). Generalise it to also accept an ordered list of non-sentinel artefacts that must move into `--path` **before** the sentinel. New signature:

```python
def publish(temp_dir, publish_path, sentinel_name="package.xml",
            preceding_artefacts: tuple[str, ...] = ()) -> None:
    """Move every entry from temp_dir into publish_path, except sentinel
    and the preceding_artefacts; then move each preceding_artefact in
    order; finally move sentinel."""
```

`get_metadata` calls it with `preceding_artefacts=("_skipped-types.csv",)`. `get_records` reuses the same helper.

The `SkipLog` is written to `temp_dir/_skipped-types.csv` at the end of retrieve+extract, before publish is invoked. Empty `SkipLog` → header-only file.

**Tests (offline):**
- Sentinel still moves last.
- `_skipped-types.csv` moves before sentinel.
- Missing `_skipped-types.csv` in temp → publish aborts (the file is a contract artefact).
- Empty `SkipLog` → header-only CSV published.

**Gate:** publish tests green; v1 publish tests stay green.

## 7. CLI / help (`cli.py`)

No flag changes. Per-command help text for `get_metadata` is regenerated from constants and now documents:

- The `_skipped-types.csv` artefact, its schema, and that an empty file is the expected state for a full-permission identity.
- The skip-and-continue discipline for per-type errors, with the documented bucket list.
- The fact that the always-probe list and bucket list are source-only.

Help still runs without authentication, without a config file, without writing anywhere.

**Tests (offline):**
- `sf-clean-room get_metadata --help` includes the documented sections.
- `sf-clean-room --help` lists `get_metadata` (unchanged) and any other commands (unchanged).
- Help-text generation references the same constants as runtime — a regression test pulls the bucket list from `constants.py` and asserts it appears in the help body.

## 8. Audit log additions (`audit.py`)

New structured events:

| Event | Fields |
|---|---|
| `skip_bucket` | type, bucket, detail (full, untruncated), components_requested?, components_retrieved? |
| `partial_retrieve` | type, requested, retrieved |
| `folder_enum` | inner, folder_type, folders_listed, members_total |

Stderr tee: at the run-summary line, include a one-line skip summary:
`skipped: 3 (insufficient_access=1, invalid_type=2)` etc. Empty → no line.

**Tests (offline):**
- New audit events have stable field shapes.
- Stderr summary is well-formed and omitted when there are zero skips.

## 9. Tests — live (chatbot-driven)

Two live runs, per [`regression-testing.md`](../regression-testing.md) §2:

### 9.1 Full-permission identity (always runnable)

- Target: the configured dev-edition alias (`tests/live_org.toml`, default `example-dev-edition`).
- Expected: `package.xml` lands; `_skipped-types.csv` is header-only **or** carries only genuine `partial_retrieve` rows for that org; behaviour otherwise identical to v1; exit 0.

### 9.2 Limited-permission identity (when a fixture is available)

- Target: a limited-permission alias if one is authenticated (e.g. a custom-profile identity). If `tests/live_org.toml` gains a `limited_test_org` key and that alias is authenticated, run it; otherwise **skip and say so** (C7 — surface, don't hide; never auto-authenticate).
- Expected: `package.xml` lands; `_skipped-types.csv` is non-empty with rows in `insufficient_access` and/or `invalid_type`; exit 0 (does NOT abort).

Both runs include a manual inspection step: open `_skipped-types.csv`, confirm every row's bucket is in `SKIP_BUCKETS`, confirm no deny-listed type appears, and confirm `components_requested`/`components_retrieved` are populated only on `partial_retrieve` rows. Verbatim error detail is checked in the **audit log**, not the published CSV.

**Gate:** the full-permission run produces the documented artefacts and matches v1; if the limited-permission fixture is available, that run does NOT abort.

## 10. Documentation

1. **`docs-change-log.md`:** new entry at top.
   - What changed; what the v2.1 contract says; the principle reference (A3, B2, B4).
   - Note: v1 design doc is unchanged; v2.1 supersedes its "abort on per-type error" implicit assumption.
   - Confirm the always-probe list contents and the rationale for each entry.
2. **`README` (root):** add a short paragraph noting that `get_metadata` is fault-tolerant to per-type permission gaps and produces `_skipped-types.csv`.
3. **`regression-testing.md`:** new §2.x covering the limited-permission live test.

## 11. Acceptance checklist

Before merging:

- [ ] Every offline test green, including the full v1 + v2 + v2.1 suite.
- [ ] Full-permission live run green; `_skipped-types.csv` header-only (or only genuine `partial_retrieve` rows); `package.xml` present; `get_records` live still green.
- [ ] Limited-permission live run green if a fixture is available; otherwise explicitly reported as not run (C7).
- [ ] Per-command help text includes the `_skipped-types.csv` and bucket documentation.
- [ ] Audit log includes the new skip detail; published CSV has no `detail` column.
- [ ] `regression-testing.md` updated with the v2.1 artefact and checks (C7).
- [ ] `docs-change-log.md` updated.
- [ ] No new operator-tunable safety surface. (Search the diff for new `argparse.add_argument` calls on `get_metadata`; there should be zero.)
- [ ] No new source path bypasses `DENY` or `ALWAYS_PROBE_TYPES`. (Search the diff for `DENY` / `ALWAYS_PROBE_TYPES` references; both should appear only in `constants.py` and the enumerator.)

## 12. Out of scope for v2.1 (and why — restated from the design)

- Retry / backoff for transient errors. Conflated into `unknown` for now; future iteration.
- Per-member naming of partial retrieves. Type-level shortfall only.
- Relaxation of the deny list. Orthogonal concern.
- Resilience changes for `get_records`. Different safety model, separate design.

---

## Appendix — Sanity-check sequence (the agent runs this end-to-end before opening a PR)

1. Fresh editable install, then `pytest -q` → green.
2. `sf-clean-room get_metadata --help` → includes the §8 documented sections.
3. `sf-clean-room get_metadata --org-alias <sysadmin> --path .test-output/sysadmin --dry-run` → batch plan, would-be empty `_skipped-types.csv`, no errors.
4. Real `sf-clean-room get_metadata --org-alias <sysadmin> --path .test-output/sysadmin` → `package.xml` present, `_skipped-types.csv` header-only.
5. `sf-clean-room get_metadata --org-alias <limited> --path .test-output/limited --dry-run` → batch plan, non-empty would-be `_skipped-types.csv`.
6. Real `sf-clean-room get_metadata --org-alias <limited> --path .test-output/limited` → `package.xml` present, `_skipped-types.csv` non-empty with rows whose buckets are all in `SKIP_BUCKETS`.
7. If a limited-permission fixture is available, diff the two `package.xml` files: the limited one has a strict subset of the types, with possibly smaller member counts on partial-retrieve types. Otherwise, note the limited run was not performed.
