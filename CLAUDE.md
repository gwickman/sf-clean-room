# CLAUDE.md — sf-clean-room

Project-specific guidance for AI coding agents working in this repository. The design docs (see §Design documents below) are authoritative — read the relevant one before making changes. This file points at the parts that are easy to break by accident.

## Design documents

| Doc | Covers |
|---|---|
| `docs/design/01-design-v1.md` | `get_metadata` — authoritative contract |
| `docs/design/02-design-v2.md` | `get_records` — authoritative contract |
| `docs/design/03-design-2.1.md` | `get_metadata` v2.1 — limited-permissions resilience |
| `docs/design/04-design-v3.md` | `get_event_logs` — authoritative contract |
| `docs/design/05-design-v4.md` | `get_technical_objects` — authoritative contract |
| `docs/reference/salesforce-security-health-check.md` | `get_security_health_check` — output reference |
| `docs/reference/salesforce-code-analyser.md` | `get_code_analysis` — output reference |
| `docs/00-design-principles.md` | Goals and principles behind the full command family |
| `docs/docs-change-log.md` | Decision history and version-to-version evolution |
| `docs/regression-testing.md` | Testing guide for chatbot-driven live regression |

## Source control

This is internal tooling, not a client repository. An AI coding agent working in this repo may stage, commit, and push here when asked.

Normal good practice still applies: never commit secrets or extracted data (`.test-output/` and credentials stay out of version control), write clear commit messages, and don't rewrite already-published history.

## What this tool is

`sf-clean-room` is an **AI-operated CLI** with six commands under one dispatcher:

- `get_metadata` — exports Salesforce **metadata** to a folder safe for downstream automated consumers. Safety is structural: sensitive metadata categories are filtered out at enumeration, before any `retrieve`. Sentinel: `package.xml`.
- `get_records` — exports Salesforce **record data**, anonymised in flight: every field is classified and DROP/HASH applied before any value is written, so raw PII never reaches a published file. Read-only (describe + `SELECT` only). Sentinel: `_field-handling-applied.csv`.
- `get_event_logs` — exports **EventLogFile** activity data, anonymised in flight, incrementally (one dated subfolder per run). IPs → network prefix, usernames hashed, URLs query-stripped. Sentinel: `_field-handling-applied.csv`.
- `get_technical_objects` — exports **40 technical objects** (Tooling entities, system tables, REST endpoints), anonymised in flight via a two-layer classifier. Snapshot publish model (clear-and-republish). Sentinel: `_field-handling-applied.csv`.
- `get_security_health_check` — exports the org's **Security Health Check** score and per-setting risk table via the Tooling API. No classifier — all org-configuration data. Sentinel: `securityhealthcheck_<alias>.json`.
- `get_code_analysis` — runs **Salesforce Code Analyzer** locally over a `get_metadata` output folder. No Salesforce session; requires the `sf code-analyzer` plugin. Sentinel: `_summary.json`.

The operator of this CLI is an AI agent, not a person. Design decisions consistently favour predictability and discoverability over flexibility.

## Invariants — do not weaken

These are load-bearing. If a change touches any of them, it is not a routine change; flag it.

1. **Deny list is source-only.** The list of excluded metadata types (`docs/design/01-design-v1.md` §6) is a constant in source. There must be no CLI flag, env var, config-file entry, or runtime mechanism that loosens it. "Add a flag to opt back in" is the wrong answer to every question.
2. **Two-phase output.** Retrieve and extract land in a per-run temp directory. The published path is only mutated at the final publish step (§5.6). Do not collapse these phases.
3. **`package.xml` is the sentinel.** It is the *last* file moved into the published path. Consumers treat its presence as the signal that the publish completed. Anything that writes `package.xml` before the rest of the tree is in place is a bug.
4. **Fail closed.** Any error in retrieve, extract, or scrub aborts the publish. The published path is either the previous run's output or the new run's output — never a partial mix (except in the narrow §8 atomicity gap, which is documented and bounded).
5. **CLI surface is narrow.** The dispatcher exposes `--help` and `--version` at the top level. Per-command flag surfaces (complete lists — no other flags exist):
   - `get_metadata`: `--org-alias`, `--path`, `--dry-run`
   - `get_records`: `--org-alias`, `--path`, `--only`, `--where`, `--plan`, `--dry-run`
   - `get_event_logs`: `--org-alias`, `--path`, `--only`, `--where`, `--plan`, `--dry-run`
   - `get_technical_objects`: `--org-alias`, `--path`, `--plan`, `--only`, `--limit`, `--dry-run`
   - `get_security_health_check`: `--org-alias`, `--path`, `--dry-run`
   - `get_code_analysis`: `--org-alias`, `--metadata-path`, `--path`, `--dry-run`

   All flags are *narrowing/specification* inputs; none disables a classifier, loosens the deny list, or bypasses the read-only/no-raw-dump guarantees. New capabilities are new subcommands, not new flags on existing ones.
6. **`get_records` is read-only and never dumps raw values.** It issues only describe and `SELECT` queries; there is no write path. The raw query result stays in process memory; DROP fields are never selected; HASH/DERIVE is applied before any value is written. Do not add a path that writes a raw, unclassified extract to disk.
7. **The classifier is source-controlled.** Its rules live in `constants.py`/`classify.py` and produce *recommendations*. A reviewed plan may override them, but special-category keeps require a justification (else they downgrade to DROP) — do not remove that enforcement, and do not make the classifier itself runtime-overridable.
8. **No library API.** Only the CLI entry point. Importing internals from another Python process is not a supported integration path.

## `--help` is part of the contract

The operator is an agent that may have discovered the binary without prior context. `--help` is how it grounds itself, at two layers:

- **Top-level** (`sf-clean-room --help`): tool purpose, list of available commands, authentication, fixed temp/config/log locations, exit codes, pointer to per-command help.
- **Per-command** (`sf-clean-room <command> --help`): the contract specific to that command — flags, publish-folder contract, sentinel rule, deny-list rationale, batch ceilings.

Both must run without authentication, without a config file, and without writing anywhere. Their content must be **generated from the same source constants that drive the runtime** (deny list, default temp roots, API version). Hand-maintained help text drifts; do not introduce that.

If you change a constant that appears in either help layer, verify the help output still reflects reality. If you add a new subcommand, register it on the top-level parser so it shows up in the dispatcher list, and give it its own `--help` with the same grounding properties.

## Pipeline (read §5 of the design for detail)

```
enumerate -> filter -> batch -> retrieve+extract (to temp) -> scrub (no-op in v1) -> publish
```

- Enumeration uses `describeMetadata` + per-type / per-folder `listMetadata`.
- Batching is **weight-aware**, not just count-aware. Heavy types (bundles, composites) carry per-type weight multipliers. The 10,000-component and ~600 MB compressed-zip limits per retrieve are real; weight-aware batching is what keeps multi-batch runs correct.
- Extraction must be safe on Windows: zip-slip prevention, `\\?\` long-path prefix, filename sanitisation (illegal chars, trailing dots/spaces, over-long components shortened with a stable hash suffix), and a `_path_renames.csv` audit trail published with the rest of the output.
- The scrub stage list exists in v1 with a single no-op stage. The orchestration code and the stage contract (returns Clean or Findings) are real; the scanners are not yet. Future scanners plug in here without changing the consumer-visible contract.

## Failure handling

- Auth / enumerate / retrieve / extract / scrub failures: abort, retain temp for forensics, **do not touch the published path**.
- Empty enumeration after filtering: publish an empty manifest (`package.xml` only) and exit zero. Consumers can still rely on the sentinel.
- Exit codes: zero on completed publish, non-zero on any abort. Specific non-zero values are not part of the contract.

## What goes in source vs config vs CLI

- **CLI:** only the flags listed in Invariant 5 above.
- **Config file** (fixed location, see §7.1): `temp_root` override. Nothing else in v1.
- **Source constants:** deny list, type weights, batch ceilings, API version, OS-aware default temp/log paths.

If you are tempted to add a new CLI flag, default it into source instead. If you are tempted to add a config-file knob, ask whether it weakens any of the invariants above — if it does, it doesn't belong there either.

## Style and conventions

- Python, single CLI entry point (`sf-clean-room`).
- Cross-platform; Windows is a first-class target. Long paths, illegal characters, and filename length limits are not edge cases here — they are the common case.
- Prefer explicit, mechanism-first error messages. The operator is an agent reading stderr to decide what to do next; vague messages cost re-runs.
- Audit log is the structured record (§10). stdout/stderr are for the operator; the log is for humans investigating after the fact.

## Dev install gotcha

`pip install -e .` on this project's setuptools backend silently falls back to a non-editable file copy, so edits to `src/` don't take effect until reinstall. For real editable mode use:

```
pip install -e . --config-settings editable_mode=compat
```

Verify with `python -c "import sf_clean_room.audit, inspect; print(inspect.getfile(sf_clean_room.audit))"` — the path should point into `src/sf_clean_room/`, not site-packages or a `build/` shim.

## When in doubt

Re-read `docs/design/01-design-v1.md`. If the design is ambiguous, surface the ambiguity rather than picking silently. The design is short on purpose; gaps are usually intentional and worth a conversation.
