"""Export a parsed Claude Code session to Markdown with YAML frontmatter."""

from datetime import datetime


def session_to_markdown(session: dict) -> str:
    """Convert a parsed session to rich Markdown with YAML frontmatter."""
    meta = session["metadata"]
    messages = session["messages"]
    title = session["title"]

    frontmatter = _build_frontmatter(session)
    header = _build_header(session)
    body = _build_body(messages)

    return f"{frontmatter}\n{header}\n{body}"


def _build_frontmatter(session: dict) -> str:
    meta = session["metadata"]
    lines = ["---"]
    lines.append(f"title: \"{_escape_yaml(session['title'])}\"")
    if meta["first_timestamp"]:
        lines.append(f"created: {meta['first_timestamp']}")
    if meta["last_timestamp"]:
        lines.append(f"updated: {meta['last_timestamp']}")
    lines.append(f"session_id: {session['session_id']}")
    if meta["models_used"]:
        lines.append(f"models_used: {', '.join(meta['models_used'])}")
    lines.append(f"total_input_tokens: {meta['total_input_tokens']}")
    lines.append(f"total_output_tokens: {meta['total_output_tokens']}")
    lines.append(f"total_cache_read_tokens: {meta['total_cache_read_tokens']}")
    lines.append(f"total_tool_calls: {meta['total_tool_calls']}")
    if meta["tool_call_counts"]:
        lines.append("tool_call_breakdown:")
        for tool, count in sorted(
            meta["tool_call_counts"].items(), key=lambda x: -x[1]
        ):
            lines.append(f"  {tool}: {count}")
    if meta["cwd"]:
        lines.append(f"working_directory: \"{_escape_yaml(meta['cwd'])}\"")
    if meta["git_branch"]:
        lines.append(f"git_branch: {meta['git_branch']}")
    if meta["version"]:
        lines.append(f"claude_code_version: {meta['version']}")
    if meta["permission_mode"]:
        lines.append(f"permission_mode: {meta['permission_mode']}")
    lines.append(f"message_count: {len(session['messages'])}")
    if meta["compactions"] > 0:
        lines.append(f"compactions: {meta['compactions']}")
    lines.append("---")
    return "\n".join(lines)


def _build_header(session: dict) -> str:
    meta = session["metadata"]
    lines = []
    lines.append(f"\n# {session['title']}\n")

    parts = []
    if meta["first_timestamp"]:
        parts.append(f"Created: {_format_ts(meta['first_timestamp'])}")
    if meta["models_used"]:
        parts.append(f"Models: {', '.join(meta['models_used'])}")

    token_total = meta["total_input_tokens"] + meta["total_output_tokens"]
    if token_total > 0:
        parts.append(f"Tokens: {token_total:,}")
    if meta["total_tool_calls"] > 0:
        parts.append(f"Tool calls: {meta['total_tool_calls']}")

    if parts:
        lines.append(f"_{' | '.join(parts)}_\n")
    lines.append("---\n")
    return "\n".join(lines)


def _build_body(messages: list) -> str:
    parts = []
    for msg in messages:
        role = msg["role"]
        if role == "user":
            parts.append(_render_user(msg))
        elif role == "assistant":
            parts.append(_render_assistant(msg))
        elif role == "system":
            parts.append(_render_system(msg))
    return "\n".join(parts)


def _render_user(msg: dict) -> str:
    lines = []
    lines.append("### User\n")

    if msg.get("timestamp"):
        lines.append(f"_{_format_ts(msg['timestamp'])}_\n")

    if msg.get("slug"):
        lines.append(f"_Tool response: {msg['slug']}_\n")

    if msg.get("text"):
        from utils.jsonl_parser import _strip_system_tags
        lines.append(_strip_system_tags(msg["text"]))

    if msg.get("tool_result"):
        tr = msg["tool_result"]
        if isinstance(tr, dict):
            lines.append("\n**Tool Result:**")
            lines.append(f"```\n{_truncate(str(tr), 2000)}\n```")

    lines.append("\n---\n")
    return "\n".join(lines)


def _render_assistant(msg: dict) -> str:
    lines = []
    lines.append("### Assistant\n")

    meta_parts = []
    if msg.get("model"):
        meta_parts.append(f"Model: {msg['model']}")
    usage = msg.get("usage", {})
    if usage.get("input_tokens"):
        meta_parts.append(f"In: {usage['input_tokens']:,}")
    if usage.get("output_tokens"):
        meta_parts.append(f"Out: {usage['output_tokens']:,}")
    if msg.get("timestamp"):
        meta_parts.append(_format_ts(msg["timestamp"]))
    if meta_parts:
        lines.append(f"_{' | '.join(meta_parts)}_\n")

    if msg.get("thinking"):
        lines.append("<details><summary>Thinking</summary>\n")
        lines.append(msg["thinking"])
        lines.append("\n</details>\n")

    if msg.get("text"):
        from utils.jsonl_parser import _strip_system_tags
        lines.append(_strip_system_tags(msg["text"]))

    if msg.get("tool_uses"):
        for tool in msg["tool_uses"]:
            lines.append(_render_tool_use(tool))

    lines.append("\n---\n")
    return "\n".join(lines)


def _render_tool_use(tool: dict) -> str:
    name = tool.get("name", "unknown")
    inp = tool.get("input", {})
    lines = []
    lines.append(f"\n> **Tool: {name}**")

    if name == "Bash":
        cmd = inp.get("command", "")
        lines.append(f">\n> ```bash\n> {cmd}\n> ```")
    elif name == "Read":
        lines.append(f">\n> File: `{inp.get('file_path', '')}`")
    elif name == "Write":
        fp = inp.get("file_path", "")
        content = inp.get("content", "")
        lines.append(f">\n> File: `{fp}`")
        lines.append(f">\n> ```\n> {_truncate(content, 500)}\n> ```")
    elif name == "Edit":
        fp = inp.get("file_path", "")
        old = inp.get("old_string", "")
        new = inp.get("new_string", "")
        lines.append(f">\n> File: `{fp}`")
        if old:
            lines.append(f">\n> Old:\n> ```\n> {_truncate(old, 300)}\n> ```")
        if new:
            lines.append(f">\n> New:\n> ```\n> {_truncate(new, 300)}\n> ```")
    elif name == "Glob":
        lines.append(f">\n> Pattern: `{inp.get('pattern', '')}`")
        if inp.get("path"):
            lines.append(f"> Path: `{inp['path']}`")
    elif name == "Grep":
        lines.append(f">\n> Pattern: `{inp.get('pattern', '')}`")
        if inp.get("path"):
            lines.append(f"> Path: `{inp['path']}`")
    elif name in ("WebFetch", "WebSearch"):
        lines.append(f">\n> URL/Query: `{inp.get('url', inp.get('query', ''))}`")
    elif name == "Task":
        lines.append(f">\n> Description: {inp.get('description', '')}")
        lines.append(f"> Agent: {inp.get('subagent_type', '')}")
    elif name == "TodoWrite":
        todos = inp.get("todos", [])
        for t in todos:
            status = t.get("status", "")
            icon = {"completed": "[x]", "in_progress": "[~]", "pending": "[ ]"}.get(
                status, "[ ]"
            )
            lines.append(f"> - {icon} {t.get('content', '')}")
    elif name == "AskUserQuestion":
        questions = inp.get("questions", [])
        for q in questions:
            lines.append(f">\n> Q: {q.get('question', '')}")
    else:
        inp_str = str(inp)
        if len(inp_str) > 500:
            inp_str = inp_str[:500] + "..."
        lines.append(f">\n> Input: `{inp_str}`")

    return "\n".join(lines)


def _render_system(msg: dict) -> str:
    lines = []
    subtype = msg.get("subtype", "")
    content = msg.get("content", "")

    if subtype == "compact_boundary":
        lines.append(f"\n*--- Context compacted ---*\n")
    elif content:
        lines.append(f"\n*[System: {content}]*\n")

    return "\n".join(lines)


def _format_ts(ts: str) -> str:
    """Format ISO timestamp to readable form."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError):
        return ts


def _escape_yaml(s: str) -> str:
    return s.replace('"', '\\"').replace("\n", " ")


def _truncate(s: str, max_len: int) -> str:
    if len(s) > max_len:
        return s[:max_len] + "..."
    return s
