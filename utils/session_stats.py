"""Takes a parsed session and crunches the numbers -- cost estimates, file
activity, command success rates, conversation turns, etc. Bridges the raw
parser output to the exporters."""

# Approximate pricing per 1M tokens (USD) as of early 2026.
# Used for best-effort cost estimation only.
_MODEL_PRICING = {
    # model_substring: (input_per_1m, output_per_1m)
    "opus": (15.0, 75.0),
    "sonnet": (3.0, 15.0),
    "haiku": (0.25, 1.25),
}


def compute_stats(session: dict) -> dict:
    """Build the full stats dict for a session. Everything the exporters and
    API endpoints need -- file lists, command history, cost, turn count."""
    meta = session["metadata"]
    messages = session["messages"]

    stats = {
        "files_touched": _compute_files_touched(meta),
        "commands_run": _compute_commands_run(messages),
        "urls_accessed": list(meta.get("web_fetches", [])),
        "conversation_turns": _count_turns(messages),
        "wall_clock_seconds": meta.get("session_wall_time_seconds"),
        "wall_clock_display": _format_duration(
            meta.get("session_wall_time_seconds")
        ),
        "cost_estimate_usd": _estimate_cost(messages, meta),
        "tool_result_summary": _summarize_tool_results(messages),
        "stop_reason_summary": dict(meta.get("stop_reasons", {})),
        "entry_type_counts": dict(meta.get("entry_counts", {})),
        "sidechain_message_count": meta.get("sidechain_messages", 0),
        "api_error_count": meta.get("api_errors", 0),
        "compaction_events": meta.get("compact_boundaries", []),
    }
    return stats


def _compute_files_touched(meta: dict) -> dict:
    """Split files into read-only, edited, and newly created buckets. Files
    that were both read and edited only show up under edited."""
    read = set(meta.get("files_read", []))
    written = set(meta.get("files_written", []))
    created = set(meta.get("files_created", []))
    # Files that were written may also have been read
    return {
        "read": sorted(read - written - created),
        "written": sorted(written),
        "created": sorted(created),
        "total_unique": len(read | written | created),
    }


def _compute_commands_run(messages: list) -> list:
    """Walk through messages and match up Bash tool_use calls with their
    subsequent tool_result entries to get exit codes and error status."""
    commands = []
    # Build a map of tool_use_id -> command from assistant messages
    pending_commands = {}
    for msg in messages:
        if msg["role"] == "assistant" and msg.get("tool_uses"):
            for tu in msg["tool_uses"]:
                if tu["name"] == "Bash":
                    cmd = tu["input"].get("command", "")
                    if cmd:
                        pending_commands[tu["id"]] = {
                            "command": cmd,
                            "timestamp": msg.get("timestamp"),
                        }

        # Match tool results back to commands
        if msg["role"] == "user" and msg.get("tool_result_parsed"):
            trp = msg["tool_result_parsed"]
            if trp.get("result_type") == "bash":
                # Try to find matching command by sequential order
                if pending_commands:
                    first_id = next(iter(pending_commands))
                    entry = pending_commands.pop(first_id)
                    entry["exit_code"] = trp.get("exit_code")
                    entry["is_error"] = trp.get("is_error", False)
                    entry["interrupted"] = trp.get("interrupted", False)
                    entry["return_code_interpretation"] = trp.get(
                        "return_code_interpretation"
                    )
                    commands.append(entry)

    # Add any unmatched commands (no result captured)
    for entry in pending_commands.values():
        entry["exit_code"] = None
        entry["is_error"] = None
        commands.append(entry)

    return commands


def _count_turns(messages: list) -> int:
    """Count how many times the user said something and got a reply back."""
    turns = 0
    prev_role = None
    for msg in messages:
        role = msg["role"]
        if role == "assistant" and prev_role == "user":
            turns += 1
        if role in ("user", "assistant"):
            prev_role = role
    return turns


def _estimate_cost(messages: list, meta: dict) -> float | None:
    """Rough cost estimate based on each message's token count and the model
    that generated it. Not exact -- doesn't account for caching discounts."""
    total = 0.0
    has_data = False

    for msg in messages:
        if msg["role"] != "assistant":
            continue
        model = msg.get("model", "")
        usage = msg.get("usage", {})
        inp = usage.get("input_tokens") or 0
        out = usage.get("output_tokens") or 0
        if not (inp or out):
            continue

        pricing = _get_pricing(model)
        if pricing:
            has_data = True
            total += (inp / 1_000_000) * pricing[0]
            total += (out / 1_000_000) * pricing[1]

    return round(total, 4) if has_data else None


def _get_pricing(model: str) -> tuple | None:
    """Find pricing by checking if 'opus', 'sonnet', or 'haiku' appears in
    the model name. Returns None for unknown models."""
    model_lower = model.lower()
    for key, pricing in _MODEL_PRICING.items():
        if key in model_lower:
            return pricing
    return None


def _summarize_tool_results(messages: list) -> dict:
    """Count up how many tool results succeeded, failed, or got interrupted,
    broken down by tool type."""
    summary = {
        "bash_success": 0,
        "bash_error": 0,
        "bash_interrupted": 0,
        "file_reads": 0,
        "file_edits": 0,
        "file_writes": 0,
        "glob_searches": 0,
        "grep_searches": 0,
        "web_fetches": 0,
        "web_searches": 0,
        "tasks": 0,
    }
    for msg in messages:
        if msg["role"] != "user":
            continue
        trp = msg.get("tool_result_parsed")
        if not trp:
            continue
        rt = trp.get("result_type", "")
        if rt == "bash":
            if trp.get("interrupted"):
                summary["bash_interrupted"] += 1
            elif trp.get("is_error"):
                summary["bash_error"] += 1
            else:
                summary["bash_success"] += 1
        elif rt == "file_read":
            summary["file_reads"] += 1
        elif rt == "file_edit":
            summary["file_edits"] += 1
        elif rt == "file_write":
            summary["file_writes"] += 1
        elif rt == "glob":
            summary["glob_searches"] += 1
        elif rt == "grep":
            summary["grep_searches"] += 1
        elif rt == "web_fetch":
            summary["web_fetches"] += 1
        elif rt == "web_search":
            summary["web_searches"] += 1
        elif rt == "task":
            summary["tasks"] += 1
    return summary


def _format_duration(seconds) -> str | None:
    """Turn seconds into something like '2h 15m' or '45s'."""
    if seconds is None:
        return None
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    secs = seconds % 60
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h {mins}m"
