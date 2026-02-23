"""API endpoints for listing projects."""

from flask import Blueprint, current_app, jsonify

from utils.session_path import get_claude_projects_dir, list_projects, list_sessions

projects_bp = Blueprint("projects", __name__)


@projects_bp.route("/api/projects")
def get_projects():
    base = current_app.config.get("CLAUDE_PROJECTS_DIR") or get_claude_projects_dir()
    projects = list_projects(base)
    return jsonify(projects)


@projects_bp.route("/api/projects/<path:project_name>/sessions")
def get_project_sessions(project_name):
    base = current_app.config.get("CLAUDE_PROJECTS_DIR") or get_claude_projects_dir()
    import os
    project_dir = os.path.join(base, project_name)
    sessions = list_sessions(project_dir)
    # Add summary preview for each session
    from utils.jsonl_parser import parse_session
    result = []
    for s in sessions:
        try:
            parsed = parse_session(s["path"])
            meta = parsed["metadata"]
            # Skip untitled sessions (no real conversation)
            if parsed["title"] == "Untitled Session":
                continue
            result.append({
                **s,
                "title": parsed["title"],
                "models": meta["models_used"],
                "tokens": meta["total_input_tokens"] + meta["total_output_tokens"],
                "tool_calls": meta["total_tool_calls"],
                "first_timestamp": meta["first_timestamp"],
                "last_timestamp": meta["last_timestamp"],
            })
        except Exception:
            result.append({**s, "title": "Error parsing session", "error": True})
    return jsonify(result)
