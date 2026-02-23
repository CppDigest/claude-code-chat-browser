"""Session detail and stats endpoints."""

import os

from flask import Blueprint, current_app, jsonify, abort

from utils.session_path import get_claude_projects_dir, safe_join
from utils.jsonl_parser import parse_session
from utils.session_stats import compute_stats

sessions_bp = Blueprint("sessions", __name__)


@sessions_bp.route("/api/sessions/<path:project_name>/<session_id>")
def get_session(project_name, session_id):
    base = current_app.config.get("CLAUDE_PROJECTS_DIR") or get_claude_projects_dir()
    try:
        filepath = safe_join(base, project_name, f"{session_id}.jsonl")
    except ValueError:
        abort(400, description="Invalid path")

    if not os.path.isfile(filepath):
        abort(404, description=f"Session {session_id} not found")

    session = parse_session(filepath)
    return jsonify(session)


@sessions_bp.route("/api/sessions/<path:project_name>/<session_id>/stats")
def get_session_stats(project_name, session_id):
    base = current_app.config.get("CLAUDE_PROJECTS_DIR") or get_claude_projects_dir()
    try:
        filepath = safe_join(base, project_name, f"{session_id}.jsonl")
    except ValueError:
        abort(400, description="Invalid path")

    if not os.path.isfile(filepath):
        abort(404, description=f"Session {session_id} not found")

    session = parse_session(filepath)
    stats = compute_stats(session)
    return jsonify(stats)
