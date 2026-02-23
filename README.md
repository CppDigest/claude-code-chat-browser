# Claude Code Chat Browser

Browse and export Claude Code chat history — Web GUI and CLI.

## Features

- **Web GUI**: Flask-based browser with project list, session viewer, full-text search, syntax highlighting, tool call rendering, thinking blocks, dark/light mode
- **CLI Export**: Standalone script to export all sessions to Markdown with YAML frontmatter
- **Rich Markdown**: Includes token usage, tool calls (Bash, Read, Edit, Write, Glob, Grep, Task, etc.), thinking blocks, model info, timestamps
- **Incremental Export**: `--since last` flag to only export new/updated sessions
- **Bulk Export**: Download all sessions as a zip from the web UI

## Quick Start

### Web GUI

```bash
pip install flask
python app.py
# Open http://localhost:3000
```

### CLI Export

```bash
# Export all sessions as zip
python scripts/export.py

# Export to specific directory, no zip
python scripts/export.py --out ./exports --no-zip

# Incremental export (only new sessions since last run)
python scripts/export.py --since last

# Export specific project only
python scripts/export.py --project myproject
```

## Data Source

Reads from `~/.claude/projects/` which contains JSONL session files created by Claude Code.

**Read-only**: Never writes to `~/.claude/`.

## Project Structure

```
claude-code-chat-browser/
├── app.py                    # Flask entry point
├── api/
│   ├── projects.py           # Project listing endpoints
│   ├── sessions.py           # Session viewer endpoints
│   ├── search.py             # Full-text search
│   └── export_api.py         # Bulk and per-session export
├── utils/
│   ├── session_path.py       # OS-aware path detection
│   ├── jsonl_parser.py       # JSONL session parser
│   └── md_exporter.py        # Markdown exporter with frontmatter
├── scripts/
│   └── export.py             # Standalone CLI export
├── static/
│   ├── index.html            # SPA entry point
│   ├── css/style.css         # Dark/light theme
│   └── js/app.js             # Client-side routing and rendering
└── tests/
```

## Exported Markdown Format

Each exported session includes:

- **YAML frontmatter**: title, timestamps, session_id, models, token counts, tool call breakdown, working directory, git branch, Claude Code version
- **Per-message metadata**: role, model, token usage (in/out/cache), timestamp
- **Thinking blocks**: Collapsible `<details>` sections
- **Tool calls**: Formatted by type (Bash commands, file reads/edits, glob/grep patterns, subagent tasks, todos)
- **System events**: Context compaction markers
