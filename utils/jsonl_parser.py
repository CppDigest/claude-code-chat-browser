"""Parse Claude Code JSONL session files into structured conversation data."""

import json
import os
from datetime import datetime


def parse_session(filepath: str) -> dict:
    """Parse a JSONL session file and return structured conversation data.

    Returns a dict with:
        session_id, project, messages[], metadata{}
    """
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

            if entry_type == "user":
                _process_user(entry, messages, metadata)
            elif entry_type == "assistant":
                _process_assistant(entry, messages, metadata)
            elif entry_type == "system":
                _process_system(entry, messages, metadata)

    metadata["models_used"] = sorted(metadata["models_used"])

    title = _infer_title(messages)

    return {
        "session_id": session_id,
        "title": title,
        "messages": messages,
        "metadata": metadata,
    }


def _process_user(entry: dict, messages: list, metadata: dict):
    """Process a user-type entry."""
    if metadata["version"] is None:
        metadata["version"] = entry.get("version")
    if metadata["cwd"] is None:
        metadata["cwd"] = entry.get("cwd")
    if metadata["git_branch"] is None:
        metadata["git_branch"] = entry.get("gitBranch")
    if metadata["permission_mode"] is None:
        metadata["permission_mode"] = entry.get("permissionMode")

    msg = entry.get("message", {})
    text = _extract_text(msg.get("content", []))

    tool_result = entry.get("toolUseResult")

    messages.append({
        "role": "user",
        "uuid": entry.get("uuid"),
        "parent_uuid": entry.get("parentUuid"),
        "timestamp": entry.get("timestamp"),
        "text": text,
        "is_sidechain": entry.get("isSidechain", False),
        "tool_result": tool_result,
        "slug": entry.get("slug"),
    })


def _process_assistant(entry: dict, messages: list, metadata: dict):
    """Process an assistant-type entry."""
    msg = entry.get("message", {})
    model = msg.get("model", "")
    if model:
        metadata["models_used"].add(model)

    usage = msg.get("usage", {})
    metadata["total_input_tokens"] += usage.get("input_tokens", 0)
    metadata["total_output_tokens"] += usage.get("output_tokens", 0)
    metadata["total_cache_read_tokens"] += usage.get("cache_read_input_tokens", 0)
    metadata["total_cache_creation_tokens"] += usage.get("cache_creation_input_tokens", 0)

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
            metadata["total_tool_calls"] += 1
            metadata["tool_call_counts"][tool_name] = (
                metadata["tool_call_counts"].get(tool_name, 0) + 1
            )
            tool_uses.append({
                "id": part.get("id"),
                "name": tool_name,
                "input": part.get("input", {}),
            })

    messages.append({
        "role": "assistant",
        "uuid": entry.get("uuid"),
        "parent_uuid": entry.get("parentUuid"),
        "timestamp": entry.get("timestamp"),
        "model": model,
        "stop_reason": msg.get("stop_reason"),
        "text": "\n".join(text_parts),
        "thinking": "\n\n".join(thinking_parts) if thinking_parts else None,
        "tool_uses": tool_uses if tool_uses else None,
        "is_sidechain": entry.get("isSidechain", False),
        "usage": {
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "cache_read": usage.get("cache_read_input_tokens", 0),
            "cache_creation": usage.get("cache_creation_input_tokens", 0),
        },
    })


def _process_system(entry: dict, messages: list, metadata: dict):
    """Process a system-type entry."""
    subtype = entry.get("subtype", "")
    if subtype == "compact_boundary":
        metadata["compactions"] += 1

    messages.append({
        "role": "system",
        "uuid": entry.get("uuid"),
        "parent_uuid": entry.get("parentUuid"),
        "timestamp": entry.get("timestamp"),
        "subtype": subtype,
        "content": entry.get("content", ""),
        "is_sidechain": entry.get("isSidechain", False),
    })


def _normalize_content(content) -> list:
    """Normalize content to a list of dicts. Handles string or list formats."""
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
    """Extract plain text from message content parts."""
    parts = _normalize_content(content_parts)
    texts = []
    for part in parts:
        if part.get("type") == "text":
            texts.append(part.get("text", ""))
    return "\n".join(texts)


def _infer_title(messages: list) -> str:
    """Infer a session title from the first user message."""
    import re
    for msg in messages:
        if msg["role"] == "user" and msg.get("text"):
            text = _strip_system_tags(msg["text"]).strip()
            first_line = text.split("\n")[0][:100]
            if first_line:
                return first_line
    return "Untitled Session"


def _strip_system_tags(text: str) -> str:
    """Remove Claude Code internal XML tags from text."""
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
