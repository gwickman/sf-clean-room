# Security policy

## Reporting a vulnerability

Please do **not** report security vulnerabilities through public GitHub issues.

Instead, open a [GitHub Security Advisory](../../security/advisories/new) (private by default) or email the maintainers directly. We will acknowledge the report within 72 hours and aim to release a fix within 30 days for confirmed vulnerabilities.

## What to report

- Bugs that could allow the anonymisation pipeline to leak raw PII or sensitive values to disk
- Bugs that could allow the deny list to be bypassed at runtime
- Bugs that could allow the tool to write to a Salesforce org (it is read-only by design)
- Dependency vulnerabilities in the published package

## What not to include in any report

Do not attach or reference:

- Salesforce org output, exports, logs, or any extracted data
- Credentials, session tokens, or API keys
- Customer data or personally identifiable information

## Scope

sf-clean-room is a local CLI. It does not run as a service, does not expose a network interface, and does not store credentials. The attack surface is the anonymisation pipeline (classifier, deny list, publish atomicity) and the dependency chain.

## Supported versions

Only the current release on `main` is supported. We do not backport fixes to older versions.
