# SF Clean Room — Design

**Status:** Draft
**Scope:** v1 of the metadata-export CLI. SF Clean Room is intended to grow into a small family of tools for safe extraction of Salesforce metadata and data; this document covers only the first tool.

---

## 1. Purpose

SF Clean Room is an AI-operated CLI that exports Salesforce metadata for an org and publishes it to a local folder that is safe to expose to downstream automated consumers — including AI agents, code analysers, search indexers, and CI pipelines. The same agent that drives the export is typically also one of those consumers.

The safety guarantee is structural, not behavioural. A consumer reading the published folder does not need to know which metadata types are sensitive, because the categories that carry credentials, identity material, or opaque binary blobs are never written to the published folder in the first place. The tool talks to Salesforce; the consumer talks to a directory.

Because the operator is an AI agent rather than a person, the CLI is designed to be **self-describing**: an agent that discovers the binary without prior context can run `sf-clean-room --help` to discover the available commands, then `sf-clean-room <command> --help` to obtain the command-specific contract — sentinel, deny-list rationale, dry-run semantics, and exit codes. See §4.4.

This is the first of several planned tools. Later tools will extend the same temp-then-publish pattern to data (record) extraction with PII hashing, secret scanning, and content-level redaction.

## 2. Principles

1. **Exclude at source.** The filter is applied to the metadata enumeration *before* any `retrieve` is submitted. Excluded types do not transit the network, do not land in temp, and are never present in any artefact the tool produces.
2. **Two-phase output.** Retrieval lands in a temp area; the published path is only mutated at the final publish step. The temp area exists so that future stages (secret scanners, PII detectors, content rewriters) can be inserted between retrieve and publish without changing the consumer-visible contract.
3. **One sentinel.** `package.xml` is moved to the published path *last*. Its presence is the signal that the publish is complete. Consumers watch for that file and only begin reading once it exists.
4. **Narrow CLI surface.** Anything that could weaken the safety guarantee — the deny list, the temp location, the scrub pipeline — is not on the CLI. Changes go through source and human review.
5. **Fail closed.** Any error in retrieve, extraction, or (future) scrub aborts the publish. The published path is either the previous run's output or the new run's output, never a partial mix of both, except in the narrow window described in §8.

## 3. Capabilities (v1)

| Capability | v1 behaviour |
|---|---|
| Scalable metadata export | Weight-aware batching that respects Salesforce's 10,000-component and ~600 MB compressed-zip limits per retrieve. Multiple batches per run are normal; the consumer sees a single coherent output. |
| Default exclusions | Hard-coded deny list applied at enumeration time. See §6. |
| Temp-then-publish pipeline | Retrieve and extraction happen in a per-run temp directory. Publish is a separate, final step. |
| Configurable temp root | Selected by config file; CLI has no override. Sensible OS-aware default. See §7. |
| Sentinel publish order | `package.xml` is the last file moved into the published path. |
| Dry-run | Enumerate, filter, and report the planned batch composition without contacting `retrieve` and without writing anything to temp or to the published path. |
| Cross-platform paths | Windows long-path support, zip-slip prevention, filename sanitisation on extraction. |
| Audit log | Per-run log of types excluded, batch composition, retrieve outcomes, and publish actions. Written to a fixed location independent of the published path. |

Out of scope for v1, captured for later tools or later versions:

- Record / data extraction.
- PII hashing or content-level redaction.
- Secret-scanner integration (the pipeline slot exists; the scanner does not).
- Allow-listing specific Custom Metadata namespaces.
- Multi-org runs in a single invocation.
- Diff against a previous publish.

## 4. CLI surface

The CLI is structured as a single entry point with named subcommands:

```
sf-clean-room <command> [<command-flags>...]

sf-clean-room --help
sf-clean-room --version
sf-clean-room <command> --help
```

The subcommand structure is deliberate. SF Clean Room is intended to grow into a small family of tools (record extraction, etc.); each new tool is a new subcommand under the same dispatcher, sharing authentication, audit log, temp root selection, and the philosophy of source-controlled exclusions. A single binary is simpler to discover, install, and reason about than several.

### 4.1 v1 commands

| Command | Purpose |
|---|---|
| `get_metadata` | Export org metadata to a publish folder. v1's only command. |

Future commands (not in v1, listed only to anchor the dispatcher's shape):

- `get_records` — extract record data with PII hashing and content-level redaction.

### 4.2 `get_metadata` flags

```
sf-clean-room get_metadata \
    --org-alias <salesforce-cli-alias-or-username> \
    --path <publish-directory> \
    [--dry-run]
```

| Flag | Required | Meaning |
|---|---|---|
| `--org-alias` | yes | Salesforce CLI alias or username. The tool uses an existing CLI session for authentication; it does not handle credentials itself. |
| `--path` | yes | Absolute or relative path to the publish directory. Created if missing. Existing contents are deleted only at the publish step, never before. |
| `--dry-run` | no | Enumerate and filter only. Print planned batch composition. No `retrieve` call, no temp write, no publish-path mutation. |

There are no other flags on `get_metadata` in v1. In particular, there is no flag to:

- Loosen the deny list.
- Change the temp root.
- Skip a pipeline stage.
- Re-enable an excluded metadata type.

Removing those knobs is intentional. The tool's safety story rests on the deny list being non-negotiable at runtime.

### 4.3 Top-level flags

| Flag | Meaning |
|---|---|
| `--help` | Print top-level help: tool purpose, list of commands, authentication, fixed locations, exit codes, and a pointer to per-command help. Safe to invoke without authentication, config, or any other state. See §4.4. |
| `--version` | Print the installed version and exit zero. |

### 4.4 `--help` as a grounding surface

The operator is an AI agent, so `--help` is the primary grounding mechanism for agents that discover the tool without prior context. There are two layers of help text, and both must be invokable without authentication, without a config file, and without writing anywhere:

1. **Top-level help** (`sf-clean-room --help`) — what the tool family is for, the list of available commands, how to authenticate, the fixed temp/config/log locations, the exit-code convention, and a pointer to per-command help.
2. **Per-command help** (e.g. `sf-clean-room get_metadata --help`) — the contract specific to that command: flags, the publish-folder contract from §9, the `package.xml` sentinel rule from §3, the deny list from §6 with the rationale that it is not runtime-overridable, and the batch ceilings from §5.3.

Together they must be sufficient for an agent to:

1. State what each command produces and where, including the sentinel rule.
2. Construct a correct invocation for a real run and for a dry run.
3. Understand that the deny list (§6) is enforced in source and cannot be changed at runtime, so the agent should not attempt to coerce broader extraction by adding flags.
4. Understand that the temp root, config-file location, and audit-log location (§7, §10) are also fixed in source/config and not selectable on the CLI.
5. Know the exit-code conventions (zero on success, non-zero on any abort), and that on failure the publish path is either unchanged or — only in the §8 atomicity gap — missing its `package.xml` sentinel and therefore must not be read.

All help text is generated from the same source constants that drive the runtime (the deny list, the default temp roots, the API version). It is not hand-maintained separately. Keeping the help text in lockstep with behaviour is a correctness property, not a documentation nicety.

The text is intended to be machine-skimmable: short sections, stable headings, no ANSI styling. Standard argparse output is acceptable provided it includes the sections above; if argparse cannot host them inline, the tool prints them in an `epilog` block.

## 5. Pipeline

```
[1] enumerate -> [2] filter -> [3] batch -> [4] retrieve + extract (to temp)
        -> [5] scrub stages (no-op in v1) -> [6] publish
```

### 5.1 Enumerate

Use Salesforce's Metadata API to:

- Call `describeMetadata` for the org's API version to obtain the full set of metadata types available.
- For foldered types (`Dashboard`, `Document`, `EmailTemplate`, `Report`), call `listMetadata` per folder and aggregate.
- For non-foldered, non-denied types, call `listMetadata` per type.

The output is a map of `metadata_type -> [fullName, ...]`.

### 5.2 Filter

Apply the §6 deny list to the enumerated map. Types in the deny list are removed wholesale; partial inclusion is not supported in v1. Log the count of components excluded per type.

### 5.3 Batch

Group the remaining members into one or more retrieve batches subject to:

- A configured maximum component count per batch (Salesforce's hard limit is 10,000; default to 8,000 for safety).
- A configured maximum weight per batch, where weight is a per-type multiplier reflecting expected compressed size. Text-heavy types weight 1; bundle types (`AuraDefinitionBundle`, `LightningComponentBundle`) weight 15–20; large composite types (`ExperienceBundle`, `SiteDotCom`) weight 200–500. Default ceiling is 50,000 weight units per batch.

Because the deny list excludes the heaviest binary types (`Document`, `StaticResource`, `ContentAsset`) and the heaviest composites are rare per org, most runs produce a single batch. The batcher exists to make multi-batch runs correct, not to be the common path.

### 5.4 Retrieve and extract

For each batch:

- Submit an asynchronous `retrieve` with `singlePackage=true`.
- Poll until `Succeeded`, `Failed`, or `Canceled`. Timeout per batch is configurable; default 30 minutes.
- On `Succeeded`, decode the returned zip and extract it into the per-run temp directory using:
  - Zip-slip prevention (destination paths must resolve inside the temp directory).
  - Windows long-path support (`\\?\` prefix on Windows extraction targets).
  - Filename sanitisation: characters illegal on Windows replaced; trailing dots / spaces stripped; over-long components shortened with a stable hash suffix.
  - A per-run `_path_renames.csv` recording any rename that occurred during extraction, written into the temp directory and published with the rest of the output.

`package.xml` is extracted into temp like any other file but is then *held aside* — either moved to a sentinel name within temp (`_package.xml.pending`) or tracked in memory — so it does not get moved during the bulk publish step.

### 5.5 Scrub stages

The pipeline runs an ordered list of scrub stages against the temp tree. v1 ships with a single no-op stage so that the contract and the stage-orchestration code exist from day one.

A stage receives the temp directory and returns either:

- **Clean** — publish may proceed.
- **Findings** — a list of (path, category, detail) tuples. Any findings abort publish; temp is retained for human inspection.

Planned future stages (not in v1):

- Secret scanner (e.g. TruffleHog with verification disabled) over the entire temp tree.
- Filename-shape detector for credential-looking strings in file or directory names (covers the "DeveloperName as secret" pattern in Custom Metadata if Custom Metadata is ever re-enabled).
- Content-level PII detector / hasher for `email/` templates and similar.

Stages are configured in source, not on the CLI.

### 5.6 Publish

Publish is the only point at which the published path is mutated.

1. If `--path` does not exist, create it (including parent directories).
2. Delete the existing contents of `--path`. The directory itself is preserved; only its children are removed. This step happens *only* if §5.1 through §5.5 succeeded — never on retrieve or scrub failure.
3. Move every entry from the temp run directory into `--path`, except the held-aside `package.xml`.
4. Move `package.xml` into `--path` last, under its real name. Consumers may now read.
5. Remove the per-run temp directory (which should now be empty).

The "delete then move" sequence is deliberately not atomic in v1; see §8 for the failure window and the planned v2 atomic-swap.

## 6. Default deny list

All exclusions are applied at the enumeration stage, before any `retrieve`. The list is one constant in source.

### 6.1 Operational exclusions

Types in this group are excluded for operational reliability — they are either unsupported by wildcard retrieve, prone to large or partial results, or require special handling outside the scope of this tool:

`Profile`, `PermissionSet`, `PermissionSetGroup`, `DataCategoryGroup`, `MLDataDefinition`, `MLPredictionDefinition`, `Role`, `Territory2Model`, `Territory2`, `Territory2Type`, `Territory2ModelState`, `Network`, `CleanDataService`, `Certificate`, `SamlSsoConfig`, `OauthCustomScope`, `ExternalServiceRegistration`.

### 6.2 Sensitivity exclusions

Types in this group are excluded because the metadata they produce routinely carries credentials, credential references, identity material, or opaque binary blobs whose contents cannot be assessed by a generic consumer:

| Type | Why excluded |
|---|---|
| `ConnectedApp` | OAuth consumer keys, callback URLs, integration contact emails, OAuth policy detail. |
| `AuthProvider` | Consumer keys / secrets (often masked, sometimes not), IdP endpoints, integration-user identities, registration handler references. |
| `NamedCredential` | Endpoint URLs and credential references that map the org's integration topology. |
| `ExternalCredential` | As above, plus the authentication parameter graph. |
| `CustomMetadata` | Frequently used as a key-bag in practice; the record's DeveloperName can itself be a credential (the value sits in the filename, invisible to content scans). Per-record allow-listing is out of scope for v1. |
| `Document` | Opaque uploaded binaries; arbitrary content. |
| `StaticResource` | Opaque uploaded archives and binaries; arbitrary content. |
| `ContentAsset` | Opaque uploaded assets; arbitrary content. |

### 6.3 Changing the list

The deny list is a source constant. Changes require a code edit and a review. There is no runtime override, no configuration file entry, no environment variable, and no CLI flag that loosens it.

## 7. Temp area

### 7.1 Selection

At startup the tool selects exactly one temp root:

1. If a configuration file contains a `temp_root` entry, that value is used.
2. Otherwise the tool uses an OS-aware default:
   - Windows: `%LOCALAPPDATA%\sf-clean-room\temp`
   - POSIX: `${XDG_CACHE_HOME:-~/.cache}/sf-clean-room/temp`

The configuration file lives at a fixed location (Windows: `%APPDATA%\sf-clean-room\config.toml`; POSIX: `${XDG_CONFIG_HOME:-~/.config}/sf-clean-room/config.toml`). The tool does not look elsewhere.

The temp root must be on a writable filesystem with adequate free space; the tool checks before starting and aborts with an actionable message if not.

### 7.2 Per-run subdirectory

Each invocation creates a fresh subdirectory under the temp root:

```
<temp_root>/<org_alias>-<utc_timestamp>-<short_uuid>/
```

All retrieve output is extracted into this subdirectory. The path is logged at start so the operator can locate it if a run aborts.

### 7.3 Lifecycle

- Created at the start of the retrieve phase.
- Populated through §5.4 and §5.5.
- Emptied and removed at the end of a successful publish.
- **Retained on failure.** If retrieve, extraction, or any scrub stage fails, the temp subdirectory is left in place and its path is surfaced to the operator. The tool does not auto-clean failure state; that is a deliberate forensic choice.

### 7.4 Not on the CLI

The temp root cannot be set from the command line. This keeps the safety surface narrow: there is no run-time vector for redirecting where intermediate, unscrubbed material lands.

## 8. Failure modes

| Failure | Behaviour |
|---|---|
| Authentication / session unavailable | Abort before any temp directory is created. Published path untouched. |
| `describeMetadata` or `listMetadata` fails | Abort before any retrieve. Temp subdirectory may exist but is empty; retained for inspection. Published path untouched. |
| A retrieve batch fails or times out | Abort. All temp content from this run is retained. Published path untouched. |
| Zip extraction fails | Abort. Temp retained. Published path untouched. |
| A scrub stage returns findings (future) | Abort publish. Temp retained. Operator alerted with the finding list. |
| Publish step fails partway between §5.6 step 2 and step 4 | This is the v1 atomicity gap. The published path is in an inconsistent state — possibly empty, possibly partially populated, definitely without `package.xml`. The absence of `package.xml` is the signal to consumers that the publish did not complete; consumers must not act on a published path that lacks `package.xml`. Operator re-runs the tool once the underlying failure is fixed. v2 will close this gap with a stage-swap (write to `<path>.new`, rename old `<path>` to `<path>.old`, rename `<path>.new` to `<path>`). |
| Dry-run on an alias with no metadata in scope | Print "no components after filtering" and exit zero. |
| Real run on an alias with no metadata in scope | Publish path created (if needed) and emptied; only `package.xml` (an empty manifest) is written. Audit log records the empty enumeration. |

## 9. Output contract

A consumer reading a `--path` that contains `package.xml` may assume:

- The folder reflects a complete, successful run.
- No type from §6 is present.
- Path lengths and filenames are valid on the operating system the tool was run on; any renames are recorded in `_path_renames.csv` at the root.
- The folder is the only artefact the consumer is expected to read. No out-of-band manifests, sidecar files, or hidden state are required.

A consumer reading a `--path` that does *not* contain `package.xml` must not act on the contents; the publish is either in progress, incomplete, or failed.

The tool does not publish a list of what was excluded into the published path. The audit log carries that detail and is for human review.

## 10. Audit log

Each run writes one log file to a fixed system location:

- Windows: `%LOCALAPPDATA%\sf-clean-room\logs\<utc_timestamp>-<org_alias>.log`
- POSIX: `${XDG_STATE_HOME:-~/.local/state}/sf-clean-room/logs/<utc_timestamp>-<org_alias>.log`

Contents:

- Invocation arguments.
- Selected temp root and per-run temp subdirectory.
- Per-type enumeration counts (raw and post-filter).
- Per-batch composition (types, member counts, weight).
- Retrieve outcomes (async IDs, durations, statuses).
- Scrub stage outcomes.
- Publish actions (path cleared, files moved, `package.xml` placed).
- Final result and exit code.

Logs are append-only at the file system level — each run produces a new file. The tool does not rotate logs in v1; that is the operator's responsibility.

### 10.1 Console feedback

During a run, milestone log lines are also tee'd to **stderr** so an operator (human or agent) can see progress in real time. This is important because a single `retrieve` against a large org can poll for minutes, and a silent process is indistinguishable from a hung one.

What streams:

- Section markers (`=== enumerate ===`, `=== filter ===`, `=== batch ===`, `=== retrieve ===`, `=== scrub ===`, `=== publish ===`).
- Milestone lines: enumeration start, post-enumeration counts, deny-list exclusions, batch plan summary, per-batch submit / async-id / **poll-tick** / completion / extract, scrub stage outcomes, publish step.

What does **not** stream (file only, to keep stderr scannable):

- The full per-type breakdown of the batch plan. The summary line streams; the line-by-line detail is in the audit log.

The poll-tick line on long retrieves is the explicit anti-hang signal: every `POLL_SECS` interval, the tool emits a line including elapsed seconds and the async retrieve id. An operator that sees no movement for longer than that interval may treat the process as stuck.

Stdout remains reserved for command output: `--dry-run` prints the batch plan to stdout, and a successful real run prints the final published path and audit-log path. This split lets stdout be piped or captured without interleaving with progress chatter.

## 11. Distribution and invocation

- SF Clean Room is a standalone Python package, installable as a CLI entry point (`sf-clean-room`).
- It does **not** expose a library API in v1 — only the CLI. This is deliberate: it removes the temptation for other automation to call into the pipeline programmatically and bypass the CLI's guarantees.
- It is invoked as a subprocess by an AI agent (or by a person at a shell, for diagnostic runs). There is no daemon, no scheduler, no listener, no MCP server, and no webhook. The agent shells out, reads stdout/stderr, checks the exit code, and then reads the published folder.
- One run per invocation. The CLI does not loop, watch, or schedule. An orchestrator that wants periodic refresh re-invokes the binary.
- Exit codes: `0` on a completed publish (including the §8 "no components" case), non-zero on any abort. The exact non-zero codes are not part of the contract; agents should branch on zero vs non-zero and read stderr / the audit log for detail.

## 12. Open questions

- **Audit log location.** Fixed system location keeps logs tamper-resistant by separation from the published path. The trade-off is operator discoverability; a `--log-path` flag would help, but it widens the CLI surface. Default in this draft: fixed system location, no flag.
- **`--dry-run` and future scrub stages.** Once scrub stages exist, should dry-run exercise them against a previous temp directory, or only against the freshly enumerated plan? Current intent: dry-run is plan-only.
- **Custom Metadata re-enablement.** A v2 opt-in to allow-list specific Custom Metadata namespaces would recover the benign majority of records. Worth doing only if there is concrete demand.
- **Atomic publish.** The stage-swap described in §8 is straightforward but adds an extra rename failure mode. Worth implementing in v2.
- **Multiple org aliases.** Out of scope for v1. The tool is single-org per invocation. Multi-org orchestration belongs in a wrapper, not in the tool.

---

## Appendix A — Glossary

| Term | Meaning |
|---|---|
| Org alias | A Salesforce CLI alias or username that resolves to an authenticated session via the local Salesforce CLI configuration. |
| Retrieve | A Salesforce Metadata API operation that returns a zip of requested metadata components. |
| Component | One named instance of a metadata type — e.g. one Apex class, one flow. |
| Batch | A subset of the filtered enumeration submitted in a single `retrieve` call. |
| Temp root | The root directory under which per-run temp subdirectories are created. Configurable via config file; not via CLI. |
| Per-run temp subdirectory | A fresh directory created under the temp root for a single invocation; holds all intermediate output. |
| Published path | The `--path` argument; the consumer-visible output directory. |
| Sentinel | `package.xml`, moved last into the published path to signal publish completion. |
| Scrub stage | A pluggable check that runs against the per-run temp subdirectory between extraction and publish. v1 ships with one no-op stage. |
