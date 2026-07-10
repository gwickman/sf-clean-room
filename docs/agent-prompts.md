# Agent prompt examples

These prompts are for terminal-based coding agents that can run local commands. Replace the placeholders before use.

## First-time org assessment

```text
I want an AI-assisted Salesforce org assessment without giving the AI direct Salesforce access.

Repository: https://github.com/gwickman/sf-clean-room
Salesforce CLI org alias: <alias>
Output folder: <local-output-folder>

Read the sf-clean-room README and command help. Recommend the smallest command sequence for an org health, security, and technical-debt review. Do not request Salesforce credentials. Use only the existing Salesforce CLI alias and consume only published output folders after their sentinel files appear.
```

## Security and code-quality review

```text
I want a Salesforce security and code-quality review using sf-clean-room outputs.

Repository: https://github.com/gwickman/sf-clean-room
Salesforce CLI org alias: <alias>
Output folder: <local-output-folder>

Read the README and command help. Use get_metadata, get_security_health_check, get_technical_objects, and get_code_analysis where appropriate. Do not request Salesforce credentials. Consume only completed output folders with sentinels.
```

## EventLogFile review

```text
I want an AI-assisted review of Salesforce EventLogFile activity without exposing raw log values to the AI.

Repository: https://github.com/gwickman/sf-clean-room
Salesforce CLI org alias: <alias>
Output folder: <local-output-folder>

Read the README and get_event_logs help. Plan the run, execute it through the existing Salesforce CLI alias, and review only the published EventLogFile output after _field-handling-applied.csv appears.
```

## Managed-services snapshot

```text
I want a repeatable Salesforce managed-services snapshot using sf-clean-room.

Repository: https://github.com/gwickman/sf-clean-room
Salesforce CLI org alias: <alias>
Output folder: <local-output-folder>

Read the README and command help. Recommend a repeatable command sequence for metadata, technical objects, security health check, event logs, and any reviewed record extracts. Do not request Salesforce credentials. Use only completed output folders with sentinels.
```
