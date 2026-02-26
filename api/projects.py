"""Project listing endpoints."""

import traceback

from flask import Blueprint, current_app, jsonify

from utils.session_path import get_claude_projects_dir, list_projects, list_sessions, safe_join
from utils.exclusion_rules import build_searchable_text, is_excluded_by_rules

projects_bp = Blueprint("projects", __name__)


@projects_bp.route("/api/projects")
def get_projects():
    base = current_app.config.get("CLAUDE_PROJECTS_DIR") or get_claude_projects_dir()
    projects = list_projects(base)

    # Enrich each project with accurate titled-session count and latest timestamp
    # so the landing page matches what the workspace page shows.
    # Uses quick_session_info() which peeks at files without full parsing.
    from utils.jsonl_parser import quick_session_info
    for project in projects:
        sessions = list_sessions(project["path"])
        titled_count = 0
        latest_ts = None
        for s in sessions:
            try:
                info = quick_session_info(s["path"])
                if info["title"] == "Untitled Session":
                    continue
                titled_count += 1
                ts = info.get("last_timestamp") or info.get("first_timestamp")
                if ts and (latest_ts is None or ts > latest_ts):
                    latest_ts = ts
            except Exception:
                titled_count += 1
        project["session_count"] = titled_count
        if latest_ts:
            project["last_modified"] = latest_ts

    return jsonify(projects)


@projects_bp.route("/api/projects/<path:project_name>/sessions")
def get_project_sessions(project_name):
    base = current_app.config.get("CLAUDE_PROJECTS_DIR") or get_claude_projects_dir()
    try:
        project_dir = safe_join(base, project_name)
    except ValueError:
        return jsonify([]), 400
    sessions = list_sessions(project_dir)
    # Add summary preview for each session
    from utils.jsonl_parser import parse_session
    rules = current_app.config.get("EXCLUSION_RULES") or []
    result = []
    for s in sessions:
        try:
            parsed = parse_session(s["path"])
            meta = parsed["metadata"]
            # Skip untitled sessions (no real conversation)
            if parsed["title"] == "Untitled Session":
                continue
            if rules:
                text_parts = [msg.get("text") or "" for msg in parsed.get("messages", []) if msg.get("text")]
                searchable = build_searchable_text(
                    project_name=project_name,
                    session_title=parsed["title"],
                    model_names=list(meta.get("models_used") or []),
                    content_snippet="\n\n".join(text_parts),
                )
                if is_excluded_by_rules(rules, searchable):
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
        except Exception as e:
            print(f"[ERROR] Failed to parse {s['id']}: {type(e).__name__}: {e}\n{traceback.format_exc()}")
            result.append({**s, "title": "Error parsing session", "error": True, "error_detail": f"{type(e).__name__}: {e}"})
    return jsonify(result)
