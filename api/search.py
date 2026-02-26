"""Search endpoint. Brute-force substring match across all sessions."""

import os

from flask import Blueprint, current_app, jsonify, request

from utils.session_path import get_claude_projects_dir, list_projects, list_sessions
from utils.jsonl_parser import parse_session
from utils.exclusion_rules import build_searchable_text, is_excluded_by_rules

search_bp = Blueprint("search", __name__)


@search_bp.route("/api/search")
def search():
    query = request.args.get("q", "").strip().lower()
    if not query:
        return jsonify([])

    max_results = int(request.args.get("limit", 50))
    base = current_app.config.get("CLAUDE_PROJECTS_DIR") or get_claude_projects_dir()
    projects = list_projects(base)

    rules = current_app.config.get("EXCLUSION_RULES") or []
    results = []
    for project in projects:
        sessions = list_sessions(project["path"])
        for sess_info in sessions:
            if len(results) >= max_results:
                break
            try:
                session = parse_session(sess_info["path"])
            except Exception:
                continue

            if rules:
                meta = session["metadata"]
                text_parts = [msg.get("text") or "" for msg in session.get("messages", []) if msg.get("text")]
                searchable = build_searchable_text(
                    project_name=project["name"],
                    session_title=session["title"],
                    model_names=list(meta.get("models_used") or []),
                    content_snippet="\n\n".join(text_parts),
                )
                if is_excluded_by_rules(rules, searchable):
                    continue

            for msg in session["messages"]:
                text = msg.get("text", "") or msg.get("content", "")
                if query in text.lower():
                    # Find the matching snippet
                    idx = text.lower().index(query)
                    start = max(0, idx - 80)
                    end = min(len(text), idx + len(query) + 80)
                    snippet = text[start:end]

                    results.append({
                        "project": project["name"],
                        "session_id": session["session_id"],
                        "title": session["title"],
                        "role": msg["role"],
                        "timestamp": msg.get("timestamp"),
                        "snippet": snippet,
                    })
                    if len(results) >= max_results:
                        break

    return jsonify(results)
