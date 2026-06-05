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
test_org = "example-dev-edition"
output_dir = ".test-output"
```

**Check it exists before using it** (this is the existence guard the design
assumes):

```powershell
sf org display --target-org example-dev-edition --json
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

## 4. Chatbot-driven live regression — `get_metadata` (v1)

Confirm v1 still works after any shared-code change (`publish.py`, `session.py`,
`sfcli.py`, `config.py`, `audit.py`):

```powershell
sf-clean-room get_metadata --org-alias example-dev-edition --path .test-output\meta --dry-run
sf-clean-room get_metadata --org-alias example-dev-edition --path .test-output\meta
```

Verify: dry-run prints a batch plan; the real run publishes a metadata tree with
`package.xml` present at the root (the v1 sentinel). No `package.xml` ⇒ failed.

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
