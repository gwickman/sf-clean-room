# Synthetic sample outputs

This folder contains synthetic sf-clean-room output shapes. The files show the publish layout and sentinel files used by downstream consumers.

The data is artificial. Real outputs are for controlled private consumers and are not automatically suitable for public posting.

| Folder | Source command | Sentinel |
|---|---|---|
| `metadata/` | `get_metadata` | `package.xml` |
| `records/` | `get_records` | `_field-handling-applied.csv` |
| `event_logs/` | `get_event_logs` | `_field-handling-applied.csv` |
| `technical_objects/` | `get_technical_objects` | `_field-handling-applied.csv` |
| `security_health_check/` | `get_security_health_check` | `securityhealthcheck_acme_dev.json` |
| `code_analysis/` | `get_code_analysis` | `_summary.json` |
