"""Session detail and stats endpoints."""

import os
import traceback

from flask import Blueprint, current_app, jsonify, abort

from utils.session_path import get_claude_projects_dir, safe_join
from utils.jsonl_parser import parse_session
from utils.session_stats import compute_stats
from utils.exclusion_rules import build_searchable_text, is_excluded_by_rules

sessions_bp = Blueprint("sessions", __name__)


@sessions_bp.route("/api/sessions/<path:project_name>/<session_id>")
def get_session(project_name, session_id):
    base = current_app.config.get("CLAUDE_PROJECTS_DIR") or get_claude_projects_dir()
    try:
        filepath = safe_join(base, project_name, f"{session_id}.jsonl")
    except ValueError:
        return jsonify({"error": "Invalid path"}), 400

    if not os.path.isfile(filepath):
        return jsonify({"error": f"Session {session_id} not found"}), 404

    try:
        session = parse_session(filepath)
        rules = current_app.config.get("EXCLUSION_RULES") or []
        if rules:
            meta = session["metadata"]
            text_parts = [msg.get("text") or "" for msg in session.get("messages", []) if msg.get("text")]
            searchable = build_searchable_text(
                project_name=project_name,
                session_title=session["title"],
                model_names=list(meta.get("models_used") or []),
                content_snippet="\n\n".join(text_parts),
            )
            if is_excluded_by_rules(rules, searchable):
                return jsonify({"error": "Session not found"}), 404
        return jsonify(session)
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[ERROR] Failed to parse session {session_id}: {e}\n{tb}")
        return jsonify({
            "error": f"Failed to parse session: {type(e).__name__}: {e}",
        }), 500


@sessions_bp.route("/api/sessions/<path:project_name>/<session_id>/stats")
def get_session_stats(project_name, session_id):
    base = current_app.config.get("CLAUDE_PROJECTS_DIR") or get_claude_projects_dir()
    try:
        filepath = safe_join(base, project_name, f"{session_id}.jsonl")
    except ValueError:
        return jsonify({"error": "Invalid path"}), 400

    if not os.path.isfile(filepath):
        return jsonify({"error": f"Session {session_id} not found"}), 404

    try:
        session = parse_session(filepath)
        stats = compute_stats(session)
        return jsonify(stats)
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[ERROR] Failed to compute stats for {session_id}: {e}\n{tb}")
        return jsonify({
            "error": f"Failed to compute stats: {type(e).__name__}: {e}",
        }), 500
