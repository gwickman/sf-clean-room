"""CLI entry point.

Invocation shape::

    sf-clean-room <command> [<command-flags>...]

v1 ships one command:

* ``get_metadata`` - export Salesforce metadata to a folder safe for downstream
  automated consumers.

Top-level flags are limited to ``--help`` and ``--version``. Per-command flags
are documented by ``sf-clean-room <command> --help``.

All help text is generated from the source constants that drive the runtime
(deny list, default temp/config/log paths, API version) so it cannot drift.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sf_clean_room import __version__
from sf_clean_room.audit import audit_log
from sf_clean_room.config import load_config
from sf_clean_room.constants import (
    API_VERSION,
    CLASSIFIER_ACTIONS,
    MAX_COMPONENTS_PER_BATCH,
    MAX_WEIGHT_PER_BATCH,
    OPERATIONAL_DENY,
    SENSITIVITY_DENY,
    SKIP_BUCKETS,
)
from sf_clean_room.paths import default_config_path, default_log_dir
from sf_clean_room.pipeline import execute, make_run_paths, plan_only
from sf_clean_room.records_extract import AUDIT_SENTINEL
from sf_clean_room.session import get_session


# ---------- help-text builders (read from constants at call time) ----------

def _top_description() -> str:
    return (
        "Export Salesforce metadata (and, in future versions, records) to a "
        "folder that is safe for downstream automated consumers - other AI "
        "agents, code analysers, CI. Sensitive metadata categories are "
        "filtered out at enumeration time and never transit the network."
    )


def _top_epilog() -> str:
    return f"""
Commands
--------
  get_metadata          Export org metadata to --path with package.xml as the sentinel.
  get_records           Export org record data to --path (anonymised in flight) with
                        _field-handling-applied.csv as the sentinel.
  get_event_logs        Export org EventLogFile data to --path (anonymised in flight),
                        incrementally, with _field-handling-applied.csv as the sentinel.
  get_technical_objects Export 40 catalogued technical objects (Tooling entities, system
                        tables, REST metrics) to --path (anonymised in flight) with
                        _field-handling-applied.csv as the sentinel.

Authentication
--------------
Every command uses an existing Salesforce CLI (sf or sfdx) session. Authenticate
once with `sf org login web --alias <alias>` (or the sfdx equivalent), then pass
that alias as --org-alias to a command.

Fixed locations
---------------
API version           : {API_VERSION}
Default temp root     : {load_config().temp_root}
Config file (optional): {default_config_path()}
Audit log directory   : {default_log_dir()}
The config file may set ``temp_root = "..."`` to override the temp root.
Nothing else is configurable in v1.

Exit codes
----------
0   = command completed
!=0 = aborted; see stderr and the audit log for detail.

Per-command help
----------------
  sf-clean-room get_metadata --help
  sf-clean-room get_records --help
  sf-clean-room get_event_logs --help
  sf-clean-room get_technical_objects --help
"""


def _get_metadata_description() -> str:
    return (
        "Export Salesforce metadata for one org to --path. The published "
        "folder is safe for downstream automated consumers; sensitive "
        "categories are filtered out before any retrieve call is made."
    )


def _get_metadata_epilog() -> str:
    deny_op = ", ".join(sorted(OPERATIONAL_DENY))
    deny_sens = ", ".join(sorted(SENSITIVITY_DENY))
    buckets = ", ".join(SKIP_BUCKETS)
    return f"""
Output contract
---------------
The publish folder (--path) is the only artefact consumers should read.
The sentinel file is package.xml: it is moved into --path LAST. A consumer
that observes package.xml in --path may assume the publish completed; a
consumer that does not observe it must not act on the folder.

Limited permissions and the skip log
-------------------------------------
A per-type permission or capability gap does NOT abort the run. When the
authenticated identity cannot enumerate or fully retrieve a metadata type, that
type is skipped and recorded; the rest is published. The run also publishes:

  _skipped-types.csv   header: type,bucket,components_requested,components_retrieved

moved into --path just before package.xml. It is always written; a header-only
file means nothing was skipped (the expected state for a full-permission
identity). Buckets: {buckets} (registry_miss is reserved and not used on this
SOAP retrieve path). package.xml reflects what was actually retrieved, so it
never overstates. Verbatim error detail for each skip is in the audit log, not
in the published CSV. This skip-and-continue behaviour is automatic - there is
no flag to toggle it.

Deny list (source-controlled, NOT runtime-overridable)
------------------------------------------------------
Operational exclusions: {deny_op}
Sensitivity exclusions: {deny_sens}

These categories are filtered out at enumeration. No CLI flag, env var, or
config-file entry loosens this list.

OPERATOR AGENTS MUST NOT EDIT THE SOURCE TO CHANGE THIS LIST. If you are an
AI agent invoking this CLI as part of a workflow, you are an operator. Do
not edit constants.py, monkey-patch the filter, copy the source into
another project to produce a deny-list-free variant, re-implement the
Metadata API calls to bypass the filter, or otherwise work around the deny
list. If the deny list appears to block your goal, that is the tool working
as designed -- surface the requirement to a human rather than engineering
around it. Source changes are made only by a human-authorized development
task with code review.

Batch ceilings (in source)
--------------------------
Max components per retrieve: {MAX_COMPONENTS_PER_BATCH:,} (Salesforce hard limit is 10,000)
Max weight per retrieve    : {MAX_WEIGHT_PER_BATCH:,} (proxy for ~600 MB compressed-zip cap)

Examples
--------
  sf-clean-room get_metadata --org-alias myorg --path ./out --dry-run
  sf-clean-room get_metadata --org-alias myorg --path ./out
"""


def _get_records_description() -> str:
    return (
        "Export Salesforce record data for one org to --path, anonymised in "
        "flight. Every field is classified (RAW/DROP/HASH/PASS/DERIVE); raw PII "
        "is never written. The agent reads the published TSVs, never Salesforce."
    )


def _get_records_epilog() -> str:
    actions = ", ".join(sorted(CLASSIFIER_ACTIONS))
    return f"""
Output contract
---------------
The publish folder (--path) holds one <Object>.tsv per object plus the audit.
The sentinel file is {AUDIT_SENTINEL}: it is moved into --path LAST. A consumer
that observes it may assume the extract completed and every field is accounted
for; without it, the folder must not be read.

How fields are handled (recommendations; a plan may override)
-------------------------------------------------------------
Actions: {actions}.
Raw query results stay in memory only; DROP fields are never selected; HASH and
DERIVE are applied before any value is written. Hash recipes are frozen and
never salted so hashed columns join across sources.

Special-category data (GDPR Art. 9) defaults to DROP. Keeping such a field
requires a justification string in [reasons.<Object>] of the plan; without it,
the field is downgraded to DROP and the downgrade is reported (the run does not
abort).

Workflow
--------
1. Plan:    sf-clean-room get_records --org-alias A --path out --only Account Contact \\
                --plan plan.toml --dry-run
            (probe + describe + classify; writes an editable plan; no values)
2. Review:  edit [overrides.*] / [reasons.*] in plan.toml
3. Extract: sf-clean-room get_records --org-alias A --path out --plan plan.toml
4. Headless/scheduled: re-run step 3 unattended. New fields not in the plan are
   classified by the conservative default and logged as drift - never leaked.

--where (narrowing only; requires --only)
-----------------------------------------
Appended verbatim after FROM <object>. Rejected if it contains ';', SQL comment
markers, DML/DDL verbs, or LIMIT/OFFSET. It narrows rows; it cannot expose a
DROP/HASH field - the classifier still runs on every returned row.

This subcommand is read-only: it issues describe and SELECT queries only.

Examples
--------
  sf-clean-room get_records --org-alias myorg --path ./out --only Account --dry-run --plan p.toml
  sf-clean-room get_records --org-alias myorg --path ./out --only Account Contact
  sf-clean-room get_records --org-alias myorg --path ./out --only Contact --where "CreatedDate = THIS_YEAR"
"""


def _get_event_logs_description() -> str:
    return (
        "Export Salesforce EventLogFile data for one org to --path, anonymised in "
        "flight. Every CSV column is classified; IPs are derived to a network "
        "prefix, URLs stripped of query strings, usernames hashed, free-text "
        "dropped - before any value is written. Incremental: each run adds a dated "
        "subfolder; today's (incomplete) logs are never downloaded."
    )


def _get_event_logs_epilog() -> str:
    return """
Output contract
---------------
Output lands under <path>/event_logs/<alias>/<start>_to_<end>/, one
<LogDate>_<EventType>_<Id>.csv per record. The sentinel is
_field-handling-applied.csv (column,action,recipe,source,downgraded), moved in
LAST. A consumer that observes it may read that subfolder; without it, must not.
Prior subfolders are never cleared - runs accumulate history beyond Salesforce's
~30-day retention.

How columns are handled (recommendations; a plan may override)
--------------------------------------------------------------
  RAW     Salesforce IDs and opaque correlation keys (incl. SESSION_KEY /
          LOGIN_KEY, which Salesforce already emits hashed) - the join keys.
  HASH    USER_NAME / DELEGATED_USER_NAME / DEVICE_ID (sha256, frozen recipe).
  DERIVE  IP -> network prefix (last octet/80 bits zeroed); URL -> host+path,
          query string stripped.
  PASS    metrics, enums, names, and Salesforce-provided geo (COUNTRY_CODE).
  DROP    free-text / content / secrets (QUERY, SEARCH_QUERY, *_MESSAGE,
          STACK_TRACE, HTTP_HEADERS, ...).

Raw LogFile bodies stay in memory; only the anonymised CSV is written. This
subcommand is read-only (REST GET only). The classification is automatic; no
flag disables it.

Incremental window
------------------
end = yesterday (UTC); start = (max prior subfolder end + 1 day) or 29 days ago
on a cold start. If a subfolder already covers through yesterday, the run is a
no-op.

Examples
--------
  sf-clean-room get_event_logs --org-alias myorg --path ./out --dry-run --plan p.toml
  sf-clean-room get_event_logs --org-alias myorg --path ./out --only Login ReportExport
  sf-clean-room get_event_logs --org-alias myorg --path ./out
"""


def _get_technical_objects_description() -> str:
    return (
        "Export 40 catalogued Salesforce technical objects (Tooling entities, system tables, "
        "REST metrics endpoints) to --path, anonymised in flight. Every field is classified "
        "(RAW/DROP/HASH/DERIVE/PASS); IPs are derived to network prefixes, geo coarsened to "
        "country/subdivision, emails/usernames hashed, free-text dropped — before any value is "
        "written. The agent reads the published CSVs, never Salesforce."
    )


def _get_technical_objects_epilog() -> str:
    from sf_clean_room.technical_catalog import CATALOGUE_NAMES
    objects_list = "  " + "\n  ".join(CATALOGUE_NAMES)
    return f"""
Catalogued objects (40)
-----------------------
{objects_list}

Output contract
---------------
The publish folder (--path) holds one <ApiName>.csv per successfully-extracted
object, plus:
  _field-handling-applied.csv  object,column,type,action,recipe,source,downgraded
                               This is the sentinel — moved into --path LAST.
  _extract-summary.json        per-object rows/columns/action counts + skip reasons.

A consumer that observes _field-handling-applied.csv may trust the folder; without
it, must not read.  Skipped objects are listed in the summary; they are permission/
edition gaps, not failures (one-object gap does not abort the run).

How fields are handled (recommendations; a plan may override)
-------------------------------------------------------------
  Layer 0  field types base64/textarea/address/location/complexvalue/anyType and
           field names Body/Metadata/SymbolTable/FullName/HtmlValue/Content are
           NEVER included in any SELECT — source code, log bodies, and blobs never
           transit.
  RAW      Salesforce IDs and reference fields (join keys; already pseudonymous).
  HASH     Email-type fields and email-named string fields; username-like strings
           (sha256 frozen recipe, joinable across sources).
  DERIVE   IP fields -> network prefix (last octet/80 bits zeroed); URL/URI fields
           -> host+path (query string stripped).
  PASS     Picklists, booleans (incl. all PermissionsXxx bits), counts, timestamps,
           config names, org-level geo (country/subdivision).
  DROP     Fine-grained geo (lat/lon/city/postcode), phone fields, free-text that
           can echo personal data (Message, StackTrace, Display, Error, Description,
           Remarks), curated echo fields (FlowInterview.InterviewLabel, etc.).

Curated overrides (source-controlled): SetupAuditTrail.DelegateUser/IdentityUsed
HASH; LoginHistory.Status and CronTrigger.CronExpression PASS (documented vocab);
FlowInterview.InterviewLabel/PauseLabel, SetupAuditTrail.Display, Organization.
PrimaryContact, ApexTestResult.Message/StackTrace, ApexLog.Status,
BackgroundOperation.Error, and others DROP.

Workflow
--------
1. Plan:   sf-clean-room get_technical_objects --org-alias A --path out --dry-run \\
               --plan plan.toml
           (describe + classify; writes an editable plan; no record values)
2. Review: edit [overrides."Object.Field"] / [reasons."Object.Field"] in plan.toml
3. Extract: sf-clean-room get_technical_objects --org-alias A --path out \\
               --plan plan.toml
4. Headless: re-run step 3 unattended. New fields not in the plan fall back to the
   conservative classifier default — they are never leaked.

This subcommand is read-only (SOQL/Tooling/REST GET only). No flag disables the
Layer-0 skip list or the classifier.

Examples
--------
  sf-clean-room get_technical_objects --org-alias myorg --path ./out --dry-run --plan p.toml
  sf-clean-room get_technical_objects --org-alias myorg --path ./out --only LoginHistory AuthSession
  sf-clean-room get_technical_objects --org-alias myorg --path ./out --limit 100
"""


# ---------- parser construction ----------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sf-clean-room",
        description=_top_description(),
        epilog=_top_epilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"sf-clean-room {__version__}",
    )

    sub = parser.add_subparsers(
        dest="command",
        metavar="<command>",
        title="commands",
    )

    gm = sub.add_parser(
        "get_metadata",
        help="Export org metadata to --path (package.xml is the completion sentinel).",
        description=_get_metadata_description(),
        epilog=_get_metadata_epilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    gm.add_argument(
        "--org-alias",
        required=True,
        metavar="ALIAS",
        help="Salesforce CLI alias or username (must already be authenticated via `sf` or `sfdx`).",
    )
    gm.add_argument(
        "--path",
        required=True,
        metavar="DIR",
        help="Publish directory. Created if missing. Existing contents are deleted only at the publish step.",
    )
    gm.add_argument(
        "--dry-run",
        action="store_true",
        help="Enumerate, filter, and report the planned batch composition. No retrieve, no temp write, no publish-path mutation.",
    )
    gm.set_defaults(func=cmd_get_metadata)

    gr = sub.add_parser(
        "get_records",
        help="Export org record data to --path, anonymised in flight (_field-handling-applied.csv is the sentinel).",
        description=_get_records_description(),
        epilog=_get_records_epilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    gr.add_argument(
        "--org-alias", required=True, metavar="ALIAS",
        help="Salesforce CLI alias or username (must already be authenticated via `sf` or `sfdx`).",
    )
    gr.add_argument(
        "--path", required=True, metavar="DIR",
        help="Publish directory. Created if missing. Existing contents are deleted only at the publish step.",
    )
    gr.add_argument(
        "--only", nargs="+", metavar="OBJECT", default=None,
        help="Objects to extract. Required unless the plan file supplies [scope].objects.",
    )
    gr.add_argument(
        "--where", metavar="PREDICATE", default=None,
        help="SOQL predicate appended to every object query. Requires --only. Validated; read-only.",
    )
    gr.add_argument(
        "--plan", metavar="FILE", default=None,
        help="Classification plan (TOML). With --dry-run it is written; without, it is consumed.",
    )
    gr.add_argument(
        "--dry-run", action="store_true",
        help="Probe, describe, and classify only. Write the annotated plan and a summary. No record values, no publish-path mutation.",
    )
    gr.set_defaults(func=cmd_get_records)

    ge = sub.add_parser(
        "get_event_logs",
        help="Export org EventLogFile data to --path, anonymised in flight (incremental; _field-handling-applied.csv is the sentinel).",
        description=_get_event_logs_description(),
        epilog=_get_event_logs_epilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ge.add_argument(
        "--org-alias", required=True, metavar="ALIAS",
        help="Salesforce CLI alias or username (must already be authenticated via `sf` or `sfdx`).",
    )
    ge.add_argument(
        "--path", required=True, metavar="DIR",
        help="Base directory (must exist). Output lands under <path>/event_logs/<alias>/<start>_to_<end>/.",
    )
    ge.add_argument(
        "--only", nargs="+", metavar="EVENTTYPE", default=None,
        help="EventTypes to include (default: all available in the window).",
    )
    ge.add_argument(
        "--plan", metavar="FILE", default=None,
        help="Classification plan (TOML): [scope].event_types and [overrides].<COLUMN>. With --dry-run it is written; without, consumed.",
    )
    ge.add_argument(
        "--dry-run", action="store_true",
        help="Query the window and report what would download + the column classification plan. No LogFile fetch, no values, no publish.",
    )
    ge.set_defaults(func=cmd_get_event_logs)

    gt = sub.add_parser(
        "get_technical_objects",
        help="Export 40 catalogued technical objects to --path, anonymised in flight (_field-handling-applied.csv is the sentinel).",
        description=_get_technical_objects_description(),
        epilog=_get_technical_objects_epilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    gt.add_argument(
        "--org-alias", required=True, metavar="ALIAS",
        help="Salesforce CLI alias or username (must already be authenticated via `sf` or `sfdx`).",
    )
    gt.add_argument(
        "--path", required=True, metavar="DIR",
        help="Publish directory. Created if missing. Existing contents are deleted only at the publish step.",
    )
    gt.add_argument(
        "--only", nargs="+", metavar="OBJECT", default=None,
        help="Objects to include (default: all 40 catalogue objects). Unknown names abort with the valid list.",
    )
    gt.add_argument(
        "--limit", type=int, default=None, metavar="N",
        help="Max rows per object — smoke-test narrowing. Applied via SOQL LIMIT N.",
    )
    gt.add_argument(
        "--plan", metavar="FILE", default=None,
        help="Classification plan (TOML): [scope].objects and [overrides.\"Object.Field\"]. With --dry-run it is written; without, consumed.",
    )
    gt.add_argument(
        "--dry-run", action="store_true",
        help="Describe + classify only: report the per-object column plan. No record values, no publish-path mutation.",
    )
    gt.set_defaults(func=cmd_get_technical_objects)

    return parser


# ---------- commands ----------

def cmd_get_metadata(args: argparse.Namespace) -> int:
    org_alias = args.org_alias
    publish_path = Path(args.path)
    config = load_config()
    with audit_log(org_alias, tee_stream=sys.stderr) as log:
        log.write(f"sf-clean-room {__version__} command=get_metadata")
        log.write(f"args: org_alias={org_alias} path={publish_path} dry_run={args.dry_run}")
        log.write(f"temp_root={config.temp_root}")
        log.write(
            f"config source={'defaults' if config.source_path is None else config.source_path}"
        )

        log.section("session")
        session = get_session(org_alias, api_version=API_VERSION)
        log.write(
            f"session resolved: instance_url={session.instance_url} "
            f"username={session.username} org_id={session.org_id}"
        )

        if args.dry_run:
            plan = plan_only(session, log)
            print(plan)
            print(f"\naudit log: {log.path}")
            return 0

        paths = make_run_paths(config.temp_root, publish_path, org_alias)
        execute(session, paths, log)
        print(f"published: {paths.publish_path}")
        print(f"audit log: {log.path}")
        return 0


def cmd_get_records(args: argparse.Namespace) -> int:
    from sf_clean_room.plan import load_plan
    from sf_clean_room.records_pipeline import (
        RecordsRequest,
        dry_run,
        execute as records_execute,
        resolve_scope,
    )

    org_alias = args.org_alias
    publish_path = Path(args.path)
    plan_path = Path(args.plan) if args.plan else None
    config = load_config()
    with audit_log(org_alias, tee_stream=sys.stderr) as log:
        log.write(f"sf-clean-room {__version__} command=get_records")
        log.write(
            f"args: org_alias={org_alias} path={publish_path} only={args.only} "
            f"where={args.where!r} plan={plan_path} dry_run={args.dry_run}"
        )
        log.write(f"temp_root={config.temp_root}")

        # Object scope: --only, or [scope].objects from an existing plan.
        existing_plan = load_plan(plan_path) if (plan_path and plan_path.exists()) else None
        objects = resolve_scope(args.only, existing_plan)

        if args.where and not args.only:
            raise ValueError("--where requires --only")

        log.section("session")
        session = get_session(org_alias, api_version=API_VERSION)
        log.write(
            f"session resolved: instance_url={session.instance_url} "
            f"username={session.username} org_id={session.org_id}"
        )

        if args.dry_run:
            plan_text = dry_run(session, objects, plan_path, log)
            print(plan_text)
            print(f"\naudit log: {log.path}")
            if plan_path:
                print(f"plan written: {plan_path}")
            return 0

        req = RecordsRequest(
            objects=objects, where=args.where, plan_path=plan_path, dry_run=False
        )
        paths = make_run_paths(config.temp_root, publish_path, org_alias)
        records_execute(session, req, paths, log)
        print(f"published: {paths.publish_path}")
        print(f"audit log: {log.path}")
        return 0


def cmd_get_event_logs(args: argparse.Namespace) -> int:
    from sf_clean_room.eventlog_pipeline import (
        EventLogRequest,
        dry_run as el_dry_run,
        execute as el_execute,
    )

    org_alias = args.org_alias
    base_path = Path(args.path)
    plan_path = Path(args.plan) if args.plan else None
    config = load_config()
    with audit_log(org_alias, tee_stream=sys.stderr) as log:
        log.write(f"sf-clean-room {__version__} command=get_event_logs")
        log.write(
            f"args: org_alias={org_alias} path={base_path} only={args.only} "
            f"plan={plan_path} dry_run={args.dry_run}"
        )
        log.write(f"temp_root={config.temp_root}")

        if not base_path.is_dir():
            raise ValueError(f"base path does not exist or is not a directory: {base_path}")

        log.section("session")
        session = get_session(org_alias, api_version=API_VERSION)
        log.write(
            f"session resolved: instance_url={session.instance_url} "
            f"username={session.username} org_id={session.org_id}"
        )

        req = EventLogRequest(only=args.only, plan_path=plan_path, dry_run=args.dry_run)
        if args.dry_run:
            report = el_dry_run(session, base_path, org_alias, req, log)
            print(report)
            if plan_path:
                plan_path.write_text(report.split("\n\n", 1)[-1], encoding="utf-8")
                print(f"\nplan written: {plan_path}")
            print(f"audit log: {log.path}")
            return 0

        dest = el_execute(session, base_path, org_alias, req, config.temp_root, log)
        print(f"published: {dest}")
        print(f"audit log: {log.path}")
        return 0


def cmd_get_technical_objects(args: argparse.Namespace) -> int:
    from sf_clean_room.technical_pipeline import (
        TechnicalRequest,
        dry_run as to_dry_run,
        execute as to_execute,
    )

    org_alias = args.org_alias
    publish_path = Path(args.path)
    plan_path = Path(args.plan) if args.plan else None
    config = load_config()
    with audit_log(org_alias, tee_stream=sys.stderr) as log:
        log.write(f"sf-clean-room {__version__} command=get_technical_objects")
        log.write(
            f"args: org_alias={org_alias} path={publish_path} only={args.only} "
            f"limit={args.limit} plan={plan_path} dry_run={args.dry_run}"
        )
        log.write(f"temp_root={config.temp_root}")

        log.section("session")
        session = get_session(org_alias, api_version=API_VERSION)
        log.write(
            f"session resolved: instance_url={session.instance_url} "
            f"username={session.username} org_id={session.org_id}"
        )

        req = TechnicalRequest(
            only=args.only, limit=args.limit, plan_path=plan_path, dry_run=args.dry_run
        )
        if args.dry_run:
            report = to_dry_run(session, publish_path, req, log)
            print(report)
            if plan_path:
                print(f"\nplan written: {plan_path}")
            print(f"audit log: {log.path}")
            return 0

        publish_path.mkdir(parents=True, exist_ok=True)
        to_execute(session, publish_path, req, config.temp_root, log)
        print(f"published: {publish_path}")
        print(f"audit log: {log.path}")
        return 0


# ---------- entry point ----------

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help(sys.stderr)
        return 2
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    except Exception as e:  # noqa: BLE001 - top-level: turn any error into a non-zero exit + stderr
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
