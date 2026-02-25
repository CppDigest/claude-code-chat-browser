"""Flask app that serves the web GUI for browsing sessions."""

import os
import sys

from flask import Flask

from api.projects import projects_bp
from api.sessions import sessions_bp
from api.search import search_bp
from api.export_api import export_bp
from utils.exclusion_rules import resolve_exclusion_rules_path, load_rules


def create_app(
    base_dir: str | None = None,
    exclusion_rules_path: str | None = None,
) -> Flask:
    app = Flask(__name__)
    app.config["CLAUDE_PROJECTS_DIR"] = base_dir

    resolved = resolve_exclusion_rules_path(exclusion_rules_path)
    app.config["EXCLUSION_RULES_PATH"] = resolved
    app.config["EXCLUSION_RULES"] = load_rules(resolved)

    app.register_blueprint(projects_bp)
    app.register_blueprint(sessions_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(export_bp)

    @app.route("/")
    def index():
        return app.send_static_file("index.html")

    return app


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Claude Code Chat Browser")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--base-dir", default=None, help="Override Claude projects dir")
    parser.add_argument(
        "--exclude-rules", "-e",
        default=None,
        metavar="PATH",
        help="Path to exclusion rules file (sensitive sessions are omitted). "
             "If omitted, uses ~/.claude-code-chat-browser/exclusion-rules.txt if present.",
    )
    args = parser.parse_args()

    app = create_app(base_dir=args.base_dir, exclusion_rules_path=args.exclude_rules)
    print(f"Claude Code Chat Browser running at http://{args.host}:{args.port}")
    app.run(
        host=args.host,
        port=args.port,
        debug=True,
        use_reloader=(sys.platform != "win32"),
    )
