# Contributing to sf-clean-room

## Scope

sf-clean-room is an AI-operated, read-only CLI for exporting anonymised Salesforce data to local folders. Contributions that stay within that scope — bug fixes, documentation improvements, new extraction commands, or improvements to the anonymisation pipeline — are welcome.

New capabilities should be new subcommands, not new flags on existing ones. See `docs/00-design-principles.md` for the principles the whole command family answers to, and the design docs in `docs/design/` for each command's authoritative contract.

## What not to include in issues or pull requests

Do not paste, attach, or reference:

- Salesforce org output, exports, logs, or any extracted data
- Credentials, session tokens, API keys, or `.sfdx` / `.sf` profile directories
- Customer data, client names, or personally identifiable information

This applies even if the data has been anonymised — the issue tracker is public.

## Development setup

Clone the repository and install in editable mode. The setuptools backend on this project silently falls back to a non-editable copy without the extra flag:

```bash
pip install -e . --config-settings editable_mode=compat
```

Verify the install points into `src/`:

```bash
python -c "import sf_clean_room.audit, inspect; print(inspect.getfile(sf_clean_room.audit))"
```

The path should end in `src/sf_clean_room/audit.py`, not `site-packages`.

## Tests

Run the offline suite before opening a pull request:

```bash
python -B -m pytest -m "not live" -q -p no:cacheprovider
```

All offline tests must pass. Live tests (`-m live`) require a pre-authenticated Salesforce CLI alias in `tests/live_org.toml` and are opt-in.

## Design-doc rule

Every change to a command's behaviour — including bug fixes that affect output shape, sentinel rules, or the anonymisation pipeline — should be reflected in the relevant design doc in `docs/design/`. The design docs hold current facts, not history; put the *why-it-changed* in a commit message or the change log (`docs/docs-change-log.md`).

## Pull requests

Use the pull request template. In particular, note the risk surface: does the change touch the deny list, the classifier, the sentinel ordering, or the publish atomicity? Those are load-bearing — see `CLAUDE.md` § Invariants.
