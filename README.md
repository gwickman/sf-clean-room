# sf-clean-room

sf-clean-room is a Python application that lets a flagship AI agent help analyse a Salesforce org without granting the agent direct access to the org or to confidential information.

For an architect or consultant with a corporate AI, it is tempting to let the AI do much of the heavy lifting when analysing a client org. But pointing an AI agent directly at a client org will, in most cases, breach both your company's AI usage policy and your client agreements. Few governance policies permit an AI to connect to a production org, and most treat the consumption of confidential data or PII by an AI as a data breach.

sf-clean-room is designed to keep the AI useful while staying inside those policies. For known schemas (event logs, setup audit trails, login history and the like) it hashes useful PII such as email addresses, so records still join and match, and drops the higher-risk columns that carry little practical value. For dynamic schemas, such as data drawn from custom objects, it hashes or drops the obvious violations and provides utilities and procedures that reduce the chance of accidental data leakage.

## Use and responsibility

The tool reduces risk; it does not remove it. Ensuring compliance with your AI usage policy, your client agreements, and applicable data-protection law remains the sole responsibility of the user of the AI and the tool. The repository provides cookbooks and procedures to help reduce that risk.

sf-clean-room is licensed under the Apache License 2.0 and is distributed on an "as is" basis, without warranties or conditions of any kind. See the [LICENSE](LICENSE) file for the full terms, including the disclaimer of warranty and limitation of liability.

---

## When to use it

Use sf-clean-room wherever you need a safe, structured read of a Salesforce org: one-off assessments (health, security, technical debt), pre-sales scoping and estimation, ongoing governance and managed-services monitoring, audit and incident work, documentation, and cross-client benchmarking.

**Assess and advise**
- Org health check
- Security review
- Well-Architected review
- Technical-debt scorecard, with month-on-month trend
- Automation rationalisation (Workflow Rule / Process Builder → Flow)
- Data-model rationalisation (unused fields, empty objects, data skew)

**Win and scope work**
- Pre-sales and discovery of an unfamiliar org
- Evidence-based estimation
- Due diligence, M&A, and org consolidation

**Run and govern**
- Continuous governance and standards checks
- Config-drift and permission-creep detection
- Managed-services health monitoring
- Audit and compliance evidence pack
- Incident forensics and RCA
- Licence and permission right-sizing

**Know and enable**
- Org documentation generation
- Onboarding and knowledge transfer
- Context for coding agents and CI gates

**Across a portfolio**
- Cross-client benchmarking

---

## Quick setup

**Prerequisites**

- **Python 3.11+**
- **Salesforce CLI** (`sf`) on your PATH — [install guide](https://developer.salesforce.com/tools/salesforcecli)
- **Pre-authenticated org aliases** — the tool uses the existing Salesforce CLI session; it does not handle authentication itself. Each org you want to analyse must be authenticated before you run any command:
  ```bash
  sf org login web --alias myorg
  ```
  You can have as many aliases as you need (one per org, sandbox, or environment).
- **`get_code_analysis` only:** the `sf code-analyzer` plugin (`sf plugins install @salesforce/plugin-code-analyzer`) and **Java 11+** on your PATH (required by the PMD and CPD engines; without it, Apex rule coverage is unavailable).

**The quickest way to get productive**

This assumes that you're using a corporate coding agent from a terminal or dedicated app like Claude Desktop or Codex, not a chatbot or as a plug-in. 

Explain your use case to the coding agent (such as Claude Code), point it at this repository, and ask it to read the documentation. The agent will work out which commands apply to your situation, verify that the prerequisites above are satisfied, and walk you through anything that still needs doing.

```
I want to [describe your use case — e.g. "run a security and code-quality review of a client org"].
Please read the sf-clean-room repository at [path or URL] and advise me on how to proceed.
```

The documentation is designed to be machine-readable: `--help` at every level gives the full command contract, and the design docs in `docs/` cover the detail. Once the agent has read them, it can drive the entire workflow — from choosing the right commands to reviewing the output.

---

## How it works

Extract Salesforce **metadata, record data, event logs, and technical objects** into local folders that are **safe to expose to downstream automated consumers** — other AI agents, code analysers, search indexers, CI pipelines.

> **Scope note.** These outputs are designed for controlled, private downstream consumers. They are not automatically safe to publish publicly. Metadata export excludes sensitive metadata types by design, but does not currently run a content secret scanner over allowed metadata or code files — treat the output accordingly.

The safety guarantee is structural, not behavioural: anything sensitive is excluded, anonymised, or derived **before** it reaches a published file. Sensitive metadata types never leave Salesforce; record PII is classified and dropped/hashed in flight; event-log IPs, usernames, and free text are derived/hashed/dropped while the raw download exists only in memory. Consumers read a directory — they never hold a Salesforce session and never see a raw extract.

`sf-clean-room` is an **AI-operated, read-only CLI**. It is designed to be discovered and used by an agent that may have no prior context — `--help` prints everything the agent needs to use it correctly. Every command publishes to a per-run temp area first and moves a **sentinel file** into the output last: see the sentinel, the publish is complete; no sentinel, don't read.

---

## Commands

| Command | What it does | Sentinel |
|---|---|---|
| `get_metadata` | Export org **metadata** (objects, fields, Apex, flows, …). A source-controlled deny list excludes credential-bearing and fragile types at enumeration, before any retrieve. Per-type permission gaps are skipped and recorded (`_skipped-types.csv`), not fatal. | `package.xml` |
| `get_records` | Export org **record data**, anonymised in flight. Every field is classified (RAW / DROP / HASH / PASS / DERIVE); raw PII never reaches disk. A reviewed plan persists the classification for headless, scheduled re-runs. | `_field-handling-applied.csv` |
| `get_event_logs` | Export org **EventLogFile** activity data, anonymised in flight and **incrementally** — each run adds a dated subfolder, building history beyond Salesforce's ~30-day retention. IPs → network prefix, URLs → query-stripped, usernames hashed, free text dropped; Salesforce IDs kept as join keys. | `_field-handling-applied.csv` |
| `get_technical_objects` | Export **40 catalogued technical objects** (Tooling entities, system tables, REST metrics endpoints), anonymised in flight. Covers Apex code health, job machinery, privilege topology, login/session/MFA activity, setup audit history, usage telemetry, and org limits. IPs → network prefix, geo coarsened to country/subdivision, emails/usernames hashed, free text dropped; permission bits and IDs kept whole. Snapshot publish model (clear-and-republish). | `_field-handling-applied.csv` |
| `get_security_health_check` | Export the org's **Security Health Check** score and per-setting risk table (HIGH_RISK / MEDIUM_RISK / LOW_RISK / INFORMATIONAL / MEETS_STANDARD) via the Tooling API. All org-configuration data — no classifier, no PII. Snapshot publish model (overwrites on each run). | `securityhealthcheck_<alias>.json` |
| `get_code_analysis` | Run **Salesforce Code Analyzer** (`sf code-analyzer`) over a local `get_metadata` output folder and publish the HTML + CSV + JSON report. **No Salesforce session** — runs locally against files on disk. Requires the `sf code-analyzer` plugin and a completed `get_metadata` run (i.e. `package.xml` must be present in `--metadata-path`). | `_summary.json` |

```bash
sf-clean-room --help                       # tool overview + command list
sf-clean-room <command> --help             # full per-command contract
```

Together these give an AI agent a safe, local picture of an org — its *structure* (`get_metadata`), its *data shape and distributions* (`get_records`), its *operational/security activity* (`get_event_logs`), its *technical internals* (`get_technical_objects`), its *security posture* (`get_security_health_check`), and its *code quality and vulnerabilities* (`get_code_analysis`) — without the agent ever touching Salesforce directly or seeing raw PII, credentials, or secrets. All commands are read-only, fail closed, and audit every run. All support `--dry-run`. (`get_code_analysis` requires no Salesforce session — it runs locally over a prior `get_metadata` output.)

---

## The metadata pipeline

```
enumerate → filter → batch → retrieve+extract (to temp) → scrub (no-op in v1) → publish
```

* **Enumerate** — `describeMetadata` + `listMetadata` (per folder for foldered types) against the org's API version.
* **Filter** — apply the hard-coded deny list. Sensitive and operationally-fragile types are dropped.
* **Batch** — weight-aware batching that respects Salesforce's 10,000-component-per-retrieve ceiling and the SOAP ZIP size limits (39 MB compressed / 400 MB uncompressed). Most runs produce a single batch.
* **Retrieve + extract** — async retrieve, poll to completion, decode the returned zip into a per-run temp directory with zip-slip prevention, Windows long-path support, and filename sanitisation. Any rewritten paths are recorded in `_path_renames.csv`.
* **Scrub** — pluggable stage list. v1 ships one no-op stage; the contract exists so secret scanners, PII hashers, and content rewriters can plug in later without changing the consumer-visible output.
* **Publish** — clear the publish directory, move every file into it, and move `package.xml` **last**. The presence of `package.xml` is the consumer's signal that the publish is complete.

Fail-closed: any error before publish leaves the publish path untouched (with one narrow caveat documented in `docs/design/01-design-v1.md` §8). The per-run temp directory is retained on failure for inspection.

---

## Install

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

All commands share the audit log, the temp-then-publish discipline, and the sentinel-last publish rule. Per-command help:

```bash
sf-clean-room get_metadata                --help   # metadata export contract
sf-clean-room get_records                 --help   # record export contract
sf-clean-room get_event_logs              --help   # event-log export contract
sf-clean-room get_technical_objects       --help   # technical objects export contract
sf-clean-room get_security_health_check   --help   # security health check contract
sf-clean-room get_code_analysis           --help   # code analysis contract
```

---

## Metadata (`get_metadata`)

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
* non-zero — aborted. Publish path is untouched, or — in the narrow atomicity gap described in `docs/design/01-design-v1.md` §8 — missing its `package.xml` sentinel. Either way, the sentinel rule is sound: no `package.xml`, no consume.

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
last. No sentinel ⇒ do not consume. See `docs/design/02-design-v2.md` for the full
contract.

---

## Event logs (`get_event_logs`)

`get_event_logs` downloads Salesforce **EventLogFile** CSVs and publishes them
anonymised. The classifier keeps Salesforce IDs and the already-hashed
`SESSION_KEY`/`LOGIN_KEY` as RAW (the join keys), hashes usernames, derives IPs to
a network prefix, strips URL query strings, keeps metrics/enums/Salesforce geo,
and drops the rare free-text/content column — all before any value is written
(the raw `LogFile` stays in memory). It is **read-only** (REST `GET` only).

```bash
# Plan (dry-run): query the window, report records per EventType + the column plan. No LogFile fetch, no values.
sf-clean-room get_event_logs --org-alias myorg --path ./out --only Login ReportExport --plan p.toml --dry-run

# Real run: download, anonymise in flight, publish a dated subfolder.
sf-clean-room get_event_logs --org-alias myorg --path ./out
```

It is **incremental**: output lands under `./out/event_logs/<alias>/<start>_to_<end>/`,
each run adds a new dated subfolder (prior ones are never cleared — this builds
history beyond Salesforce's ~30-day retention), `end = yesterday (UTC)`, and a run
that already covers through yesterday is a no-op. The sentinel
`_field-handling-applied.csv` is moved into the subfolder last. See
`docs/design/04-design-v3.md`.

---

## Testing

```bash
pip install -e . --config-settings editable_mode=compat   # editable install resolves into src/
python -m pytest -q                                        # offline suite (no org needed)
```

Real / regression testing against a live org is **chatbot-driven** and described
in `docs/regression-testing.md`. The test org is configured in
`tests/live_org.toml` (default `sf_clean_room`); live `pytest` tests
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
