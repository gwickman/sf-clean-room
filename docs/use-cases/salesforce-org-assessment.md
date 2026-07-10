# Use AI to assess a Salesforce org without exposing raw PII

## Problem

Architects, consultants, security reviewers, and managed-service teams often need a structured view of a Salesforce org for health checks, security reviews, technical-debt discovery, pre-sales scoping, and governance monitoring.

## Why direct AI access is the wrong boundary

An AI agent with direct Salesforce access gets a live session and can encounter confidential records, PII, credential-adjacent metadata, and customer-specific operational detail. sf-clean-room keeps the agent on the file-consumer side of the boundary.

## How sf-clean-room helps

- `get_metadata` exports a Salesforce metadata tree with sensitive metadata types excluded before retrieve.
- `get_records` exports selected records with field handling applied in flight.
- `get_event_logs` exports EventLogFile CSVs with usernames, IPs, URLs, and free-text fields handled before publish.
- `get_technical_objects` exports Tooling and system objects that describe automation, privileges, jobs, login/session activity, setup audit trail, usage telemetry, and limits.
- `get_security_health_check` exports the org Security Health Check score and per-setting risk table.
- `get_code_analysis` runs Salesforce Code Analyzer over a completed `get_metadata` output folder.

## Minimal workflows

First authenticate a Salesforce CLI alias:

```bash
sf org login web --alias myorg
```

For an org assessment:

```bash
sf-clean-room get_metadata --org-alias myorg --path ./out/metadata --dry-run
sf-clean-room get_metadata --org-alias myorg --path ./out/metadata
sf-clean-room get_technical_objects --org-alias myorg --path ./out/technical --dry-run
sf-clean-room get_technical_objects --org-alias myorg --path ./out/technical
sf-clean-room get_security_health_check --org-alias myorg --path ./out/security --dry-run
sf-clean-room get_security_health_check --org-alias myorg --path ./out/security
```

For EventLogFile review:

```bash
sf-clean-room get_event_logs --org-alias myorg --path ./out/event-logs --dry-run
sf-clean-room get_event_logs --org-alias myorg --path ./out/event-logs
```

For code analysis:

```bash
sf-clean-room get_code_analysis --org-alias myorg --metadata-path ./out/metadata --path ./out/code-analysis --dry-run
sf-clean-room get_code_analysis --org-alias myorg --metadata-path ./out/metadata --path ./out/code-analysis
```

## What the AI sees

The AI consumes only completed published folders. A folder is complete when its sentinel file is present:

- `package.xml` for metadata.
- `_field-handling-applied.csv` for records, event logs, and technical objects.
- `securityhealthcheck_<alias>.json` for Security Health Check.
- `_summary.json` for code analysis.

## What it does not do

sf-clean-room does not write to Salesforce, does not handle Salesforce authentication, does not decide whether a use case complies with an AI policy or client agreement, and does not make generated outputs suitable for public posting.
