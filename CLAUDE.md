# CLAUDE.md — sf-clean-room

Project-specific guidance for Claude Code working in this repository. Read `docs/design.md` before making changes; it is the authoritative contract. This file points at the parts of that contract that are easy to break by accident.

## What this tool is

`sf-clean-room` is an **AI-operated CLI** that exports Salesforce metadata to a local folder which is safe for downstream automated consumers (other agents, code analysers, CI). The safety guarantee is structural: sensitive metadata categories never enter the published folder because they are filtered out at enumeration time, before any `retrieve` call.

The operator of this CLI is an AI agent, not a person. Design decisions consistently favour predictability and discoverability over flexibility.

## Invariants — do not weaken

These are load-bearing. If a change touches any of them, it is not a routine change; flag it.

1. **Deny list is source-only.** The list of excluded metadata types (`docs/design.md` §6) is a constant in source. There must be no CLI flag, env var, config-file entry, or runtime mechanism that loosens it. "Add a flag to opt back in" is the wrong answer to every question.
2. **Two-phase output.** Retrieve and extract land in a per-run temp directory. The published path is only mutated at the final publish step (§5.6). Do not collapse these phases.
3. **`package.xml` is the sentinel.** It is the *last* file moved into the published path. Consumers treat its presence as the signal that the publish completed. Anything that writes `package.xml` before the rest of the tree is in place is a bug.
4. **Fail closed.** Any error in retrieve, extract, or scrub aborts the publish. The published path is either the previous run's output or the new run's output — never a partial mix (except in the narrow §8 atomicity gap, which is documented and bounded).
5. **CLI surface is narrow.** The dispatcher exposes `--help` and `--version` at the top level, and the v1 command `get_metadata` exposes `--org-alias`, `--path`, `--dry-run`. Nothing else. In particular: no `--temp-root`, no `--exclude`, no `--include`, no `--skip-scrub`. The narrow surface is the safety story. New tools added later (e.g. `get_records`) are new subcommands under the same dispatcher, not new flags on existing ones.
6. **No library API in v1.** Only the CLI entry point. Importing internals from another Python process is not a supported integration path.

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

- **CLI:** only the five flags above.
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

Re-read `docs/design.md`. If the design is ambiguous, surface the ambiguity rather than picking silently. The design is short on purpose; gaps are usually intentional and worth a conversation.
