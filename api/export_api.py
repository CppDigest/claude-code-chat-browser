"""API endpoint for bulk export."""

import io
import zipfile
from datetime import datetime

from flask import Blueprint, current_app, jsonify, send_file

from utils.session_path import get_claude_projects_dir, list_projects, list_sessions
from utils.jsonl_parser import parse_session
from utils.md_exporter import session_to_markdown

export_bp = Blueprint("export", __name__)


@export_bp.route("/api/export", methods=["POST"])
def bulk_export():
    base = current_app.config.get("CLAUDE_PROJECTS_DIR") or get_claude_projects_dir()
    projects = list_projects(base)

    buf = io.BytesIO()
    count = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for project in projects:
            sessions = list_sessions(project["path"])
            for sess_info in sessions:
                try:
                    session = parse_session(sess_info["path"])
                    if session["title"] == "Untitled Session":
                        continue
                    md = session_to_markdown(session)
                    title_slug = _slugify(session["title"])[:60]
                    short_id = sess_info["id"][:8]
                    proj_slug = _slugify(project["name"])
                    rel_path = f"{proj_slug}/{title_slug}__{short_id}.md"
                    zf.writestr(rel_path, md)
                    count += 1
                except Exception:
                    continue

    buf.seek(0)
    date_tag = datetime.now().strftime("%Y-%m-%d")
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"claude-code-export-{date_tag}.zip",
    )


@export_bp.route("/api/export/session/<path:project_name>/<session_id>")
def export_session_md(project_name, session_id):
    import os
    base = current_app.config.get("CLAUDE_PROJECTS_DIR") or get_claude_projects_dir()
    filepath = os.path.join(base, project_name, f"{session_id}.jsonl")

    if not os.path.isfile(filepath):
        return jsonify({"error": "Session not found"}), 404

    session = parse_session(filepath)
    md = session_to_markdown(session)

    buf = io.BytesIO(md.encode("utf-8"))
    buf.seek(0)
    title_slug = _slugify(session["title"])[:60]
    return send_file(
        buf,
        mimetype="text/markdown",
        as_attachment=True,
        download_name=f"{title_slug}.md",
    )


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
