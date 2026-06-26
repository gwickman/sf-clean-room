# 01 — Metadata Export (v1): Goals and Requirements

**Status:** Ideation / rationale companion to the v1 contract.
**Governed by:** [`00-design-principles.md`](../00-design-principles.md) — the family-wide principles this version instantiates.
**Authoritative contract:** [`01-design-v1.md`](../design/01-design-v1.md). Where this document and the design disagree, the design wins; flag the drift.

This document sits one altitude above the design. The design says *what the tool does and how*; this says *what problem v1 solves, for whom, and which requirements the design is satisfying*. It exists so that a later reader (human or agent) can judge whether a proposed change still serves the original goals.

---

## 1. The problem

An AI agent doing architecture review, gap analysis, or integration design on a Salesforce org needs to ground itself on the org's **real structure** — objects, fields, Apex, flows, validation rules — not on guesses. The obvious move is to point the agent at a metadata extract.

The obvious move is unsafe. A naive `sf project retrieve` pulls everything, including metadata categories that routinely carry **credentials, credential references, identity material, and opaque binary blobs**: `ConnectedApp` (OAuth consumer keys), `AuthProvider` (consumer secrets, IdP endpoints), `NamedCredential` / `ExternalCredential` (endpoint URLs and the integration topology), `CustomMetadata` (frequently abused as a key-bag where the secret is the record's `DeveloperName` and so sits in the *filename*, invisible to content scans), and `Document` / `StaticResource` / `ContentAsset` (arbitrary uploaded binaries). Under any reasonable acceptable-use policy, live credentials and secrets are **Restricted** — an AI agent must never process them. A downstream consumer that reads such an extract is reading Restricted data.

So the requirement is not "retrieve metadata." It is **"produce a metadata folder that is safe to hand to an automated consumer without that consumer having to know what's sensitive."**

## 2. Who the actors are

The framing that drives almost every design decision:

- **Operator** — an AI agent (not a person) that invokes the CLI as a step in a larger workflow. It may have discovered the binary with no prior context. It reads stderr and exit codes to decide what to do next.
- **Consumer** — frequently the *same* agent, plus other automated readers: code analysers, search indexers, CI. The consumer talks to a directory, never to Salesforce.
- **Maintainer** — a human, with code review. The only party allowed to change the safety-critical surfaces.

The operator/maintainer split is load-bearing. The operator can *run* the tool but cannot *weaken* it; weakening is a maintainer action gated by human review. This is why "add a flag to opt back in" is the wrong answer to every question — it would hand a safety lever to the operator.

## 3. Goals

1. **Structural safety, not behavioural.** A consumer reading the published folder must not need to know which metadata types are sensitive, because the sensitive categories were never written there. Safety is a property of the artefact, not a discipline the consumer must practise.
2. **Self-grounding for agents.** An agent that finds the binary cold can run `--help` (top-level and per-command) and learn the full contract: what it produces and where, the sentinel rule, the deny-list rationale, dry-run semantics, exit codes — without authenticating, without a config file, without writing anywhere.
3. **Predictability over flexibility.** Because the operator is an agent, every knob is a chance to be coerced or to drift. A narrow, fixed surface is easier to reason about and harder to misuse than a configurable one.
4. **Scale correctly without the consumer noticing.** Large orgs exceed a single `retrieve`. The tool may run many batches; the consumer must still see one coherent output.
5. **Extensibility without contract change.** Future safety stages (secret scanners, PII detectors, content rewriters) must be insertable without altering what the consumer sees. v1 builds the slot, not the scanner.

## 4. Requirements

### 4.1 Functional

- **Exclude at source.** The deny list (design §6) is applied to the metadata enumeration *before* any `retrieve`. Excluded types never transit the network, never land in temp, never appear in any artefact — Restricted data never reaches disk even transiently.
- **Enumerate completely.** `describeMetadata` for the org's API version; per-folder `listMetadata` for foldered types (`Dashboard`, `Document`, `EmailTemplate`, `Report`); per-type `listMetadata` otherwise.
- **Weight-aware batching.** Respect Salesforce's hard limits — 10,000 components and ~600 MB compressed zip per retrieve. Count alone is insufficient because a few bundle/composite types (`ExperienceBundle`, `SiteDotCom`, `LightningComponentBundle`, `AuraDefinitionBundle`) dominate compressed size. Per-type weight multipliers (see `constants.py`: `ExperienceBundle`=500, `SiteDotCom`=200, bundles 15–20) keep multi-batch runs correct. Most runs are single-batch because the heaviest binary types are already denied.
- **Two-phase output.** Retrieve and extract land in a per-run temp directory; the published path is mutated only at the final publish step. The temp area is where future scrub stages plug in.
- **Sentinel publish order.** `package.xml` is the **last** file moved into the published path. Its presence is the consumer's go-signal.
- **Dry-run.** Enumerate, filter, batch, and report the plan — no `retrieve`, no temp write, no publish mutation.
- **Cross-platform extraction.** Windows is first-class: zip-slip prevention, `\\?\` long-path prefix, filename sanitisation (illegal chars, trailing dots/spaces, over-long components shortened with a stable hash suffix), and a published `_path_renames.csv` audit trail.
- **Audit log.** Per-run, fixed system location: excluded counts, batch composition, retrieve outcomes, publish actions.

### 4.2 Non-functional / safety invariants

These are the requirements that make the goals real. They are restated in `CLAUDE.md` as "do not weaken":

- **Deny list is source-only.** No CLI flag, env var, or config entry loosens it. Changed only by a human-authorized dev task with review.
- **Narrow CLI surface.** Top level: `--help`, `--version`. `get_metadata`: `--org-alias`, `--path`, `--dry-run`. Nothing else — no `--temp-root`, `--exclude`, `--include`, `--skip-scrub`. New tools are new subcommands, not new flags.
- **Fail closed.** Any error in retrieve/extract/scrub aborts the publish; the published path is the previous run's output or the new run's, never a partial mix (except the bounded §8 atomicity gap).
- **No library API.** CLI only, so other automation cannot import internals and bypass the guarantees.
- **Help generated from source constants.** Help text is derived from the same constants that drive the runtime (deny list, temp roots, API version), so it cannot drift from behaviour.

### 4.3 The output contract

A consumer reading a `--path` containing `package.xml` may assume: the run completed; no denied type is present; paths/filenames are valid for the host OS with renames recorded in `_path_renames.csv`; the folder is the only artefact it needs. No `package.xml` → do not read.

## 5. Out of scope for v1 (and why)

- **Record / data extraction** — different safety model (PII, not credentials). This is v2; see [`02-data-download.md`](02-data-download.md).
- **PII hashing / content redaction** — belongs with data, not metadata.
- **Working secret scanners** — the scrub *slot* and stage contract (returns Clean or Findings) exist; the scanners do not. Building the slot first means later scanners need no contract change.
- **Allow-listing specific `CustomMetadata` namespaces** — would recover the benign majority of records, but only worth it on concrete demand (design §12).
- **Multi-org runs, diff-against-previous** — orchestration concerns that belong in a wrapper, not the tool.

## 6. How the design satisfies the goals (traceability)

| Goal | Mechanism in the design |
|---|---|
| Structural safety | Exclude-at-source filter (§2.1, §5.2, §6); denied types never retrieved |
| Self-grounding | Two-layer `--help`, generated from source constants (§4.4) |
| Predictability | Narrow CLI surface, source-only deny list, fixed temp/log locations (§4, §6, §7, §10) |
| Scale invisibly | Weight-aware batching (§5.3); single coherent published folder |
| Extensibility | Temp-then-publish (§2.2) + scrub stage contract with a v1 no-op (§5.5) |
| Trust the artefact | `package.xml` sentinel published last (§3, §5.6); output contract (§9) |
| Don't poison on failure | Fail-closed with retained temp for forensics (§5.6, §7.3, §8) |

## 7. Open questions

From design §12:

- **Atomic publish.** The publish step's delete-then-move has a documented non-atomic window (§8). A stage-swap (`<path>.new` → rename) would close it. The sentinel rule already makes the gap safe to detect; atomicity is a robustness upgrade, not a safety fix.
- **`CustomMetadata` re-enablement.** Allow-listing specific namespaces would recover the benign majority of records — worth doing only on concrete demand.
- **Dry-run vs future scrub.** Once scrub stages exist, the current intent is that dry-run stays plan-only.
