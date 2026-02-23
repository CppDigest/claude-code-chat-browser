#!/usr/bin/env python3
"""CLI tool to export Claude Code chat history to Markdown files.

Usage:
    python scripts/export.py                     # export all sessions as zip
    python scripts/export.py --since last        # incremental export
    python scripts/export.py --out ./exports     # custom output directory
    python scripts/export.py --no-zip            # individual MD files, no zip
    python scripts/export.py --project myproject # export specific project only
"""

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
from utils.md_exporter import session_to_markdown


STATE_DIR = os.path.join(os.path.expanduser("~"), ".claude-code-chat-browser")
STATE_FILE = os.path.join(STATE_DIR, "export_state.json")


def main():
    args = parse_args(sys.argv[1:])

    base_dir = args.get("base_dir") or get_claude_projects_dir()
    out_dir = args.get("out") or os.getcwd()
    since = args.get("since", "all")
    no_zip = args.get("no_zip", False)
    project_filter = args.get("project")

    if not os.path.isdir(base_dir):
        print(f"Error: Claude Code projects directory not found: {base_dir}")
        print("Make sure Claude Code has been used on this machine.")
        sys.exit(1)

    last_export = _load_state() if since == "last" else {}

    projects = list_projects(base_dir)
    if project_filter:
        projects = [p for p in projects if project_filter in p["name"]]

    if not projects:
        print("No projects found.")
        sys.exit(0)

    print(f"Found {len(projects)} project(s) in {base_dir}")

    all_exports = []
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

            md = session_to_markdown(session)
            meta = session["metadata"]
            ts = meta.get("first_timestamp", "")
            if not ts:
                # Fallback: use file modification time
                from datetime import datetime as _dt
                ts = _dt.fromtimestamp(sess_info["modified"]).strftime("%Y-%m-%dT%H:%M:%S")
                meta["first_timestamp"] = ts
            date_str = ts[:10]
            title_slug = _slugify(session["title"])[:60]
            short_id = sid[:8]
            project_slug = _slugify(project["name"])

            rel_path = os.path.join(
                date_str, project_slug, f"{title_slug}__{short_id}.md"
            )

            all_exports.append((rel_path, md))
            manifest.append({
                "session_id": sid,
                "path": rel_path,
                "title": session["title"],
                "project": project["name"],
                "updated_at": meta.get("last_timestamp", ""),
                "models": meta.get("models_used", []),
                "tokens": meta["total_input_tokens"] + meta["total_output_tokens"],
                "tool_calls": meta["total_tool_calls"],
            })

            last_export[sid] = sess_info["modified"]

    exported = len(all_exports)
    print(f"Exporting {exported} session(s) ({skipped} skipped, {total_sessions} total)")

    if not all_exports:
        print("Nothing to export.")
        return

    os.makedirs(out_dir, exist_ok=True)

    if no_zip:
        for rel_path, md in all_exports:
            full_path = os.path.join(out_dir, rel_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(md)
        manifest_path = os.path.join(out_dir, "manifest.jsonl")
        with open(manifest_path, "w", encoding="utf-8") as f:
            for entry in manifest:
                f.write(json.dumps(entry) + "\n")
        print(f"Exported {exported} file(s) to {out_dir}")
    else:
        date_tag = datetime.now().strftime("%Y-%m-%d")
        zip_name = f"claude-code-export-{date_tag}.zip"
        zip_path = os.path.join(out_dir, zip_name)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for rel_path, md in all_exports:
                zf.writestr(rel_path, md)
            manifest_str = "\n".join(json.dumps(e) for e in manifest)
            zf.writestr("manifest.jsonl", manifest_str)
        print(f"Exported {exported} session(s) to {zip_path}")

    _save_state(last_export)
    print("Export state saved.")


def parse_args(argv: list) -> dict:
    args = {}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--since" and i + 1 < len(argv):
            args["since"] = argv[i + 1]
            i += 2
        elif arg == "--out" and i + 1 < len(argv):
            args["out"] = argv[i + 1]
            i += 2
        elif arg == "--project" and i + 1 < len(argv):
            args["project"] = argv[i + 1]
            i += 2
        elif arg == "--base-dir" and i + 1 < len(argv):
            args["base_dir"] = argv[i + 1]
            i += 2
        elif arg == "--no-zip":
            args["no_zip"] = True
            i += 1
        elif arg in ("--help", "-h"):
            print(__doc__)
            sys.exit(0)
        else:
            print(f"Unknown argument: {arg}")
            print(__doc__)
            sys.exit(1)
    return args


def _load_state() -> dict:
    if os.path.isfile(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}


def _save_state(state: dict):
    os.makedirs(STATE_DIR, exist_ok=True)
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


if __name__ == "__main__":
    main()
