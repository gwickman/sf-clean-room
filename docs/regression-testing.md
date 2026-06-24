# Regression Testing — Guidance for the Coding Chatbot

This document tells a coding agent how to test and regression-test `sf-clean-room`
after a change. There are two layers:

1. **Offline suite** (`pytest`) — pure logic and pipeline behaviour with mocked
   `sf` calls. Always runnable, no org, no network. This is your first gate.
2. **Live / chatbot-driven** — you drive the real CLI against a real org and
   inspect the published artefacts. This catches integration issues the mocks
   cannot (CLI flag drift, JSON shape changes, describe/query quirks, encoding).

Live testing is **opt-in and you drive it**. It is not wired into the program.

---

## 0. Golden rules

- **Never authenticate or modify `sf` state.** If the test org is not
  authenticated, stop and report — do not run `sf org login`, do not change the
  default org. (AUP: no AI auto-access to orgs.)
- **Never test record extraction against a client/production org.** Use the
  dedicated dev-edition test org only (see §2). Metadata (`get_metadata`) is far
  less sensitive than records (`get_records`); never point `get_records` at a
  client org to "just check."
- **All live output goes under `.test-output/`** (gitignored). Never write test
  output into a real client project tree.
- **Confirm the editable install first** (see §1) or you will test stale code.

---

## 1. Confirm the install, then run the offline suite

```powershell
# Editable install must resolve into src/, not site-packages (see CLAUDE.md).
pip install -e . --config-settings editable_mode=compat
python -c "import sf_clean_room.audit, inspect; print(inspect.getfile(sf_clean_room.audit))"
#   -> must print a path under src\sf_clean_room\

python -m pytest -q
```

Expected: all pass; the only skips are the POSIX-path tests (on Windows) and the
`live` tests (when the org is not authenticated). A green offline suite is the
precondition for everything below.

The offline suite covers: the classifier (`test_classify.py`), hash recipes
(`test_hashing.py`), the plan/override/special-category/drift logic
(`test_plan.py`), SOQL build + `--where` validation + in-flight transform + TSV
escaping + audit/summary (`test_records_extract.py`), the full mocked pipeline
incl. sentinel and no-DROP-leak (`test_records_pipeline.py`), and the CLI surface
(`test_cli.py`, `test_cli_records.py`), plus the entire v1 metadata suite.

## 2. The test org

Configured in [`../tests/live_org.toml`](../tests/live_org.toml):

```toml
test_org = "example-prodcopy"
output_dir = ".test-output"
```

**Check it exists before using it** (this is the existence guard the design
assumes):

```powershell
sf org display --target-org example-prodcopy --json
```

- If this returns a connected session → live testing is enabled.
- If it errors / is not authenticated → **stop. Report to the user** that the
  test org is not available and that they can enable live tests with
  `sf org login web --alias example-dev-edition`. Do not log in yourself.

To run the automated live tests (they auto-skip when the org is unavailable):

```powershell
python -m pytest -m live -q
```

## 3. Chatbot-driven live regression — `get_records`

Drive the real CLI and inspect what lands on disk. Output under `.test-output/`.

```powershell
$org  = "example-dev-edition"
$out  = ".test-output\$org\Contact"
$plan = ".test-output\$org-contact-plan.toml"

# 3a. Plan (dry-run): probe + describe + classify. No record values are read.
sf-clean-room get_records --org-alias $org --path $out --only Contact --plan $plan --dry-run
```

Verify the dry-run:
- Exit code 0.
- `$plan` exists; `[scope].objects` lists `Contact`.
- The recommendation comments look sane: `Id`/`*Id` are RAW; `FirstName`,
  `LastName`, `Phone`, `Birthdate` are DROP; `Email` is HASH_EMAIL; obvious
  identifiers are HASH_ID; special-category fields are tagged `[SPECIAL-CATEGORY]`.

```powershell
# 3b. Real extract using the (optionally edited) plan.
sf-clean-room get_records --org-alias $org --path $out --only Contact --plan $plan
```

Verify the extract — these are the **acceptance checks**:
- Exit code 0, and `_field-handling-applied.csv` (the sentinel) exists in `$out`.
  No sentinel ⇒ treat the run as failed.
- `Contact.tsv` exists. Its header contains **no** field whose audit action is
  `DROP`. Cross-check: every column name in the TSV header must appear in
  `_field-handling-applied.csv` with an action in
  `{RAW, PASS, HASH_EMAIL, HASH_ID, DERIVE}`.
- **PII leak check** (the most important one): no raw names/emails/phones in the
  TSV. Email/identifier columns must be 64-hex-char SHA-256 values, not raw.
- `_extract-summary.json` `action_counts` sum equals the field count, and
  `where_clause` reflects any `--where` you passed.
- `_capability-probe.json` and `_schema-scan.csv` are present.

```powershell
# 3c. Determinism / headless: re-run 3b unchanged. Output must be identical
#     (same columns, same hashes). This is the scheduled-run path.
# 3d. Drift safety: add a field to the org OR remove a field line from
#     [known_fields] in the plan, re-run 3b, and confirm the new/unknown field
#     is classified by the conservative default and listed in
#     _extract-summary.json "drift_fields" — never silently emitted.
```

### Special-category behaviour to spot-check
Edit the plan to `KEEP` a special-category field **without** a `[reasons.<Object>]`
entry, run 3b, and confirm: the run does **not** abort, the field is **DROPped**,
and the summary/stderr report the downgrade. Then add a justification under
`[reasons.<Object>]`, re-run, and confirm the field is now retained and the
justification appears in `_field-handling-applied.csv`.

### `--where` (narrowing) spot-check
`--where "CreatedDate = THIS_YEAR"` narrows rows; the classifier still runs on
every returned row. Confirm a bad predicate is refused before any query, e.g.
`--where "Id != null; DROP TABLE x"` exits non-zero with a validation error and
writes nothing.

## 4. Chatbot-driven live regression — `get_metadata` (v1 + v2.1 limited-permissions)

Confirm metadata export still works after any shared-code change (`publish.py`,
`session.py`, `sfcli.py`, `config.py`, `audit.py`, `enumerate_md.py`,
`pipeline.py`):

```powershell
sf-clean-room get_metadata --org-alias example-dev-edition --path .test-output\meta --dry-run
sf-clean-room get_metadata --org-alias example-dev-edition --path .test-output\meta
```

Verify:
- Dry-run prints a batch plan **and** a "would-be `_skipped-types.csv`" block
  (empty for a full-permission identity). Enumeration must not abort.
- The real run publishes a metadata tree with `package.xml` at the root (the
  sentinel). No `package.xml` ⇒ failed.
- **`_skipped-types.csv` is present** at the root, header
  `type,bucket,components_requested,components_retrieved`. For a full-permission
  dev org it is header-only or contains only genuine `partial_retrieve` rows.
- Every `bucket` value is in `SKIP_BUCKETS`; **no deny-listed type appears** in
  the file. Verbatim error detail is in the **audit log**, not this CSV.
- `package.xml` lists only what was retrieved (never overstates).

### v2.1 acceptance — limited-permission identity (when a fixture exists)
v2.1's reason for being is graceful degradation under limited permissions. If a
limited-permission alias is authenticated (e.g. a custom-profile identity), run
the two commands above against it and confirm: the run does **not** abort;
`package.xml` lands; `_skipped-types.csv` is **non-empty** with rows in
`insufficient_access` and/or `invalid_type`; exit 0. If no such fixture is
authenticated, **say so explicitly and skip** — never auto-authenticate one
(principle C7: surface, don't hide). The offline suite
(`tests/test_enumerate.py`, `tests/test_pipeline_v21.py`) covers the
limited-permission code paths with mocks regardless.

> **STATUS (cannot yet run): no limited-permission live fixture.** As of the
> v2.1 build, no limited-permission alias is authenticated in the project-profile
> profile, so this live acceptance has **not** been run against a real limited
> identity — it is covered offline by mocks only. To enable it, authenticate a
> dedicated limited-profile user (ideally on `example-dev-edition`) and add a
> `limited_test_org` key to `tests/live_org.toml`. Do not point it at a client
> production org. Until then, report this step as "not run — no fixture".

## 4b. Chatbot-driven live regression — `get_event_logs` (v3)

```powershell
$org = "example-dev-edition"
sf-clean-room get_event_logs --org-alias $org --path .test-output --dry-run
sf-clean-room get_event_logs --org-alias $org --path .test-output
sf-clean-room get_event_logs --org-alias $org --path .test-output   # again -> idempotent no-op
```

Verify:
- Dry-run prints the window and a per-EventType record count, plus the column
  classification plan; it does **not** abort and fetches no `LogFile`.
- The real run publishes `<path>/event_logs/<org>/<start>_to_<end>/` containing
  `_field-handling-applied.csv` (the sentinel) and `_extract-summary.json`; exit 0.
- The second same-day run is an **idempotent no-op** (reports the existing folder).
- **If the org has Event Monitoring data** (CSVs present): no-raw-dump checks —
  no raw dotted-quad IP anywhere; `CLIENT_IP` cells end `.0`; no `@`-bearing
  username; hashed columns are 64-hex; no header column whose audit action is
  `DROP`; URL columns carry no `?` query string.

> **STATUS (2026-06-24, example-prodcopy):** Event Monitoring enabled; 1025
> EventLogFile records across a 30-day window. Dry-run ✓; extraction ✓; sentinel
> (`_field-handling-applied.csv`) present ✓; idempotency re-run ✓ (exit 0). No-raw-dump
> checks: `CLIENT_IP` cells end in `.0` ✓; `SESSION_KEY`/`LOGIN_KEY` RAW ✓;
> `USER_NAME` 64-hex HASH ✓; URL columns carry no `?` query strings ✓.
>
> **Bug found and fixed during this run:** `sanitise_url()` was not masking IPv4
> addresses embedded in URL *paths*. Apex code on this org calls
> `util.appinium.com/ipinfo/<user-ip>` for IP lookups, placing raw user IPs in
> `ApexCallout` log URLs (293 occurrences across 18 files). Fixed by adding an
> `_IP_IN_URL` regex sub to `sanitise_url()` — last octet zeroed in place for any
> dotted-quad anywhere in the URL (host or path). Unit tests in
> `tests/test_eventlog_classify.py` extended with three path-IP cases.
> Re-run after fix verified IPs are zeroed.

## 4c. Chatbot-driven live regression — `get_technical_objects` (v4)

```powershell
$org = "example-dev-edition"

# Dry-run: describe + classify all 40 objects (some will fail with permission gaps on dev edition).
sf-clean-room get_technical_objects --org-alias $org --path .test-output\techobj --dry-run --plan .test-output\techobj-plan.toml

# Real run (limit 50 rows per object for speed).
sf-clean-room get_technical_objects --org-alias $org --path .test-output\techobj --limit 50

# Re-run (snapshot replaces cleanly).
sf-clean-room get_technical_objects --org-alias $org --path .test-output\techobj --limit 50
```

Verify:

- Dry-run: exit 0; `techobj-plan.toml` written; plan contains `[scope]`, `[overrides]`, and at least the objects the dev org permits.
- Real run: exit 0; `_field-handling-applied.csv` (sentinel) present at root of `--path`; `_extract-summary.json` present.
- Sentinel is the **last** file by mtime.
- **No-raw-dump checks** (run on every CSV in `--path` except the sentinel and summary):
  - No **raw** dotted-quad IP (last octet non-zero, regex `\d+\.\d+\.\d+\.[1-9]\d*`) anywhere in data rows. Derived network prefixes ending in `.0` (e.g. `192.168.1.0`) are the expected DERIVE/ip_prefix output and must appear.
  - No `@`-bearing string unless it is 64 hex characters (a hash).
  - Header must contain no `InterviewLabel`, `PauseLabel`, `Display` (curated DROP fields).
  - `LoginGeo.csv` (if present): header must not contain `Latitude`, `Longitude`, `City`, `PostalCode`.
  - `LoginGeo.csv` (if present): header must contain `Country` or `Subdivision`.
- Re-run: sentinel still present; `_extract-summary.json` reflects the new run.
- `_field-handling-applied.csv` has columns `object,column,type,action,recipe,source,downgraded`.
- `_extract-summary.json` has keys `objects`, `skipped`, `limit`.

### Expected permission-gap skips on dev edition (record in summary, not failures)

Some objects require paid add-ons or specific platform settings not present on a Developer Edition org.  A skip means the object appears in `skipped` in `_extract-summary.json` and no CSV is published for it — this is the expected behaviour, not a failure.  Objects **likely to skip** on dev edition:

| Object | Reason |
|---|---|
| `SetupAuditTrail` | May be empty or restricted on some dev orgs |
| `AuthSession` | May be empty or permission-gated |
| `IdpEventLog` | Requires SSO/IDP configuration |
| `VerificationHistory` | Requires MFA event history |
| `ApexExecutionOverlayResult` | Requires Apex debugger sessions |
| `ApexLog` | Only present if debug logs exist |
| `LightningUsage*` | Lightning usage telemetry may be absent |

Record any additional unexplained skips in this file (principle C7: surface, don't hide).

> **STATUS (2026-06-24, example-prodcopy):** 36/40 objects extracted; exit 0 ✓.
> 4 LightningUsage* objects skipped (404 NOT_FOUND — Lightning Usage telemetry
> add-on not enabled); recorded in `_extract-summary.json` `skipped` list.
> No-raw-dump: 60 IP-like values in `AuthSession.csv` all derived (last octet
> `= 0`) ✓; no raw `@`-bearing strings ✓; `LoginGeo` has no `Latitude`,
> `Longitude`, `City`, `PostalCode` ✓; sentinel last by mtime ✓; re-run
> (snapshot replace) ✓.
>
> **Classifier limitation noted:** `Username__c` on `Contact` is classified PASS
> (field name is a generic string type — does not trigger email hashing). However,
> this field contains 30,947 email-format Salesforce Community usernames
> (`adam.durant@yo.co.va`). This is not a code bug — the plan review step is the
> designed safeguard. **Recommended action before any scheduled headless run:**
> add `Username__c = "HASH_ID"` to `[overrides.Contact]` in the plan file.

## 5. Reporting back

Summarise: offline suite result (pass/skip counts); whether the live org was
available; for each live step run — exit code, sentinel present, leak-check
result, any downgrades/drift observed. If the org was unavailable, say so and
give the exact `sf org login` command rather than working around it.

## 6. Quick offline smoke without an org

To exercise the real pipeline code paths end-to-end without an org, drive
`records_pipeline.execute` / `dry_run` with synthetic `describe_fn`/`query_fn`
callbacks (both are injectable). `.test-output/_harness_offline.py` is a worked
example: it emits a plan and a full set of artefacts from fake data so you can
eyeball the real file formats. This is not a substitute for §3 but is a fast
sanity check after refactors.
