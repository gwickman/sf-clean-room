## Summary

<!-- What does this PR change and why? One to three sentences. -->

## Risk surface

<!-- Check any that apply. Load-bearing invariants are listed in CLAUDE.md §Invariants. -->

- [ ] Touches the deny list (Invariant 1) — requires design-doc update
- [ ] Changes the two-phase publish or sentinel ordering (Invariants 2–3) — requires design-doc update
- [ ] Changes classifier rules or adds a classifier override path (Invariant 7)
- [ ] Adds or changes a CLI flag (Invariant 5)
- [ ] Changes anonymisation behaviour (drop/hash/derive logic)
- [ ] None of the above

## Tests run

- [ ] `python -B -m pytest -m "not live" -q -p no:cacheprovider` — all pass
- [ ] `sf-clean-room --help` and relevant `<command> --help` — output reflects changes
- [ ] Live regression (if applicable) — org alias: `<alias>`, command: `<command>`

## Documentation

- [ ] Design doc in `docs/design/` updated (if contract changed)
- [ ] `CLAUDE.md` flag list updated (if flags added or removed)
- [ ] `--help` text reflects changes (generated from source constants — no manual drift)
