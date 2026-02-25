"""Reads Claude Code .jsonl session files and turns them into dicts we can
actually work with -- messages, tool calls, token counts, file activity, etc."""

import json
import os
from datetime import datetime


def parse_session(filepath: str) -> dict:
    """Main entry point. Reads every line from a .jsonl file and builds up
    a session dict with messages, metadata (tokens, models, tool counts),
    and file/command activity."""
    session_id = os.path.basename(filepath).replace(".jsonl", "")
    messages = []
    metadata = {
        "session_id": session_id,
        "models_used": set(),
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cache_read_tokens": 0,
        "total_cache_creation_tokens": 0,
        "total_tool_calls": 0,
        "tool_call_counts": {},
        "first_timestamp": None,
        "last_timestamp": None,
        "version": None,
        "cwd": None,
        "git_branch": None,
        "permission_mode": None,
        "compactions": 0,
        # Extended token accounting
        "total_ephemeral_5m_tokens": 0,
        "total_ephemeral_1h_tokens": 0,
        "service_tiers": set(),
        # Timing
        "session_wall_time_seconds": None,
        # Compaction details
        "compact_boundaries": [],
        # Error tracking
        "api_errors": 0,
        # File activity (from tool_use inputs)
        "files_read": set(),
        "files_written": set(),
        "files_created": set(),
        "bash_commands": [],
        "web_fetches": [],
        # Sidechain tracking
        "sidechain_messages": 0,
        # Stop reasons
        "stop_reasons": {},
        # Entry type counts
        "entry_counts": {},
    }

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            entry_type = entry.get("type")
            ts = entry.get("timestamp")
            # file-history-snapshot stores timestamp inside snapshot
            if not ts and entry_type == "file-history-snapshot":
                snap = entry.get("snapshot")
                if isinstance(snap, dict):
                    ts = snap.get("timestamp")

            if ts:
                if metadata["first_timestamp"] is None:
                    metadata["first_timestamp"] = ts
                metadata["last_timestamp"] = ts

            # Count entry types
            if entry_type:
                metadata["entry_counts"][entry_type] = (
                    metadata["entry_counts"].get(entry_type, 0) + 1
                )

            # Track sidechain
            if entry.get("isSidechain"):
                metadata["sidechain_messages"] += 1

            if entry_type == "user":
                _process_user(entry, messages, metadata)
            elif entry_type == "assistant":
                _process_assistant(entry, messages, metadata)
            elif entry_type == "system":
                _process_system(entry, messages, metadata)
            elif entry_type == "progress":
                _process_progress(entry, messages)

    metadata["models_used"] = sorted(metadata["models_used"])
    metadata["service_tiers"] = sorted(metadata["service_tiers"])
    metadata["files_read"] = sorted(metadata["files_read"])
    metadata["files_written"] = sorted(metadata["files_written"])
    metadata["files_created"] = sorted(metadata["files_created"])

    # Compute wall clock time
    if metadata["first_timestamp"] and metadata["last_timestamp"]:
        try:
            t0 = datetime.fromisoformat(
                metadata["first_timestamp"].replace("Z", "+00:00")
            )
            t1 = datetime.fromisoformat(
                metadata["last_timestamp"].replace("Z", "+00:00")
            )
            metadata["session_wall_time_seconds"] = max(
                0, (t1 - t0).total_seconds()
            )
        except (ValueError, AttributeError):
            pass

    title = _infer_title(messages)

    return {
        "session_id": session_id,
        "title": title,
        "messages": messages,
        "metadata": metadata,
    }


def _process_user(entry: dict, messages: list, metadata: dict):
    """Pull out text, tool results, and session-level metadata (cwd, version, etc.)
    from a user entry."""
    if metadata["version"] is None:
        metadata["version"] = entry.get("version")
    if metadata["cwd"] is None:
        metadata["cwd"] = entry.get("cwd")
    if metadata["git_branch"] is None:
        metadata["git_branch"] = entry.get("gitBranch")
    if metadata["permission_mode"] is None:
        metadata["permission_mode"] = entry.get("permissionMode")

    msg = entry.get("message", {})
    content = msg.get("content", [])
    text = _extract_text(content)
    images = _extract_images(content)

    tool_result = entry.get("toolUseResult")
    tool_result_parsed = _parse_tool_result(tool_result, entry.get("slug"))

    # Also extract images from toolUseResult content (e.g., Read tool on image files)
    if isinstance(tool_result, dict) and "content" in tool_result:
        tr_content = tool_result["content"]
        if isinstance(tr_content, list):
            tr_images = _extract_images(tr_content)
            if tr_images:
                images = (images or []) + tr_images

    messages.append({
        "role": "user",
        "uuid": entry.get("uuid"),
        "parent_uuid": entry.get("parentUuid"),
        "timestamp": entry.get("timestamp"),
        "text": text,
        "images": images if images else None,
        "is_sidechain": entry.get("isSidechain", False),
        "tool_result": tool_result,
        "tool_result_parsed": tool_result_parsed,
        "slug": entry.get("slug"),
    })


def _process_assistant(entry: dict, messages: list, metadata: dict):
    """Handle assistant responses -- splits content into text, thinking blocks,
    and tool_use calls, and accumulates token/model/tool stats."""
    msg = entry.get("message", {})
    model = msg.get("model", "")
    if model and model != "<synthetic>":
        metadata["models_used"].add(model)

    # API error tracking
    if entry.get("isApiErrorMessage"):
        metadata["api_errors"] += 1

    usage = msg.get("usage", {})
    metadata["total_input_tokens"] += usage.get("input_tokens") or 0
    metadata["total_output_tokens"] += usage.get("output_tokens") or 0
    metadata["total_cache_read_tokens"] += usage.get("cache_read_input_tokens") or 0
    metadata["total_cache_creation_tokens"] += (
        usage.get("cache_creation_input_tokens") or 0
    )

    # Extended cache metrics
    cache_creation = usage.get("cache_creation", {})
    if isinstance(cache_creation, dict):
        metadata["total_ephemeral_5m_tokens"] += (
            cache_creation.get("ephemeral_5m_input_tokens") or 0
        )
        metadata["total_ephemeral_1h_tokens"] += (
            cache_creation.get("ephemeral_1h_input_tokens") or 0
        )

    # Service tier
    tier = usage.get("service_tier")
    if tier:
        metadata["service_tiers"].add(tier)

    # Stop reason tracking
    stop_reason = msg.get("stop_reason", "")
    if stop_reason:
        metadata["stop_reasons"][stop_reason] = (
            metadata["stop_reasons"].get(stop_reason, 0) + 1
        )

    content_parts = _normalize_content(msg.get("content", []))
    text_parts = []
    thinking_parts = []
    tool_uses = []

    for part in content_parts:
        ptype = part.get("type")
        if ptype == "text":
            text_parts.append(part.get("text", ""))
        elif ptype == "thinking":
            thinking_parts.append(part.get("thinking", ""))
        elif ptype == "tool_use":
            tool_name = part.get("name", "unknown")
            tool_input = part.get("input", {})
            metadata["total_tool_calls"] += 1
            metadata["tool_call_counts"][tool_name] = (
                metadata["tool_call_counts"].get(tool_name, 0) + 1
            )
            tool_uses.append({
                "id": part.get("id"),
                "name": tool_name,
                "input": tool_input,
            })
            # Track file activity from tool inputs
            safe_input = tool_input if isinstance(tool_input, dict) else {}
            _track_file_activity(tool_name, safe_input, metadata)

    messages.append({
        "role": "assistant",
        "uuid": entry.get("uuid"),
        "parent_uuid": entry.get("parentUuid"),
        "timestamp": entry.get("timestamp"),
        "model": model,
        "stop_reason": stop_reason,
        "text": "\n".join(text_parts),
        "thinking": "\n\n".join(thinking_parts) if thinking_parts else None,
        "tool_uses": tool_uses if tool_uses else None,
        "is_sidechain": entry.get("isSidechain", False),
        "is_api_error": entry.get("isApiErrorMessage", False),
        "usage": {
            "input_tokens": usage.get("input_tokens") or 0,
            "output_tokens": usage.get("output_tokens") or 0,
            "cache_read": usage.get("cache_read_input_tokens") or 0,
            "cache_creation": usage.get("cache_creation_input_tokens") or 0,
            "service_tier": usage.get("service_tier"),
        },
    })


def _process_system(entry: dict, messages: list, metadata: dict):
    """Handle system entries (mostly compact_boundary markers from context
    compaction)."""
    subtype = entry.get("subtype", "")
    if subtype == "compact_boundary":
        metadata["compactions"] += 1
        compact_meta = entry.get("compactMetadata")
        if isinstance(compact_meta, dict):
            metadata["compact_boundaries"].append({
                "timestamp": entry.get("timestamp"),
                "trigger": compact_meta.get("trigger"),
                "pre_tokens": compact_meta.get("preTokens"),
            })

    messages.append({
        "role": "system",
        "uuid": entry.get("uuid"),
        "parent_uuid": entry.get("parentUuid"),
        "timestamp": entry.get("timestamp"),
        "subtype": subtype,
        "content": entry.get("content", ""),
        "is_sidechain": entry.get("isSidechain", False),
    })


def _process_progress(entry: dict, messages: list):
    """Capture progress entries -- streaming bash output, hook results, etc.
    These are noisy so we mostly just store them for the JSON export."""
    data = entry.get("data", {})
    progress_type = data.get("type", "")

    messages.append({
        "role": "progress",
        "uuid": entry.get("uuid"),
        "parent_uuid": entry.get("parentUuid"),
        "timestamp": entry.get("timestamp"),
        "progress_type": progress_type,
        "data": data,
        "tool_use_id": entry.get("toolUseID"),
        "parent_tool_use_id": entry.get("parentToolUseID"),
        "is_sidechain": entry.get("isSidechain", False),
    })


def _track_file_activity(tool_name: str, tool_input: dict, metadata: dict):
    """Look at what each tool call did and record which files got touched,
    what commands got run, what URLs got fetched."""
    fp = tool_input.get("file_path", "")
    if tool_name == "Read" and fp:
        metadata["files_read"].add(fp)
    elif tool_name == "Write" and fp:
        metadata["files_created"].add(fp)
    elif tool_name == "Edit" and fp:
        metadata["files_written"].add(fp)
    elif tool_name == "Bash":
        cmd = tool_input.get("command", "")
        if cmd:
            metadata["bash_commands"].append(cmd)
    elif tool_name in ("WebFetch", "WebSearch"):
        url_or_query = tool_input.get("url") or tool_input.get("query", "")
        if url_or_query:
            metadata["web_fetches"].append(url_or_query)


def _parse_tool_result(tool_result, slug: str = None) -> dict | None:
    """Figure out what kind of tool result this is (bash, file edit, glob, etc.)
    by looking at which keys are present, since the JSONL doesn't always tag them."""
    if not isinstance(tool_result, dict):
        return None

    result = {"slug": slug}

    # Bash results: have stdout/stderr/interrupted
    if "stdout" in tool_result or "stderr" in tool_result:
        result["result_type"] = "bash"
        result["stdout"] = tool_result.get("stdout", "")
        result["stderr"] = tool_result.get("stderr", "")
        result["exit_code"] = tool_result.get("exitCode")
        result["interrupted"] = tool_result.get("interrupted", False)
        result["is_error"] = tool_result.get("is_error", False)
        result["return_code_interpretation"] = tool_result.get(
            "returnCodeInterpretation"
        )
        return result

    # File edit results: have filePath + structuredPatch or oldString/newString
    if "structuredPatch" in tool_result or (
        "filePath" in tool_result and "newString" in tool_result
    ):
        result["result_type"] = "file_edit"
        result["file_path"] = tool_result.get("filePath", "")
        result["replace_all"] = tool_result.get("replaceAll", False)
        return result

    # File create/write results: have filePath + content but no patch
    if "filePath" in tool_result and "content" in tool_result:
        result["result_type"] = "file_write"
        result["file_path"] = tool_result.get("filePath", "")
        return result

    # Glob results: have filenames array
    if "filenames" in tool_result and isinstance(
        tool_result.get("filenames"), list
    ):
        result["result_type"] = "glob"
        result["num_files"] = tool_result.get("numFiles", len(tool_result["filenames"]))
        result["truncated"] = tool_result.get("truncated", False)
        result["duration_ms"] = tool_result.get("durationMs")
        return result

    # Grep results: have mode + numFiles/numLines
    if "mode" in tool_result and "numFiles" in tool_result:
        result["result_type"] = "grep"
        result["mode"] = tool_result.get("mode")
        result["num_files"] = tool_result.get("numFiles", 0)
        result["num_lines"] = tool_result.get("numLines", 0)
        result["duration_ms"] = tool_result.get("durationMs")
        return result

    # Read result: have file dict with content
    if "file" in tool_result and isinstance(tool_result["file"], dict):
        result["result_type"] = "file_read"
        result["file_path"] = tool_result["file"].get("filePath", "")
        result["num_lines"] = tool_result["file"].get("numLines")
        return result

    # WebSearch results
    if "query" in tool_result and "results" in tool_result:
        result["result_type"] = "web_search"
        result["query"] = tool_result.get("query", "")
        result["result_count"] = len(tool_result.get("results", []))
        result["duration_seconds"] = tool_result.get("durationSeconds")
        return result

    # WebFetch results
    if "url" in tool_result and "code" in tool_result:
        result["result_type"] = "web_fetch"
        result["url"] = tool_result.get("url", "")
        result["status_code"] = tool_result.get("code")
        result["duration_ms"] = tool_result.get("durationMs")
        return result

    # Task results -- multiple variants
    if "task_id" in tool_result or "message" in tool_result:
        result["result_type"] = "task"
        result["task_id"] = tool_result.get("task_id")
        result["task_type"] = tool_result.get("task_type")
        return result

    # Task retrieval (has nested "task" dict + retrieval_status)
    if "retrieval_status" in tool_result and "task" in tool_result:
        result["result_type"] = "task"
        task_obj = tool_result["task"] if isinstance(tool_result["task"], dict) else {}
        result["retrieval_status"] = tool_result.get("retrieval_status")
        result["task_id"] = task_obj.get("task_id")
        return result

    # Task completed subagent (has agentId + totalDurationMs + status)
    if "agentId" in tool_result and "totalDurationMs" in tool_result:
        result["result_type"] = "task"
        result["agent_id"] = tool_result.get("agentId")
        result["status"] = tool_result.get("status")
        result["total_duration_ms"] = tool_result.get("totalDurationMs")
        result["total_tokens"] = tool_result.get("totalTokens")
        result["total_tool_use_count"] = tool_result.get("totalToolUseCount")
        return result

    # Task async launched (has agentId + isAsync + status)
    if "agentId" in tool_result and "isAsync" in tool_result:
        result["result_type"] = "task"
        result["agent_id"] = tool_result.get("agentId")
        result["status"] = tool_result.get("status")
        result["description"] = tool_result.get("description")
        return result

    # TodoWrite results (has newTodos/oldTodos)
    if "newTodos" in tool_result or "oldTodos" in tool_result:
        result["result_type"] = "todo_write"
        new_todos = tool_result.get("newTodos", [])
        result["todo_count"] = len(new_todos) if isinstance(new_todos, list) else 0
        result["todos"] = new_todos if isinstance(new_todos, list) else []
        return result

    # AskUserQuestion results (has questions/answers)
    if "questions" in tool_result and "answers" in tool_result:
        result["result_type"] = "user_input"
        result["questions"] = tool_result.get("questions", [])
        result["answers"] = tool_result.get("answers", {})
        return result

    # Plan results (has plan + filePath)
    if "plan" in tool_result and "filePath" in tool_result:
        result["result_type"] = "plan"
        result["file_path"] = tool_result.get("filePath", "")
        return result

    # Generic fallback
    result["result_type"] = "unknown"
    return result


def quick_session_info(filepath: str) -> dict:
    """Lightweight peek at a session file -- returns title and last_timestamp
    without fully parsing all messages.  Much faster than parse_session() for
    large files.

    Strategy: read the first ~50 lines for the title, then seek to the end of
    the file and read the last chunk to find the last timestamp."""
    title = None
    first_ts = None
    last_ts = None

    # --- Pass 1: read first lines to find the title and first_timestamp ---
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        lines_read = 0
        for line in f:
            lines_read += 1
            if lines_read > 80:
                break
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            ts = entry.get("timestamp")
            if ts:
                if first_ts is None:
                    first_ts = ts
                last_ts = ts  # keep updating in case file is small

            if title is None and entry.get("type") == "user":
                msg = entry.get("message", {})
                text = _extract_text(msg.get("content", []))
                if text:
                    clean = _strip_system_tags(text).strip()
                    first_line = clean.split("\n")[0][:100]
                    if first_line:
                        title = first_line

    # --- Pass 2: read last chunk for the last timestamp ---
    file_size = os.path.getsize(filepath)
    if file_size > 10000:
        # Only bother with tail-read for non-tiny files
        chunk_size = min(file_size, 32768)
        with open(filepath, "rb") as f:
            f.seek(file_size - chunk_size)
            tail = f.read().decode("utf-8", errors="replace")
        # Parse lines in reverse to find latest timestamp
        for line in reversed(tail.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = entry.get("timestamp")
            if ts:
                last_ts = ts
                break

    return {
        "title": title or "Untitled Session",
        "first_timestamp": first_ts,
        "last_timestamp": last_ts,
    }


def _normalize_content(content) -> list:
    """Content can be a plain string, a list of strings, or a list of typed
    blocks. Normalize everything into [{type, text}, ...] form."""
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        result = []
        for part in content:
            if isinstance(part, str):
                result.append({"type": "text", "text": part})
            elif isinstance(part, dict):
                result.append(part)
        return result
    return []


def _extract_text(content_parts) -> str:
    """Grab just the text blocks out of a content array, ignore tool_use/thinking."""
    parts = _normalize_content(content_parts)
    texts = []
    for part in parts:
        if part.get("type") == "text":
            texts.append(part.get("text", ""))
    return "\n".join(texts)


def _extract_images(content_parts) -> list:
    """Pull base64 image blocks out of a content array.
    Also looks inside nested tool_result content blocks."""
    parts = _normalize_content(content_parts)
    images = []
    for part in parts:
        if part.get("type") == "image":
            source = part.get("source", {})
            if source.get("type") == "base64" and source.get("data"):
                images.append({
                    "media_type": source.get("media_type", "image/png"),
                    "data": source["data"],
                })
        elif part.get("type") == "tool_result":
            nested = part.get("content", [])
            if isinstance(nested, list):
                for sub in nested:
                    if isinstance(sub, dict) and sub.get("type") == "image":
                        source = sub.get("source", {})
                        if source.get("type") == "base64" and source.get("data"):
                            images.append({
                                "media_type": source.get("media_type", "image/png"),
                                "data": source["data"],
                            })
    return images


def _infer_title(messages: list) -> str:
    """Use the first line of the first real user message as the session title."""
    for msg in messages:
        if msg["role"] == "user" and msg.get("text"):
            text = _strip_system_tags(msg["text"]).strip()
            first_line = text.split("\n")[0][:100]
            if first_line:
                return first_line
    return "Untitled Session"


def _strip_system_tags(text: str) -> str:
    """Strip out the internal XML tags Claude Code injects (system-reminder,
    ide_opened_file, etc.) so exported text is clean."""
    import re
    # Remove block tags and their content
    for tag in (
        "system-reminder", "ide_opened_file", "user-prompt-submit-hook",
        "claude_background_info", "fast_mode_info", "env",
    ):
        text = re.sub(rf"<{tag}>[\s\S]*?</{tag}>", "", text)
    # Strip remaining known opening/closing tags
    text = re.sub(r"</?(?:ide_selection|local-command-stdout|local-command-stderr|command-name|antml:\w+|function_calls|example\w*)>", "", text)
    return text.strip()
