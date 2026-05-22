"""CLI entry point.

Invocation shape::

    sf-clean-room <command> [<command-flags>...]

v1 ships one command:

* ``get_metadata`` — export Salesforce metadata to a folder safe for downstream
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
    MAX_COMPONENTS_PER_BATCH,
    MAX_WEIGHT_PER_BATCH,
    OPERATIONAL_DENY,
    SENSITIVITY_DENY,
)
from sf_clean_room.paths import default_config_path, default_log_dir
from sf_clean_room.pipeline import execute, make_run_paths, plan_only
from sf_clean_room.session import get_session


# ---------- help-text builders (read from constants at call time) ----------

def _top_description() -> str:
    return (
        "Export Salesforce metadata (and, in future versions, records) to a "
        "folder that is safe for downstream automated consumers — other AI "
        "agents, code analysers, CI. Sensitive metadata categories are "
        "filtered out at enumeration time and never transit the network."
    )


def _top_epilog() -> str:
    return f"""
Commands
--------
  get_metadata    Export org metadata to --path with package.xml as the sentinel.

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
    return f"""
Output contract
---------------
The publish folder (--path) is the only artefact consumers should read.
The sentinel file is package.xml: it is moved into --path LAST. A consumer
that observes package.xml in --path may assume the publish completed; a
consumer that does not observe it must not act on the folder.

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
    except Exception as e:  # noqa: BLE001 — top-level: turn any error into a non-zero exit + stderr
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
