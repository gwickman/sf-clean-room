# How sf-clean-room compares to adjacent Salesforce tools

sf-clean-room is a read-only Salesforce org assessment CLI. It publishes anonymised local outputs for AI agents and other downstream tools without giving those consumers a Salesforce session.

## Short version

Use sf-clean-room when you want AI-assisted Salesforce analysis from local files, with sensitive metadata excluded before retrieve and record or event-log PII dropped, hashed, or derived before publish.

| Tool | Best fit | How sf-clean-room differs |
|---|---|---|
| Salesforce Data Mask / Data Mask & Seed | Masking and seeding sandbox data | sf-clean-room does not mutate Salesforce data or prepare sandboxes. It extracts local, read-only assessment outputs. |
| SFDMU | Moving records between orgs or CSV files, including migrations and seeding | sf-clean-room is not a migration tool and does not write to Salesforce. It focuses on controlled local analysis outputs. |
| Salesforce Inspector Reloaded | Interactive browser querying and export | sf-clean-room is a repeatable CLI with conservative anonymisation, audit artefacts, and sentinel-based publishing. |
| Salesforce Code Analyzer | Static analysis of Salesforce source and metadata | sf-clean-room can run Code Analyzer over retrieved metadata, but also gathers records, event logs, technical objects, and security posture. |
| EventLogFile retrieval scripts/exporters | Downloading Salesforce event logs | sf-clean-room anonymises EventLogFile data in flight and keeps it joined to broader org-assessment context. |
| Data clean-room platforms | Multi-party analytics and governed collaboration | sf-clean-room is a local CLI for Salesforce assessment outputs, not a hosted clean-room platform. |

## Why the distinction matters

Most adjacent tools either mutate an org, move records, require manual querying, or solve a narrower analysis problem. sf-clean-room is deliberately read-only: it uses an existing Salesforce CLI session, writes local outputs, and applies the safety boundary before downstream consumers see the files.

## References

- Salesforce Data Mask: https://help.salesforce.com/s/articleView?id=platform.data_mask_overview.htm&type=5
- Salesforce Data Mask & Seed: https://www.salesforce.com/platform/data-masking/
- SFDMU: https://forcedotcom.github.io/SFDX-Data-Move-Utility/
- Salesforce Inspector Reloaded data export: https://tprouvot.github.io/Salesforce-Inspector-reloaded/data-export/
- Salesforce Code Analyzer: https://developer.salesforce.com/docs/platform/salesforce-code-analyzer/overview
