# 00 — Design Principles

**Status:** Foundational. These principles govern the whole `sf-clean-room` tool family. They are garnered from [`01-metadata-ideation.md`](01-metadata-ideation.md) (v1, metadata) and [`02-data-download.md`](02-data-download.md) (v2, records), and they sit above both — when a specific design choice is in question, check it against these.

The principles are not all equally rigid, and that is deliberate. Some protect against harms that need no intelligence to recognise (live secrets, writes to production) and are therefore **absolute**. Others govern judgment calls (which PII fields matter for a given analysis) and are therefore **strong defaults a trusted operator can refine**. The sections below mark which is which.

---

## A. The core safety model

### A1. Abstract the operator from the source. *(load-bearing)*
The consumer talks to a local artefact — a directory, a set of files — never directly to Salesforce. In v1 the consumer reads a published metadata folder; in v2 the chatbot goes through `get_records` rather than running raw `sf data query`/`export` itself. This abstraction is the most durable safety property the family has, because it holds regardless of how strict or lenient any individual filter is. Everything else reinforces it.

### A2. Handle the dangerous thing upstream of the operator.
Safety acts *before* the consumer can see anything unsafe. Metadata: credential-bearing types are excluded at enumeration, before any `retrieve` — they never transit the network or land on disk. Records: values are classified, hashed, or dropped **in flight**; there is no code path that writes a raw, unclassified extract to disk or transmits it beyond the authorised `sf` CLI. The consumer only ever receives material that already passed the safety step.

### A3. Distinguish zero-judgment harms from judgment calls.
- **Zero-judgment harms** — live secrets and credentials (the metadata deny list), and any write to Salesforce. Recognising these needs no context and no intelligence. They are **absolute**: source-controlled, non-overridable at runtime, no CLI flag, no config knob.
- **Judgment calls** — which PII-shaped fields matter for a particular analysis, whether an identifier should hash or pass, whether an essay field is needed. These benefit from context the tool does not have. Here the tool supplies a **strong safe default and a clear recommendation**, and a trusted operator refines it.

Lock the former; default-and-recommend the latter. Conflating the two is what makes a design either leaky (everything overridable) or fragile (everything rigid).

### A4. Read-only, absolutely.
The tool never mutates Salesforce — no create/update/delete/upsert/deploy, no REST POST/PATCH/DELETE. This needs no judgment and admits no override, in any version. A write is catastrophic in a way a read never is.

## B. The operator relationship

### B1. Assume a flagship, privacy-aware operator.
The operator is a top-tier model that is already making a genuine effort to follow the governing privacy and acceptable-use rules. Design to **leverage that intelligence**, not to treat the operator as an adversary to be mechanically constrained at every step. Over-rigid guards waste the operator's capability, multiply failure points, and make the tool fragile. The tool does the mechanical heavy lifting (bulk extraction, in-flight hashing, raw-never-dumped, audit); the operator brings the analytical and consent context the tool cannot have.

### B2. Forcing a human decision is an anti-pattern.
The tool must encourage **full autonomy**. When it meets ambiguity, it resolves with a safe default, states the situation plainly in its response, and recommends an action — it does **not** halt and demand a human. "Abort and make a person decide" is a last resort for genuine zero-judgment harms (A3), not a routine control-flow tool. Anything an intelligent operator can resolve, the tool should hand back as a clear recommendation, not a wall.

### B3. Tool and operator collaborate iteratively.
The tool recommends; the operator refines; they converge. The canonical example: the tool runs a schema scan and returns an **annotated schema with recommended classifications**; the operator overrides where it knows the analytical need or the user has authorised specific data; a subsequent run extracts per the agreed plan. Runs are cheap, self-describing, and repeatable so this loop is the normal path, not an exception.

Once converged, the agreed plan is a **persistable specification**: the operator is needed to *author* the safety decisions, not to *execute* them. A reviewed plan therefore runs unattended on a schedule (no agent in the loop), staying safe-by-default against schema drift — new fields a stale plan never saw fall back to the conservative default rather than leaking. The intelligence is spent once, at authoring time; execution is mechanical and repeatable.

### B4. Safe by default, flexible by intent.
The zero-effort outcome must be the safe one — strong conservative defaults so that doing nothing special yields a safe artefact. Loosening is always **explicit and auditable**: the operator states the override, the tool records it. This is what makes trusting the operator (B1) sound rather than reckless — every judgment call that departed from the default is visible for human review.

## C. Discoverability and mechanics

### C1. Self-grounding via `--help`.
An agent that discovers the binary cold can run top-level and per-command `--help` and learn the full contract — purpose, commands, inputs, sentinel rule, output location, exit codes — without authenticating, without a config file, and without writing anywhere. Help text is generated from the same source constants that drive the runtime, so it cannot drift from behaviour.

### C2. Two-phase, sentinel-gated, fail-closed output.
Work lands in a per-run temp area; the published path is mutated only at a final step; a **sentinel file** is written last to signal completeness (`package.xml` for metadata, `_field-handling-applied.csv` for records). A consumer that sees the sentinel may trust the artefact; absent the sentinel it must not read. Any error in the pipeline aborts the publish — the published path is the previous run's output or the new run's, never a partial mix. Failure retains temp for forensics; it never poisons the published path.

### C3. One discoverable binary; subcommands, not flags.
New capabilities are new subcommands under one dispatcher (`get_metadata`, `get_records`, …), sharing authentication, audit log, temp handling, and this philosophy. A new capability is never bolted on as a new flag that could widen an existing command's safety surface.

### C4. Right-sized CLI surface — narrow for safety, flexible for the task.
The surface is as small as the task allows and no smaller. **Narrowing** inputs (object selection, a validated `--where` predicate) are safe and allowed: they reduce what is extracted and cannot expose anything the classifier would otherwise handle. Knobs that disable safety machinery wholesale, or that hand the operator a silent lever over a zero-judgment harm (A3), do not belong on the CLI. The narrowness is part of the safety story; the flexibility is part of the autonomy story (B1–B4); C4 is where they are balanced rather than traded off.

### C5. Audit everything that matters.
Every run records what it did — exclusions, classifications including operator overrides, batch composition, retrieve outcomes, publish actions — to a fixed location for human review. The audit trail is the record that makes trust verifiable: it is how a human later confirms the operator's judgment calls were sound.

### C6. Design docs hold current facts; decision history lives in the change log.
The design and ideation documents state what the design *is* and *requires* — not the story of how it got there. Version-to-version evolution, superseded approaches, "this used to work differently," and the reasoning behind a changed decision all belong in [`../docs-change-log.md`](../docs-change-log.md), which may be as verbose as needed. Keeping history out of the design docs keeps them short, current, and free of stale comparisons; keeping it *somewhere* preserves the reasoning for anyone who needs it. When a design fact changes, update the doc to the new fact and append the before/after and the why to the change log. Comparing two tools that coexist in the family (e.g. how a principle applies to metadata vs. records) is a present-tense design fact and stays in the docs; narrating how a single tool's design shifted over time is history and moves to the log.

---

## How the principles divide v1 from v2

Both versions share A1, A2, A4, B-discoverability and all of C. The visible difference is **A3 applied to different threats**:

- v1 (metadata) is almost entirely zero-judgment: the dangerous categories are credential-bearing *types*, recognisable without context, so the deny list is a locked source constant and the operator cannot weaken it. v1's operator relationship is therefore mostly "operator runs, maintainer changes safety."
- v2 (records) is mostly judgment calls: which *fields* matter is context-dependent, so the classifier supplies recommendations and the trusted operator refines them (B1–B4). The locked floor shrinks to A4 (read-only), A2 (no raw dump), and A1 (abstraction) — and the audit trail (C5) carries the rest.

This is not a contradiction between the versions; it is the same principle (A3) producing different rigidity because the threats differ.
