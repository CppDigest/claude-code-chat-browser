# Claude Code Chat Browser

Browse and export Claude Code chat history — Web GUI and CLI.

## Features

### Web GUI
- **Project dashboard** with card grid, aggregate stats, and staggered animations
- **Session viewer** with split layout (sidebar + message panel)
- **Full-text search** across all sessions
- **Syntax highlighting** for code blocks
- **Tool call rendering** — Bash, Read, Edit, Write, Glob, Grep, Task, TodoWrite, WebFetch, WebSearch, and more
- **Thinking blocks** — collapsible sections for Claude's reasoning
- **Dark/light theme** with Inter font
- **Responsive design** — mobile-friendly with hamburger sidebar
- **Toast notifications** with icon, progress bar, and close button
- **Confirm modals** with keyboard support (Enter/Escape) and backdrop blur
- **Top loading bar** (YouTube-style) during data fetches
- **Smooth transitions** — staggered card/message animations, crossfade content swaps
- **Scroll-to-top button** in bottom-right corner
- **Per-model badges** in session header
- **Bulk export** — download all sessions as a zip

### CLI Export
- Standalone script to export all sessions to Markdown with YAML frontmatter
- Rich Markdown: token usage, tool calls, thinking blocks, model info, timestamps
- `--since last` flag for incremental export (only new/updated sessions)
- `--project` flag to export a specific project

## Quick Start

### Web GUI

```bash
# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (macOS/Linux)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run
python app.py
# Open http://localhost:5000
```

Options:
```bash
python app.py --port 8080 --host 0.0.0.0
python app.py --base-dir /path/to/claude/projects
```

### CLI Export

```bash
# Activate venv first (see above), then:

# List all projects (shows directory names you can use with --project)
python scripts/export.py list

# Export all sessions as zip
python scripts/export.py

# Export to specific directory, no zip
python scripts/export.py --out ./exports --no-zip

# Incremental export (only new sessions since last run)
python scripts/export.py --since last

# Export specific project only (substring match on directory name)
python scripts/export.py --project boost-capy
```

The `--project` flag matches against the directory names under `~/.claude/projects/`. These are path-based names like `F--boost-capy` or `d--harbor-forge`. You can use any substring — for example `boost-capy` will match `F--boost-capy`. Run `python scripts/export.py list` to see all available project names.

## Data Source

Reads from `~/.claude/projects/` which contains JSONL session files created by Claude Code.

**Read-only**: Never writes to `~/.claude/`.

## Project Structure

```
claude-code-chat-browser/
├── app.py                    # Flask entry point (default port 5000)
├── api/
│   ├── projects.py           # Project listing & session counts
│   ├── sessions.py           # Session parsing & message delivery
│   ├── search.py             # Full-text search across sessions
│   └── export_api.py         # Bulk zip and per-session Markdown export
├── utils/
│   ├── session_path.py       # OS-aware path detection & project naming
│   ├── jsonl_parser.py       # JSONL session parser with tool result classification
│   └── md_exporter.py        # Markdown exporter with YAML frontmatter
├── scripts/
│   └── export.py             # Standalone CLI export tool
├── static/
│   ├── index.html            # SPA entry point (Inter font, minimal markup)
│   ├── css/style.css         # Dark/light theme, responsive, animations
│   └── js/app.js             # Hash-based routing, rendering, UI components
└── tests/
```

## Exported Markdown Format

Each exported session includes:

- **YAML frontmatter**: title, timestamps, session_id, models, token counts, tool call breakdown, working directory, git branch, Claude Code version
- **Per-message metadata**: role, model, token usage (in/out/cache), timestamp
- **Thinking blocks**: Collapsible `<details>` sections
- **Tool calls**: Formatted by type (Bash commands, file reads/edits, glob/grep patterns, subagent tasks, todos, web fetches, plans)
- **System events**: Context compaction markers
