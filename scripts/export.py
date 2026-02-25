#!/usr/bin/env python3
"""CLI for exporting Claude Code chat history.

Examples:
    export.py                          # zip of all sessions as markdown
    export.py list                     # show projects
    export.py list --project foo       # show sessions in a project
    export.py stats                    # token/cost totals
    export.py stats --session UUID     # single session breakdown
    export.py --format json --no-zip   # JSON files instead of zip
    export.py --since last             # only sessions changed since last run
"""

import argparse
import json
import os
import sys
import zipfile
from datetime import datetime

# Allow running from repo root or scripts/ directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, REPO_ROOT)

from utils.session_path import get_claude_projects_dir, list_projects, list_sessions
from utils.jsonl_parser import parse_session
from utils.session_stats import compute_stats, _format_duration
from utils.md_exporter import session_to_markdown
from utils.json_exporter import session_to_json
from utils.exclusion_rules import (
    resolve_exclusion_rules_path,
    load_rules,
    build_searchable_text,
    is_excluded_by_rules,
)


STATE_DIR = os.path.join(os.path.expanduser("~"), ".claude-code-chat-browser")
STATE_FILE = os.path.join(STATE_DIR, "export_state.json")


def main():
    parser = build_parser()
    args = parser.parse_args()

    command = getattr(args, "command", None) or "export"

    if command == "list":
        cmd_list(args)
    elif command == "stats":
        cmd_stats(args)
    else:
        cmd_export(args)

def cmd_list(args):
    """Print a table of projects, or drill into one project's sessions."""
    base_dir = getattr(args, "base_dir", None) or get_claude_projects_dir()
    project_filter = getattr(args, "project", None)

    if not os.path.isdir(base_dir):
        _die(f"Claude Code projects directory not found: {base_dir}")

    projects = list_projects(base_dir)
    if project_filter:
        projects = [p for p in projects if project_filter in p["name"]]

    if not projects:
        print("No projects found.")
        return

    # If a specific project is selected, list its sessions
    if project_filter and len(projects) == 1:
        _list_sessions(projects[0])
        return

    # Otherwise list all projects
    print(f"Projects ({len(projects)} found):\n")
    print(f"  {'Project':<45} {'Sessions':>8}   {'Last Modified'}")
    print(f"  {chr(9472) * 45} {chr(9472) * 8}   {chr(9472) * 19}")
    for p in sorted(projects, key=lambda x: x.get("last_modified", ""), reverse=True):
        name = p.get("display_name") or p["name"]
        count = p.get("session_count", 0)
        modified = p.get("last_modified", "")[:19].replace("T", " ")
        print(f"  {name:<45} {count:>8}   {modified}")


def _list_sessions(project: dict):
    """Print each session in a project with title, tokens, tool count."""
    sessions = list_sessions(project["path"])
    name = project.get("display_name") or project["name"]
    print(f"Sessions in {name} ({len(sessions)} found):\n")
    print(f"  {'Date':<12} {'Title':<50} {'ID':>10} {'Tokens':>10} {'Tools':>6}")
    print(f"  {chr(9472) * 12} {chr(9472) * 50} {chr(9472) * 10} {chr(9472) * 10} {chr(9472) * 6}")

    for s in sorted(sessions, key=lambda x: x.get("modified", 0), reverse=True):
        try:
            parsed = parse_session(s["path"])
            if parsed["title"] == "Untitled Session":
                continue
            meta = parsed["metadata"]
            ts = (meta.get("first_timestamp") or "")[:10]
            title = parsed["title"][:50]
            sid = s["id"][:10]
            tokens = meta["total_input_tokens"] + meta["total_output_tokens"]
            tools = meta["total_tool_calls"]
            print(f"  {ts:<12} {title:<50} {sid:>10} {tokens:>10,} {tools:>6}")
        except Exception as e:
            print(f"  Warning: failed to parse {s['id'][:10]}: {e}", file=sys.stderr)
            continue


def cmd_stats(args):
    """Show stats -- either for one session or aggregated across all."""
    base_dir = getattr(args, "base_dir", None) or get_claude_projects_dir()
    project_filter = getattr(args, "project", None)
    session_id = getattr(args, "session", None)
    fmt = getattr(args, "format", "text") or "text"

    if not os.path.isdir(base_dir):
        _die(f"Claude Code projects directory not found: {base_dir}")

    if session_id:
        _session_stats(session_id, base_dir, fmt)
    else:
        _aggregate_stats(base_dir, project_filter, fmt)


def _session_stats(session_id: str, base_dir: str, fmt: str):
    """Detailed breakdown for one session: tokens, files, commands, cost."""
    filepath = _find_session(session_id, base_dir)
    if not filepath:
        _die(f"Session not found: {session_id}")

    session = parse_session(filepath)
    stats = compute_stats(session)

    if fmt == "json":
        print(json.dumps(stats, indent=2, default=str))
        return

    meta = session["metadata"]
    print(f"=== Session: {session_id[:12]} ===\n")
    print(f"  Title:      {session['title']}")
    if meta["first_timestamp"]:
        print(f"  Created:    {meta['first_timestamp'][:19]}")
    dur = _format_duration(meta.get("session_wall_time_seconds"))
    if dur:
        print(f"  Duration:   {dur}")
    print(f"  Models:     {', '.join(meta['models_used']) or 'unknown'}")
    inp = meta["total_input_tokens"]
    out = meta["total_output_tokens"]
    print(f"  Tokens:     {inp + out:,} (input: {inp:,} / output: {out:,})")
    cache_r = meta["total_cache_read_tokens"]
    cache_c = meta["total_cache_creation_tokens"]
    if cache_r or cache_c:
        print(f"  Cache:      read: {cache_r:,} / creation: {cache_c:,}")
    print(f"  Tool calls: {meta['total_tool_calls']}")
    if meta["tool_call_counts"]:
        breakdown = ", ".join(
            f"{t}: {c}" for t, c in sorted(
                meta["tool_call_counts"].items(), key=lambda x: -x[1]
            )
        )
        print(f"              {breakdown}")
    if meta.get("stop_reasons"):
        sr = ", ".join(f"{r}: {c}" for r, c in meta["stop_reasons"].items())
        print(f"  Stop:       {sr}")

    ft = stats.get("files_touched", {})
    total_files = ft.get("total_unique", 0)
    if total_files:
        print(
            f"  Files:      {total_files} unique "
            f"({len(ft.get('read', []))} read, "
            f"{len(ft.get('written', []))} edited, "
            f"{len(ft.get('created', []))} created)"
        )
    cmds = stats.get("commands_run", [])
    if cmds:
        trs = stats.get("tool_result_summary", {})
        ok = trs.get("bash_success", 0)
        err = trs.get("bash_error", 0)
        print(f"  Commands:   {len(cmds)} run ({ok} success, {err} error)")
    if meta.get("compactions"):
        print(f"  Compactions: {meta['compactions']}")
    if meta.get("api_errors"):
        print(f"  API errors: {meta['api_errors']}")
    cost = stats.get("cost_estimate_usd")
    if cost is not None:
        print(f"  Est. cost:  ~${cost:.2f} USD")


def _aggregate_stats(base_dir: str, project_filter: str, fmt: str):
    """Sum up tokens, tools, cost across every session. Optionally filter
    by project."""
    projects = list_projects(base_dir)
    if project_filter:
        projects = [p for p in projects if project_filter in p["name"]]

    totals = {
        "projects": len(projects),
        "sessions": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
        "tool_calls": 0,
        "tool_counts": {},
        "models": set(),
        "files_unique": set(),
        "commands_run": 0,
        "compactions": 0,
        "api_errors": 0,
        "total_cost": 0.0,
        "has_cost": False,
    }

    for project in projects:
        sessions = list_sessions(project["path"])
        for s in sessions:
            try:
                session = parse_session(s["path"])
                if session["title"] == "Untitled Session":
                    continue
                meta = session["metadata"]
                stats = compute_stats(session)

                totals["sessions"] += 1
                totals["input_tokens"] += meta["total_input_tokens"]
                totals["output_tokens"] += meta["total_output_tokens"]
                totals["cache_read_tokens"] += meta["total_cache_read_tokens"]
                totals["cache_creation_tokens"] += meta["total_cache_creation_tokens"]
                totals["tool_calls"] += meta["total_tool_calls"]
                for t, c in meta["tool_call_counts"].items():
                    totals["tool_counts"][t] = totals["tool_counts"].get(t, 0) + c
                totals["models"].update(meta["models_used"])
                ft = stats.get("files_touched", {})
                for category in ("read", "written", "created"):
                    totals["files_unique"].update(ft.get(category, []))
                totals["commands_run"] += len(stats.get("commands_run", []))
                totals["compactions"] += meta.get("compactions", 0)
                totals["api_errors"] += meta.get("api_errors", 0)
                cost = stats.get("cost_estimate_usd")
                if cost is not None:
                    totals["total_cost"] += cost
                    totals["has_cost"] = True
            except Exception as e:
                print(f"  Warning: failed to parse {s['id'][:10]} in {project['name']}: {e}", file=sys.stderr)
                continue

    if fmt == "json":
        out = dict(totals)
        out["models"] = sorted(out["models"])
        out["files_unique"] = len(out["files_unique"])
        print(json.dumps(out, indent=2, default=str))
        return

    total_tokens = totals["input_tokens"] + totals["output_tokens"]
    print("=== Aggregate Stats ===\n")
    print(f"  Projects:     {totals['projects']}")
    print(f"  Sessions:     {totals['sessions']}")
    print(f"  Models:       {', '.join(sorted(totals['models'])) or 'none'}")
    print(f"  Total tokens: {total_tokens:,} (input: {totals['input_tokens']:,} / output: {totals['output_tokens']:,})")
    if totals["cache_read_tokens"]:
        print(f"  Cache:        read: {totals['cache_read_tokens']:,} / creation: {totals['cache_creation_tokens']:,}")
    print(f"  Tool calls:   {totals['tool_calls']:,}")
    if totals["tool_counts"]:
        breakdown = ", ".join(
            f"{t}: {c}" for t, c in sorted(
                totals["tool_counts"].items(), key=lambda x: -x[1]
            )[:10]
        )
        print(f"                {breakdown}")
    print(f"  Files:        {len(totals['files_unique']):,} unique")
    print(f"  Commands:     {totals['commands_run']:,}")
    if totals["compactions"]:
        print(f"  Compactions:  {totals['compactions']}")
    if totals["api_errors"]:
        print(f"  API errors:   {totals['api_errors']}")
    if totals["has_cost"]:
        print(f"  Est. cost:    ~${totals['total_cost']:.2f} USD")


def cmd_export(args):
    """The main export command. Writes md/json files, optionally zipped."""
    base_dir = getattr(args, "base_dir", None) or get_claude_projects_dir()
    out_dir = getattr(args, "out", None) or os.getcwd()
    since = getattr(args, "since", None) or "all"
    no_zip = getattr(args, "no_zip", False)
    project_filter = getattr(args, "project", None)
    fmt = getattr(args, "format", None) or "md"
    session_filter = getattr(args, "session", None)
    exclusion_rules_path = getattr(args, "exclude_rules", None)

    if not os.path.isdir(base_dir):
        _die(f"Claude Code projects directory not found: {base_dir}")

    rules = load_rules(resolve_exclusion_rules_path(exclusion_rules_path))

    state = _load_state() if since == "last" else {}
    last_export = state.get("sessions", {})

    # Single session export
    if session_filter:
        filepath = _find_session(session_filter, base_dir)
        if not filepath:
            _die(f"Session not found: {session_filter}")
        session = parse_session(filepath)
        stats = compute_stats(session)
        _export_single(session, stats, fmt, out_dir)
        return

    projects = list_projects(base_dir)
    if project_filter:
        projects = [p for p in projects if project_filter in p["name"]]

    if not projects:
        print("No projects found.")
        return

    print(f"Found {len(projects)} project(s) in {base_dir}")

    all_exports = []  # list of (rel_path, content)
    manifest = []
    total_sessions = 0
    skipped = 0

    for project in projects:
        sessions = list_sessions(project["path"])
        for sess_info in sessions:
            total_sessions += 1
            sid = sess_info["id"]

            if since == "last":
                prev_mtime = last_export.get(sid, 0)
                if sess_info["modified"] <= prev_mtime:
                    skipped += 1
                    continue

            try:
                session = parse_session(sess_info["path"])
            except Exception as e:
                print(f"  Warning: failed to parse {sid}: {e}")
                continue

            if session["title"] == "Untitled Session":
                skipped += 1
                continue

            if rules:
                meta = session["metadata"]
                searchable = build_searchable_text(
                    project_name=project.get("display_name") or project["name"],
                    session_title=session["title"],
                    model_names=list(meta.get("models_used") or []),
                    content_snippet=_session_text_for_exclusion(session),
                )
                if is_excluded_by_rules(rules, searchable):
                    skipped += 1
                    continue

            stats = compute_stats(session)
            meta = session["metadata"]
            ts = meta.get("first_timestamp", "")
            if not ts:
                from datetime import datetime as _dt
                ts = _dt.fromtimestamp(sess_info["modified"]).strftime(
                    "%Y-%m-%dT%H:%M:%S"
                )
                meta["first_timestamp"] = ts
            date_str = ts[:10]
            ts_file = ts[:19].replace(":", "-")   # 2026-02-10T01-46-15
            title_slug = _slugify(session["title"])
            short_id = sid[:8]
            project_slug = _slugify(project["name"])

            if fmt in ("md", "both"):
                md = session_to_markdown(session, stats)
                rel_path = os.path.join(
                    date_str, project_slug, f"{ts_file}__{title_slug}__{short_id}.md"
                )
                all_exports.append((rel_path, md))

            if fmt in ("json", "both"):
                js = session_to_json(session, stats)
                rel_path = os.path.join(
                    date_str, project_slug, f"{ts_file}__{title_slug}__{short_id}.json"
                )
                all_exports.append((rel_path, js))

            manifest.append({
                "session_id": sid,
                "title": session["title"],
                "project": project["name"],
                "updated_at": meta.get("last_timestamp", ""),
                "models": meta.get("models_used", []),
                "tokens": meta["total_input_tokens"] + meta["total_output_tokens"],
                "tool_calls": meta["total_tool_calls"],
                "files_touched": stats.get("files_touched", {}).get(
                    "total_unique", 0
                ),
                "commands_run": len(stats.get("commands_run", [])),
                "cost_estimate_usd": stats.get("cost_estimate_usd"),
                "wall_clock_seconds": meta.get("session_wall_time_seconds"),
            })

            last_export[sid] = sess_info["modified"]

    exported = len(all_exports)
    print(
        f"Exporting {exported} file(s) "
        f"({skipped} skipped, {total_sessions} total)"
    )

    if not all_exports:
        print("Nothing to export.")
        return

    os.makedirs(out_dir, exist_ok=True)

    if no_zip:
        for rel_path, content in all_exports:
            full_path = os.path.join(out_dir, rel_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
        manifest_path = os.path.join(out_dir, "manifest.jsonl")
        with open(manifest_path, "w", encoding="utf-8") as f:
            for entry in manifest:
                f.write(json.dumps(entry, default=str) + "\n")
        print(f"Exported {exported} file(s) to {out_dir}")
    else:
        date_tag = datetime.now().strftime("%Y-%m-%d")
        zip_name = f"claude-code-export-{date_tag}.zip"
        zip_path = os.path.join(out_dir, zip_name)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for rel_path, content in all_exports:
                zf.writestr(rel_path, content)
            manifest_str = "\n".join(
                json.dumps(e, default=str) for e in manifest
            )
            zf.writestr("manifest.jsonl", manifest_str)
        print(f"Exported {exported} file(s) to {zip_path}")

    _save_state(last_export, count=len(manifest), out_dir=out_dir)
    print(f"State saved to {STATE_FILE}")


def _export_single(session: dict, stats: dict, fmt: str, out_dir: str):
    """Write one session to disk as md, json, or both."""
    title_slug = _slugify(session["title"])
    short_id = session["session_id"][:8]
    ts = session["metadata"].get("first_timestamp", "")
    ts_file = ts[:19].replace(":", "-") if ts else "0000-00-00T00-00-00"

    files = []
    if fmt in ("md", "both"):
        md = session_to_markdown(session, stats)
        files.append((f"{ts_file}__{title_slug}__{short_id}.md", md))
    if fmt in ("json", "both"):
        js = session_to_json(session, stats)
        files.append((f"{ts_file}__{title_slug}__{short_id}.json", js))

    os.makedirs(out_dir, exist_ok=True)
    for fname, content in files:
        fpath = os.path.join(out_dir, fname)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Exported: {fpath}")


# ==================== Helpers ====================


def _session_text_for_exclusion(session: dict) -> str:
    """Extract plain text from all session messages for exclusion rule matching."""
    parts = []
    for msg in session.get("messages", []):
        text = msg.get("text") or ""
        if isinstance(text, str) and text.strip():
            parts.append(text)
    return "\n\n".join(parts)


# ==================== Argument Parser ====================


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export Claude Code chat history to Markdown/JSON",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    # Global options (for backward compatibility when no subcommand)
    parser.add_argument("--base-dir", default=None,
                        help="Override Claude Code projects directory")
    parser.add_argument("--project", default=None,
                        help="Filter by project name (substring match)")
    parser.add_argument("--since", choices=["all", "last"], default=None,
                        help="Export all or only new since last run")
    parser.add_argument("--out", default=None,
                        help="Output directory (default: current dir)")
    parser.add_argument("--no-zip", action="store_true", default=False,
                        help="Write individual files instead of zip")
    parser.add_argument("--format", choices=["md", "json", "both"],
                        default=None, help="Export format (default: md)")
    parser.add_argument("--session", default=None,
                        help="Export/stats for single session (UUID prefix)")
    parser.add_argument(
        "--exclude-rules", "-e",
        default=None,
        metavar="PATH",
        dest="exclude_rules",
        help="Path to exclusion rules file (sensitive sessions are omitted). "
             "If omitted, uses ~/.claude-code-chat-browser/exclusion-rules.txt if present.",
    )

    subparsers = parser.add_subparsers(dest="command")

    # List subcommand
    list_p = subparsers.add_parser("list", help="List projects and sessions")
    list_p.add_argument("--project", default=None,
                        help="Filter/select project")
    list_p.add_argument("--base-dir", default=None,
                        help="Override Claude Code projects directory")

    # Stats subcommand
    stats_p = subparsers.add_parser("stats", help="Show statistics")
    stats_p.add_argument("--session", default=None,
                         help="Stats for specific session (UUID prefix)")
    stats_p.add_argument("--format", choices=["text", "json"], default="text",
                         help="Output format (default: text)")
    stats_p.add_argument("--project", default=None,
                         help="Filter by project name")
    stats_p.add_argument("--base-dir", default=None,
                         help="Override Claude Code projects directory")

    # Export subcommand (explicit)
    export_p = subparsers.add_parser("export", help="Export sessions")
    export_p.add_argument("--since", choices=["all", "last"], default="all",
                          help="Export all or only new since last run")
    export_p.add_argument("--out", default=None,
                          help="Output directory (default: current dir)")
    export_p.add_argument("--no-zip", action="store_true",
                          help="Write individual files instead of zip")
    export_p.add_argument("--format", choices=["md", "json", "both"],
                          default="md", help="Export format (default: md)")
    export_p.add_argument("--session", default=None,
                          help="Export single session by UUID prefix")
    export_p.add_argument("--project", default=None,
                          help="Filter by project name")
    export_p.add_argument("--base-dir", default=None,
                          help="Override Claude Code projects directory")
    export_p.add_argument(
        "--exclude-rules", "-e",
        default=None,
        metavar="PATH",
        dest="exclude_rules",
        help="Path to exclusion rules file (sensitive sessions are omitted). "
             "If omitted, uses ~/.claude-code-chat-browser/exclusion-rules.txt if present.",
    )

    return parser


def _find_session(session_id: str, base_dir: str) -> str | None:
    """Scan all projects for a session matching this UUID (or prefix).
    Fails if the prefix matches more than one session."""
    matches = []
    for project in list_projects(base_dir):
        for s in list_sessions(project["path"]):
            if s["id"] == session_id:
                return s["path"]
            if s["id"].startswith(session_id):
                matches.append(s)
    if len(matches) == 1:
        return matches[0]["path"]
    if len(matches) > 1:
        _die(
            f"Ambiguous prefix '{session_id}' matches {len(matches)} sessions:\n"
            + "\n".join(f"  {m['id']}" for m in matches)
        )
    return None


def _load_state() -> dict:
    """Load export state, migrating legacy flat format to the current schema.

    Current schema::

        {
            "lastExportTime": "2026-02-25T12:00:00",
            "exportedCount": 42,
            "exportDir": "/path/to/out",
            "sessions": {"<session-uuid>": <mtime-float>, ...}
        }

    Legacy schema (written by older versions)::

        {"<session-uuid>": <mtime-float>, ...}
    """
    if not os.path.isfile(STATE_FILE):
        return {}
    with open(STATE_FILE, "r") as f:
        data = json.load(f)
    # Migrate: if the file has neither "sessions" nor "lastExportTime" it is
    # the old flat dict of session_id → mtime.
    if "sessions" not in data and "lastExportTime" not in data:
        return {"sessions": data}
    return data


def _save_state(sessions: dict, count: int, out_dir: str):
    """Persist export state with standardised fields matching cursor-chat-browser."""
    os.makedirs(STATE_DIR, exist_ok=True)
    state = {
        "lastExportTime": datetime.now().isoformat(),
        "exportedCount": count,
        "exportDir": out_dir,
        "sessions": sessions,
    }
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _slugify(text: str) -> str:
    slug = ""
    for c in text.lower():
        if c.isalnum():
            slug += c
        elif c in " -_/.":
            slug += "-"
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def _die(msg: str):
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
