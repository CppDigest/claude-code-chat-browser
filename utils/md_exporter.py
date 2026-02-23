"""Markdown export. Produces a .md with YAML frontmatter, a summary section
(cost, files touched, commands run), and the full conversation."""

from datetime import datetime


def session_to_markdown(session: dict, stats: dict = None) -> str:
    """Glue together frontmatter + header + summary + conversation body."""
    frontmatter = _build_frontmatter(session)
    header = _build_header(session)
    summary = _build_summary(session, stats) if stats else ""
    body = _build_body(session["messages"])

    parts = [frontmatter, header]
    if summary:
        parts.append(summary)
    parts.append(body)
    return "\n".join(parts)


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
    if meta.get("stop_reasons"):
        lines.append("stop_reasons:")
        for reason, count in sorted(
            meta["stop_reasons"].items(), key=lambda x: -x[1]
        ):
            lines.append(f"  {reason}: {count}")
    if meta["cwd"]:
        lines.append(f"working_directory: \"{_escape_yaml(meta['cwd'])}\"")
    if meta["git_branch"]:
        lines.append(f"git_branch: {meta['git_branch']}")
    if meta["version"]:
        lines.append(f"claude_code_version: {meta['version']}")
    if meta["permission_mode"]:
        lines.append(f"permission_mode: {meta['permission_mode']}")
    if meta.get("service_tiers"):
        lines.append(f"service_tiers: {', '.join(meta['service_tiers'])}")
    lines.append(f"message_count: {len(session['messages'])}")
    if meta["compactions"] > 0:
        lines.append(f"compactions: {meta['compactions']}")
    if meta.get("api_errors", 0) > 0:
        lines.append(f"api_errors: {meta['api_errors']}")
    if meta.get("sidechain_messages", 0) > 0:
        lines.append(f"sidechain_messages: {meta['sidechain_messages']}")
    wall = meta.get("session_wall_time_seconds")
    if wall is not None:
        lines.append(f"wall_clock_seconds: {int(wall)}")
    files_r = meta.get("files_read", [])
    files_w = meta.get("files_written", [])
    files_c = meta.get("files_created", [])
    if files_r or files_w or files_c:
        lines.append(f"files_read: {len(files_r)}")
        lines.append(f"files_written: {len(files_w)}")
        lines.append(f"files_created: {len(files_c)}")
    if meta.get("bash_commands"):
        lines.append(f"commands_run: {len(meta['bash_commands'])}")
    if meta.get("web_fetches"):
        lines.append(f"web_fetches: {len(meta['web_fetches'])}")
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
    wall = meta.get("session_wall_time_seconds")
    if wall is not None:
        from utils.session_stats import _format_duration
        dur = _format_duration(wall)
        if dur:
            parts.append(f"Duration: {dur}")

    if parts:
        lines.append(f"_{' | '.join(parts)}_\n")
    lines.append("---\n")
    return "\n".join(lines)


def _build_summary(session: dict, stats: dict) -> str:
    """The summary block that goes right after the header -- cost, files
    table, command list, URLs, tool result breakdown."""
    lines = ["## Session Summary\n"]

    # Cost estimate
    cost = stats.get("cost_estimate_usd")
    if cost is not None:
        lines.append(f"**Estimated cost:** ~${cost:.2f} USD\n")

    # Files touched
    ft = stats.get("files_touched", {})
    read_files = ft.get("read", [])
    written_files = ft.get("written", [])
    created_files = ft.get("created", [])
    if read_files or written_files or created_files:
        lines.append("### Files Touched\n")
        lines.append("| Action | File |")
        lines.append("|--------|------|")
        for fp in created_files:
            lines.append(f"| Create | `{_truncate(fp, 100)}` |")
        for fp in written_files:
            lines.append(f"| Edit | `{_truncate(fp, 100)}` |")
        for fp in read_files[:20]:
            lines.append(f"| Read | `{_truncate(fp, 100)}` |")
        if len(read_files) > 20:
            lines.append(f"| Read | _...and {len(read_files) - 20} more_ |")
        lines.append("")

    # Commands run
    commands = stats.get("commands_run", [])
    if commands:
        lines.append("### Commands Run\n")
        for i, cmd in enumerate(commands[:30], 1):
            status = ""
            if cmd.get("is_error"):
                status = " -- **error**"
            elif cmd.get("interrupted"):
                status = " -- interrupted"
            elif cmd.get("exit_code") == 0:
                status = " -- success"
            elif cmd.get("return_code_interpretation"):
                status = f" -- {cmd['return_code_interpretation']}"
            lines.append(f"{i}. `{_truncate(cmd['command'], 120)}`{status}")
        if len(commands) > 30:
            lines.append(f"\n_...and {len(commands) - 30} more commands_")
        lines.append("")

    # URLs accessed
    urls = stats.get("urls_accessed", [])
    if urls:
        lines.append("### URLs Accessed\n")
        for url in urls[:15]:
            lines.append(f"- `{_truncate(url, 150)}`")
        if len(urls) > 15:
            lines.append(f"- _...and {len(urls) - 15} more_")
        lines.append("")

    # Tool result summary
    trs = stats.get("tool_result_summary", {})
    non_zero = {k: v for k, v in trs.items() if v > 0}
    if non_zero:
        lines.append("### Tool Results\n")
        for k, v in non_zero.items():
            label = k.replace("_", " ").title()
            lines.append(f"- {label}: {v}")
        lines.append("")

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
        # Skip progress messages in MD (too noisy)
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

    # Render structured tool result instead of raw dump
    trp = msg.get("tool_result_parsed")
    if trp:
        lines.append(_render_tool_result(trp))
    elif msg.get("tool_result"):
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
    if usage.get("service_tier"):
        meta_parts.append(f"Tier: {usage['service_tier']}")
    if msg.get("timestamp"):
        meta_parts.append(_format_ts(msg["timestamp"]))
    if meta_parts:
        lines.append(f"_{' | '.join(meta_parts)}_\n")

    if msg.get("is_api_error"):
        lines.append("**[API Error]**\n")

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


def _render_tool_result(parsed: dict) -> str:
    """Format a tool result nicely instead of dumping raw JSON."""
    rt = parsed.get("result_type", "unknown")
    lines = []

    if rt == "bash":
        stdout = parsed.get("stdout", "")
        stderr = parsed.get("stderr", "")
        exit_code = parsed.get("exit_code")
        status = ""
        if parsed.get("interrupted"):
            status = " (interrupted)"
        elif parsed.get("is_error"):
            status = f" (error, exit {exit_code})"
        elif exit_code is not None:
            status = f" (exit {exit_code})"

        lines.append(f"\n**Bash Result{status}:**")
        if stdout:
            lines.append(f"```\n{_truncate(stdout, 2000)}\n```")
        if stderr:
            lines.append(f"**stderr:**\n```\n{_truncate(stderr, 1000)}\n```")

    elif rt == "file_read":
        fp = parsed.get("file_path", "")
        num_lines = parsed.get("num_lines")
        detail = f" ({num_lines} lines)" if num_lines else ""
        lines.append(f"\n**Read:** `{fp}`{detail}")

    elif rt == "file_edit":
        fp = parsed.get("file_path", "")
        lines.append(f"\n**Edited:** `{fp}`")

    elif rt == "file_write":
        fp = parsed.get("file_path", "")
        lines.append(f"\n**Wrote:** `{fp}`")

    elif rt == "glob":
        n = parsed.get("num_files", 0)
        trunc = " (truncated)" if parsed.get("truncated") else ""
        lines.append(f"\n**Glob:** {n} files found{trunc}")

    elif rt == "grep":
        n = parsed.get("num_files", 0)
        nl = parsed.get("num_lines", 0)
        lines.append(f"\n**Grep:** {n} files, {nl} lines matched")

    elif rt == "web_search":
        q = parsed.get("query", "")
        rc = parsed.get("result_count", 0)
        lines.append(f"\n**Search:** `{q}` -- {rc} results")

    elif rt == "web_fetch":
        url = parsed.get("url", "")
        code = parsed.get("status_code", "")
        lines.append(f"\n**Fetch:** `{url}` -- status {code}")

    elif rt == "task":
        lines.append("\n**Task completed**")

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
    """2024-01-15T10:30:00Z -> 2024-01-15 10:30:00"""
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
