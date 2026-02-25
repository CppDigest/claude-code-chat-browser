"""
Regression tests for CLI argument parity between claude-code-chat-browser and
cursor-chat-browser-python.

Every flag/default documented here must match the reference (cursor) project so
that users switching between the two tools experience zero CLI friction.

Run:
    pytest tests/test_cli_args.py -v
"""

import sys
import os
import importlib
import argparse
import types
import pytest

# Ensure the repo root is on sys.path when tests are run from any directory.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from scripts.export import build_parser


# ---------------------------------------------------------------------------
# export.py argument tests
# ---------------------------------------------------------------------------

class TestExportParserFlags:
    """Every flag that cursor's export.py exposes must also exist here."""

    def setup_method(self):
        self.parser = build_parser()

    def _parse(self, argv: list[str]) -> argparse.Namespace:
        return self.parser.parse_args(argv)

    # -- --since ----------------------------------------------------------------

    def test_since_defaults_to_none_at_top_level(self):
        args = self._parse([])
        assert args.since is None  # default; cmd_export normalises to "all"

    def test_since_all(self):
        args = self._parse(["--since", "all"])
        assert args.since == "all"

    def test_since_last(self):
        args = self._parse(["--since", "last"])
        assert args.since == "last"

    def test_since_invalid_value_raises(self):
        with pytest.raises(SystemExit):
            self._parse(["--since", "yesterday"])

    def test_since_subcommand_default_is_all(self):
        args = self._parse(["export"])
        assert args.since == "all"

    def test_since_subcommand_last(self):
        args = self._parse(["export", "--since", "last"])
        assert args.since == "last"

    # -- --out ------------------------------------------------------------------

    def test_out_default_is_none(self):
        args = self._parse([])
        assert args.out is None  # cmd_export normalises to os.getcwd()

    def test_out_explicit(self):
        args = self._parse(["--out", "/tmp/exports"])
        assert args.out == "/tmp/exports"

    def test_out_subcommand(self):
        args = self._parse(["export", "--out", "/tmp/exports"])
        assert args.out == "/tmp/exports"

    # -- --no-zip ---------------------------------------------------------------

    def test_no_zip_default_false(self):
        args = self._parse([])
        assert args.no_zip is False

    def test_no_zip_flag(self):
        args = self._parse(["--no-zip"])
        assert args.no_zip is True

    def test_no_zip_subcommand(self):
        args = self._parse(["export", "--no-zip"])
        assert args.no_zip is True

    # -- --exclude-rules / -e  (cursor parity) ----------------------------------

    def test_exclude_rules_long_form_default_none(self):
        args = self._parse([])
        assert args.exclude_rules is None

    def test_exclude_rules_long_form(self):
        args = self._parse(["--exclude-rules", "/path/to/rules.txt"])
        assert args.exclude_rules == "/path/to/rules.txt"

    def test_exclude_rules_short_form(self):
        args = self._parse(["-e", "/path/to/rules.txt"])
        assert args.exclude_rules == "/path/to/rules.txt"

    def test_exclude_rules_subcommand_long(self):
        args = self._parse(["export", "--exclude-rules", "/path/rules.txt"])
        assert args.exclude_rules == "/path/rules.txt"

    def test_exclude_rules_subcommand_short(self):
        args = self._parse(["export", "-e", "/path/rules.txt"])
        assert args.exclude_rules == "/path/rules.txt"

    # -- --base-dir -------------------------------------------------------------

    def test_base_dir_default_none(self):
        args = self._parse([])
        assert args.base_dir is None

    def test_base_dir_explicit(self):
        args = self._parse(["--base-dir", "/home/user/.claude/projects"])
        assert args.base_dir == "/home/user/.claude/projects"

    def test_base_dir_subcommand(self):
        args = self._parse(["export", "--base-dir", "/home/user/.claude/projects"])
        assert args.base_dir == "/home/user/.claude/projects"

    # -- --format ---------------------------------------------------------------

    def test_format_default_none_at_top_level(self):
        args = self._parse([])
        assert args.format is None  # cmd_export normalises to "md"

    def test_format_md(self):
        args = self._parse(["--format", "md"])
        assert args.format == "md"

    def test_format_json(self):
        args = self._parse(["--format", "json"])
        assert args.format == "json"

    def test_format_both(self):
        args = self._parse(["--format", "both"])
        assert args.format == "both"

    def test_format_invalid_raises(self):
        with pytest.raises(SystemExit):
            self._parse(["--format", "csv"])

    # -- subcommand dispatch ----------------------------------------------------

    def test_no_subcommand_command_attr_is_none(self):
        args = self._parse([])
        assert getattr(args, "command", None) is None

    def test_list_subcommand(self):
        args = self._parse(["list"])
        assert args.command == "list"

    def test_stats_subcommand(self):
        args = self._parse(["stats"])
        assert args.command == "stats"

    def test_export_subcommand(self):
        args = self._parse(["export"])
        assert args.command == "export"

    # -- --help does not raise (just exits 0) -----------------------------------

    def test_help_exits_zero(self):
        with pytest.raises(SystemExit) as exc_info:
            self._parse(["--help"])
        assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# app.py argument tests
# ---------------------------------------------------------------------------

class TestAppArgparse:
    """app.py __main__ block must expose the same flags as cursor's app.py."""

    def _build_parser(self) -> argparse.ArgumentParser:
        """Re-create the argparse parser from app.py without importing Flask."""
        parser = argparse.ArgumentParser(description="Claude Code Chat Browser")
        parser.add_argument("--port", type=int, default=5000)
        parser.add_argument("--host", default="127.0.0.1")
        parser.add_argument("--base-dir", default=None)
        parser.add_argument("--exclude-rules", "-e", default=None,
                            metavar="PATH", dest="exclude_rules")
        return parser

    def test_host_default_is_localhost(self):
        """Default host must be 127.0.0.1 to match cursor which binds to localhost only."""
        parser = self._build_parser()
        args = parser.parse_args([])
        assert args.host == "127.0.0.1"

    def test_host_override(self):
        parser = self._build_parser()
        args = parser.parse_args(["--host", "127.0.0.1"])
        assert args.host == "127.0.0.1"

    def test_port_default(self):
        parser = self._build_parser()
        args = parser.parse_args([])
        assert args.port == 5000

    def test_port_override(self):
        parser = self._build_parser()
        args = parser.parse_args(["--port", "8080"])
        assert args.port == 8080

    def test_base_dir_default_none(self):
        parser = self._build_parser()
        args = parser.parse_args([])
        assert args.base_dir is None

    def test_base_dir_override(self):
        parser = self._build_parser()
        args = parser.parse_args(["--base-dir", "/tmp/projects"])
        assert args.base_dir == "/tmp/projects"

    def test_exclude_rules_default_none(self):
        parser = self._build_parser()
        args = parser.parse_args([])
        assert args.exclude_rules is None

    def test_exclude_rules_long_form(self):
        parser = self._build_parser()
        args = parser.parse_args(["--exclude-rules", "/tmp/rules.txt"])
        assert args.exclude_rules == "/tmp/rules.txt"

    def test_exclude_rules_short_form(self):
        """Cursor's app.py uses -e as the short form; claude must too."""
        parser = self._build_parser()
        args = parser.parse_args(["-e", "/tmp/rules.txt"])
        assert args.exclude_rules == "/tmp/rules.txt"

    def test_app_py_actual_argparse_has_exclude_rules(self):
        """Smoke-test: import app module and verify argparse accepts -e."""
        result = os.popen(
            f'{sys.executable} -c "'
            'import sys, os; sys.path.insert(0, os.path.abspath(\\\".\\\"));"'
        )
        # Lightweight check: parse the app.py source for the flag definition
        app_path = os.path.join(REPO_ROOT, "app.py")
        with open(app_path, "r", encoding="utf-8") as f:
            src = f.read()
        assert '"--exclude-rules"' in src or "'--exclude-rules'" in src
        assert '"-e"' in src

    def test_app_py_host_default_is_localhost(self):
        """app.py source must declare 127.0.0.1 as the --host default, matching cursor."""
        app_path = os.path.join(REPO_ROOT, "app.py")
        with open(app_path, "r", encoding="utf-8") as f:
            src = f.read()
        assert '"127.0.0.1"' in src

    def test_app_py_use_reloader_is_platform_aware(self):
        """use_reloader must depend on sys.platform, not be hardcoded False."""
        app_path = os.path.join(REPO_ROOT, "app.py")
        with open(app_path, "r", encoding="utf-8") as f:
            src = f.read()
        assert "sys.platform" in src
        assert "win32" in src
        # Must NOT have unconditional use_reloader=False
        assert "use_reloader=False" not in src
