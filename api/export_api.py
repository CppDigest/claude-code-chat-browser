"""Export endpoints -- bulk zip download and single-session md/json."""

import io
import json
import zipfile
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request, send_file

from utils.session_path import get_claude_projects_dir, list_projects, list_sessions
from utils.jsonl_parser import parse_session
from utils.session_stats import compute_stats
from utils.md_exporter import session_to_markdown
from utils.json_exporter import session_to_json
from utils.exclusion_rules import build_searchable_text, is_excluded_by_rules

export_bp = Blueprint("export", __name__)


def _session_text_for_exclusion(session: dict) -> str:
    """Extract a plain-text snippet from session messages for exclusion matching."""
    parts = []
    for msg in session.get("messages", []):
        text = msg.get("text") or ""
        if isinstance(text, str) and text.strip():
            parts.append(text)
    return "\n\n".join(parts)


@export_bp.route("/api/export", methods=["POST"])
def bulk_export():
    base = current_app.config.get("CLAUDE_PROJECTS_DIR") or get_claude_projects_dir()
    projects = list_projects(base)
    rules = current_app.config.get("EXCLUSION_RULES") or []

    buf = io.BytesIO()
    count = 0
    manifest = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for project in projects:
            sessions = list_sessions(project["path"])
            for sess_info in sessions:
                try:
                    session = parse_session(sess_info["path"])
                    if session["title"] == "Untitled Session":
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
                            continue

                    stats = compute_stats(session)
                    md = session_to_markdown(session, stats)
                    title_slug = _slugify(session["title"])[:60] or "session"
                    short_id = sess_info["id"][:8]
                    proj_slug = _slugify(project["name"])
                    rel_path = f"{proj_slug}/{title_slug}__{short_id}.md"
                    zf.writestr(rel_path, md)
                    manifest.append({
                        "session_id": sess_info["id"],
                        "title": session["title"],
                        "project": project["name"],
                        "tokens": session["metadata"]["total_input_tokens"]
                        + session["metadata"]["total_output_tokens"],
                        "tool_calls": session["metadata"]["total_tool_calls"],
                        "cost_estimate_usd": stats.get("cost_estimate_usd"),
                    })
                    count += 1
                except Exception as e:
                    current_app.logger.warning("Failed to export %s: %s", sess_info["id"][:10], e)
                    continue
        if manifest:
            manifest_str = "\n".join(json.dumps(e, default=str) for e in manifest)
            zf.writestr("manifest.jsonl", manifest_str)

    buf.seek(0)
    date_tag = datetime.now().strftime("%Y-%m-%d")
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"claude-code-export-{date_tag}.zip",
    )


@export_bp.route("/api/export/session/<path:project_name>/<session_id>")
def export_session(project_name, session_id):
    import os
    from utils.session_path import safe_join
    base = current_app.config.get("CLAUDE_PROJECTS_DIR") or get_claude_projects_dir()
    try:
        filepath = safe_join(base, project_name, f"{session_id}.jsonl")
    except ValueError:
        return jsonify({"error": "Invalid path"}), 400

    if not os.path.isfile(filepath):
        return jsonify({"error": "Session not found"}), 404

    fmt = request.args.get("format", "md")
    session = parse_session(filepath)
    stats = compute_stats(session)
    title_slug = _slugify(session["title"])[:60] or "session"

    if fmt == "json":
        content = session_to_json(session, stats)
        buf = io.BytesIO(content.encode("utf-8"))
        buf.seek(0)
        return send_file(
            buf,
            mimetype="application/json",
            as_attachment=True,
            download_name=f"{title_slug}.json",
        )

    md = session_to_markdown(session, stats)
    buf = io.BytesIO(md.encode("utf-8"))
    buf.seek(0)
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
