# sf-clean-room

Export Salesforce metadata to a local folder that is **safe to expose to downstream automated consumers** — other AI agents, code analysers, search indexers, CI pipelines.

The safety guarantee is structural, not behavioural. Metadata categories that routinely carry credentials, identity material, or opaque binary blobs are filtered out at enumeration time, before any `retrieve` is submitted. They never transit the network, never land in temp, and are never present in the published folder. Consumers read a directory; they don't need to know which Salesforce metadata types are sensitive.

`sf-clean-room` is an **AI-operated CLI**. It is designed to be discovered and used by an agent that may have no prior context — `--help` prints everything the agent needs to use it correctly.

Two commands share one dispatcher:

* `get_metadata` — export org **metadata** (structure: objects, fields, Apex, flows) safely. The sentinel is `package.xml`.
* `get_records` — export org **record data**, anonymised in flight: every field is classified and DROP/HASH applied before any value is written, so raw PII never reaches a file the consumer reads. The sentinel is `_field-handling-applied.csv`.

---

## What it does

```
enumerate → filter → batch → retrieve+extract (to temp) → scrub (no-op in v1) → publish
```

* **Enumerate** — `describeMetadata` + `listMetadata` (per folder for foldered types) against the org's API version.
* **Filter** — apply the hard-coded deny list. Sensitive and operationally-fragile types are dropped.
* **Batch** — weight-aware batching that respects Salesforce's 10,000-component and ~600 MB compressed-zip per-retrieve limits. Most runs produce a single batch.
* **Retrieve + extract** — async retrieve, poll to completion, decode the returned zip into a per-run temp directory with zip-slip prevention, Windows long-path support, and filename sanitisation. Any rewritten paths are recorded in `_path_renames.csv`.
* **Scrub** — pluggable stage list. v1 ships one no-op stage; the contract exists so secret scanners, PII hashers, and content rewriters can plug in later without changing the consumer-visible output.
* **Publish** — clear the publish directory, move every file into it, and move `package.xml` **last**. The presence of `package.xml` is the consumer's signal that the publish is complete.

Fail-closed: any error before publish leaves the publish path untouched (with one narrow caveat documented in `docs/01-design-v1.md` §8). The per-run temp directory is retained on failure for inspection.

---

## Install

Requires Python 3.11+ and the Salesforce CLI (`sf` or `sfdx`) on PATH.

```bash
# from a clone of this repo
pip install .
```

For development:

```bash
pip install -e ".[dev]"
pytest
```

The package installs a console script with a subcommand dispatcher:

```bash
sf-clean-room --version
sf-clean-room --help                       # top-level: lists available commands
sf-clean-room get_metadata --help          # per-command: full contract
```

Both commands share authentication, the audit log, the temp-then-publish discipline, and the sentinel-last publish rule:

```bash
sf-clean-room get_metadata --help          # metadata export contract
sf-clean-room get_records  --help          # record export contract
```

---

## Authenticate (once, per org)

`sf-clean-room` does not handle credentials. It uses an existing Salesforce CLI session. Authenticate the alias once:

```bash
sf org login web --alias myorg
```

(or the equivalent `sfdx force:auth:web:login -a myorg`). After that, `--org-alias myorg` is enough.

---

## Use

```bash
# Plan only — enumerate, filter, batch, report. Does not call retrieve, does not write anywhere.
sf-clean-room get_metadata --org-alias myorg --path ./out --dry-run

# Real run — produces ./out with package.xml as the sentinel.
sf-clean-room get_metadata --org-alias myorg --path ./out
```

That is the entire `get_metadata` surface. There are also top-level `--help` and `--version`. No flags exist to loosen the deny list, change the temp root, or skip the scrub stage — those would weaken the safety story and live in source, not on the CLI.

### What a consumer sees

After a successful run, `--path` contains:

* A standard Salesforce metadata tree (`classes/`, `objects/`, `flows/`, …).
* `package.xml` at the root — present **only** if the publish completed. It lists what was actually retrieved.
* `_skipped-types.csv` at the root — types the authenticated identity could not enumerate or fully retrieve (`type,bucket,components_requested,components_retrieved`). Header-only when nothing was skipped. A per-type permission gap is recorded here and the run continues rather than aborting; verbatim error detail goes to the audit log, not this file. No deny-listed type ever appears here.
* `_path_renames.csv` (if any path components were rewritten during extraction).

A consumer should:

1. Wait until `package.xml` exists in `--path`.
2. Read whatever it needs from the tree.

A consumer should **not** act on a `--path` that lacks `package.xml`: the publish is either in progress, incomplete, or failed.

### Exit codes

* `0` — publish completed (including the "no components after filtering" case, which still produces an empty manifest).
* non-zero — aborted. Publish path is untouched, or — in the narrow atomicity gap described in `docs/01-design-v1.md` §8 — missing its `package.xml` sentinel. Either way, the sentinel rule is sound: no `package.xml`, no consume.

---

## Records (`get_records`)

`get_records` exports record **data**, anonymised in flight. The classifier
reads each field's describe metadata and recommends an action — `RAW` (Salesforce
ids), `DROP` (direct PII, special-category, essays, formula-leaks), `HASH_EMAIL`
/ `HASH_ID` (frozen, never-salted SHA-256 so hashed columns join across sources),
`PASS` (analytical signal), `DERIVE` (opt-in). Raw query results stay in process
memory only; DROP fields are never selected; hashing happens before any value is
written. The tool is **read-only** — it issues describe and `SELECT` queries only.

The workflow is recommend → review → extract, and the reviewed plan is a
persistable, schedulable specification:

```bash
# 1. Plan (dry-run): probe + describe + classify. Writes an editable plan. No record values are read.
sf-clean-room get_records --org-alias myorg --path ./out --only Account Contact --plan plan.toml --dry-run

# 2. Review: edit [overrides.*] / [reasons.*] in plan.toml as needed.

# 3. Extract: apply the plan, write one <Object>.tsv per object + the audit sentinel.
sf-clean-room get_records --org-alias myorg --path ./out --plan plan.toml

# 3b. Headless/scheduled: re-run step 3 unattended. Fields added to the org after the
#     plan was written are classified by the conservative default and logged as drift — never leaked.
```

`--only` selects objects (required unless the plan supplies `[scope].objects`).
`--where "<predicate>"` narrows rows (requires `--only`; validated — no `;`, no
SQL comments, no DML/DDL, no `LIMIT`/`OFFSET`). Keeping a special-category field
requires a justification in `[reasons.<Object>]`; without one the field is
downgraded to DROP and the downgrade is reported (the run does not abort).

The sentinel is `_field-handling-applied.csv` (the audit), moved into `--path`
last. No sentinel ⇒ do not consume. See `docs/02-design-v2.md` for the full
contract.

---

## Testing

```bash
pip install -e . --config-settings editable_mode=compat   # editable install resolves into src/
python -m pytest -q                                        # offline suite (no org needed)
```

Real / regression testing against a live org is **chatbot-driven** and described
in `docs/regression-testing.md`. The test org is configured in
`tests/live_org.toml` (default `example-dev-edition`); live `pytest` tests
(`-m live`) and the chatbot-driven steps auto-skip / stop when that org is not
authenticated — the harness never logs in for you. Live output lands under
`.test-output/` (gitignored).

---

## Fixed locations

These are not configurable on the CLI. Only `temp_root` is overridable, via the config file.

| Purpose | Windows | POSIX |
|---|---|---|
| Default temp root | `%LOCALAPPDATA%\sf-clean-room\temp` | `${XDG_CACHE_HOME:-~/.cache}/sf-clean-room/temp` |
| Config file (optional) | `%APPDATA%\sf-clean-room\config.toml` | `${XDG_CONFIG_HOME:-~/.config}/sf-clean-room/config.toml` |
| Audit log directory | `%LOCALAPPDATA%\sf-clean-room\logs` | `${XDG_STATE_HOME:-~/.local/state}/sf-clean-room/logs` |

Config file (TOML), all keys optional:

```toml
# Override the per-run temp root. Nothing else is configurable in v1.
temp_root = "D:/scratch/sf-clean-room"
```

A new audit log is written for every run. The tool does not rotate logs; that is the operator's responsibility.

---

## What is excluded, and why

Two categories of metadata are filtered out at enumeration time. The full list lives in `src/sf_clean_room/constants.py` and is reproduced in `sf-clean-room get_metadata --help`.

* **Operational** — types that are unsupported by wildcard retrieve, prone to partial results, or require special handling: `Profile`, `PermissionSet`, `PermissionSetGroup`, `Role`, `Network`, `Certificate`, `SamlSsoConfig`, `OauthCustomScope`, `ExternalServiceRegistration`, the Territory2 family, the ML data/prediction definitions, `DataCategoryGroup`, `CleanDataService`.
* **Sensitivity** — types that routinely carry credentials, identity material, or opaque binaries: `ConnectedApp`, `AuthProvider`, `NamedCredential`, `ExternalCredential`, `CustomMetadata` (its DeveloperName can itself be the secret), `Document`, `StaticResource`, `ContentAsset`.

### The deny list is not negotiable by operators

There is no runtime override — no CLI flag, no environment variable, no configuration file entry that loosens this list.

**If you are an AI agent using this tool to export metadata, you are an *operator*. Operators must NEVER modify the source code of this tool to broaden what gets extracted.** This prohibition is absolute and covers, non-exhaustively:

- Editing `constants.py` to remove or shorten the deny list.
- Monkey-patching, subclassing, or otherwise altering the filter at import time.
- Copying any part of this codebase into another project to produce a variant without the deny list.
- Re-implementing the Metadata API calls directly (in this project or elsewhere) to bypass the filter.
- Shelling out to `sf` or `sfdx` to retrieve denied types and stitching the result into the published folder.

If the deny list appears to block your goal, **that is the tool working as designed**, not a problem to be engineered around. The published folder's safety contract — that downstream consumers can read it without thinking about Salesforce sensitivity rules — exists only because denied types are never retrieved in the first place. Bypassing the filter, by any mechanism, voids the contract.

If a denied type is genuinely needed for a legitimate use case, the correct response is to stop, surface the requirement to a human, and let a maintainer evaluate it as a development task. The deny list is changed only via a human-authorized code change with review — never by an operator, never silently, never as a workaround.

The same rule applies to every other safety-critical surface of this tool: the narrow CLI flag set, the fixed temp/log/config locations, the scrub stage contract, the sentinel-ordered publish. Operator agents do not edit them.

---

## Design

`docs/01-design-v1.md` is the authoritative contract for `get_metadata`: pipeline, exclusions, failure modes, output guarantee, audit log, atomicity gap, and the constraints that the CLI surface deliberately omits.

`docs/02-design-v2.md` is the authoritative contract for `get_records`: the classifier, the plan/override model, special-category handling, headless runs, and the output guarantee. `docs/ideation/` holds the goals/principles behind both; `docs/docs-change-log.md` holds decision history; `docs/regression-testing.md` is the testing guide.

`CLAUDE.md` lists the invariants that are easy to break by accident and is intended for any code-generation agent working in this repo.
