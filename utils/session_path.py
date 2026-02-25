"""Finds where Claude Code stores its .jsonl session files on disk and
lists projects/sessions from that directory."""

import os
import platform


def safe_join(base: str, *parts: str) -> str:
    """Join path components and verify the result stays under base.
    Raises ValueError if the resolved path escapes the base directory."""
    joined = os.path.realpath(os.path.join(base, *parts))
    base_resolved = os.path.realpath(base)
    if not joined.startswith(base_resolved + os.sep) and joined != base_resolved:
        raise ValueError(f"Path escapes base directory: {joined}")
    return joined


def get_claude_projects_dir() -> str:
    """~/.claude/projects/ -- handles Windows USERPROFILE vs Unix HOME."""
    system = platform.system()
    if system == "Windows":
        home = os.environ.get("USERPROFILE", os.path.expanduser("~"))
    else:
        home = os.path.expanduser("~")
    return os.path.join(home, ".claude", "projects")


def list_projects(base_dir: str | None = None) -> list[dict]:
    """Scan the projects dir and return info for each one that has .jsonl files."""
    base = base_dir or get_claude_projects_dir()
    if not os.path.isdir(base):
        return []

    projects = []
    for name in sorted(os.listdir(base)):
        project_dir = os.path.join(base, name)
        if not os.path.isdir(project_dir):
            continue
        jsonl_files = [
            f for f in os.listdir(project_dir)
            if f.endswith(".jsonl") and not f.startswith(".")
        ]
        if jsonl_files:
            latest_mtime = max(
                os.path.getmtime(os.path.join(project_dir, jf))
                for jf in jsonl_files
            )
            from datetime import datetime, timezone
            last_modified = datetime.fromtimestamp(
                latest_mtime, tz=timezone.utc
            ).isoformat()
            # Read cwd from sessions to get the real project path
            display_name = None
            for jf in jsonl_files:
                display_name = _get_display_name(
                    os.path.join(project_dir, jf), None
                )
                if display_name:
                    break
            if not display_name:
                display_name = name
            projects.append({
                "name": name,
                "path": project_dir,
                "display_name": display_name,
                "session_count": len(jsonl_files),
                "last_modified": last_modified,
            })
    return projects


def _get_display_name(jsonl_path: str, fallback: str) -> str:
    """Peek at the first entry's cwd field to get a human-readable project path
    instead of the hashed directory name."""
    import json
    try:
        with open(jsonl_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                cwd = entry.get("cwd")
                if cwd:
                    # Normalize: replace backslashes, strip trailing slash
                    cwd = cwd.replace("\\", "/").rstrip("/")
                    # Extract last folder name and capitalize first letter
                    folder = cwd.rsplit("/", 1)[-1]
                    return folder[:1].upper() + folder[1:] if folder else cwd
    except Exception:
        pass
    return fallback


def list_sessions(project_dir: str) -> list[dict]:
    """Return id, path, size, mtime for each .jsonl file in a project dir."""
    sessions = []
    if not os.path.isdir(project_dir):
        return sessions

    for fname in sorted(os.listdir(project_dir)):
        if not fname.endswith(".jsonl"):
            continue
        fpath = os.path.join(project_dir, fname)
        session_id = fname.replace(".jsonl", "")
        stat = os.stat(fpath)
        sessions.append({
            "id": session_id,
            "path": fpath,
            "size_bytes": stat.st_size,
            "modified": stat.st_mtime,
        })
    return sessions
