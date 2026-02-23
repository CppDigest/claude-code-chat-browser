"""Flask web application for browsing Claude Code chat history."""

import os

from flask import Flask

from api.projects import projects_bp
from api.sessions import sessions_bp
from api.search import search_bp
from api.export_api import export_bp


def create_app(base_dir: str | None = None) -> Flask:
    app = Flask(__name__)
    app.config["CLAUDE_PROJECTS_DIR"] = base_dir

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
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--base-dir", default=None, help="Override Claude projects dir")
    args = parser.parse_args()

    app = create_app(base_dir=args.base_dir)
    print(f"Claude Code Chat Browser running at http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=True)
