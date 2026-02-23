"""API endpoints for viewing individual sessions."""

import os

from flask import Blueprint, current_app, jsonify, abort

from utils.session_path import get_claude_projects_dir
from utils.jsonl_parser import parse_session

sessions_bp = Blueprint("sessions", __name__)


@sessions_bp.route("/api/sessions/<path:project_name>/<session_id>")
def get_session(project_name, session_id):
    base = current_app.config.get("CLAUDE_PROJECTS_DIR") or get_claude_projects_dir()
    filepath = os.path.join(base, project_name, f"{session_id}.jsonl")

    if not os.path.isfile(filepath):
        abort(404, description=f"Session {session_id} not found")

    session = parse_session(filepath)
    return jsonify(session)
