"""
Integration tests for --exclude-rules / -e filtering in scripts/export.py.

These tests exercise the full CLI pipeline: synthetic JSONL session files on
disk, a rules file, and the export subcommand, verifying that matched sessions
are omitted from output.

Run:
    pytest tests/test_export_exclusion_filtering.py -v
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPORT_SCRIPT = REPO_ROOT / "scripts" / "export.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_session(project_dir: Path, session_id: str, messages: list[dict]) -> Path:
    """Write a minimal JSONL session file and return its path."""
    path = project_dir / f"{session_id}.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for entry in messages:
            f.write(json.dumps(entry) + "\n")
    return path


def _user_entry(text: str, session_id: str, parent_uuid: str | None = None) -> dict:
    return {
        "type": "user",
        "uuid": f"user-{text[:8].replace(' ', '-')}",
        "parentUuid": parent_uuid,
        "timestamp": "2026-02-25T10:00:00.000Z",
        "sessionId": session_id,
        "cwd": "/home/user/project",
        "message": {"role": "user", "content": [{"type": "text", "text": text}]},
    }


def _assistant_entry(text: str, session_id: str, parent_uuid: str) -> dict:
    return {
        "type": "assistant",
        "uuid": f"asst-{text[:8].replace(' ', '-')}",
        "parentUuid": parent_uuid,
        "timestamp": "2026-02-25T10:00:05.000Z",
        "sessionId": session_id,
        "message": {
            "role": "assistant",
            "model": "claude-opus-4-5",
            "content": [{"type": "text", "text": text}],
            "stop_reason": "end_turn",
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
        },
    }


def _run_export(
    base_dir: Path,
    out_dir: Path,
    rules_path: Path | None,
    extra_args: list[str] | None = None,
) -> subprocess.CompletedProcess:
    cmd = [
        sys.executable,
        str(EXPORT_SCRIPT),
        "--base-dir", str(base_dir),
        "--since", "all",
        "--no-zip",
        "--out", str(out_dir),
    ]
    if rules_path:
        cmd += ["--exclude-rules", str(rules_path)]
    if extra_args:
        cmd += extra_args
    return subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )


def _collect_md(out_dir: Path) -> list[Path]:
    return sorted(out_dir.rglob("*.md"))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExclusionRulesFiltering:
    def test_matched_session_is_excluded(self, tmp_path):
        """A session whose content matches an exclusion rule must not be exported."""
        proj_dir = tmp_path / "projects" / "-home-user-myproject"
        proj_dir.mkdir(parents=True)
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        sid_secret = "aaaa1111-0000-0000-0000-000000000001"
        sid_safe = "bbbb2222-0000-0000-0000-000000000002"

        u1 = _user_entry("Please summarize our secret roadmap for Q1.", sid_secret)
        a1 = _assistant_entry("Here is the summary.", sid_secret, u1["uuid"])
        _write_session(proj_dir, sid_secret, [u1, a1])

        u2 = _user_entry("How do I write a unit test in Python?", sid_safe)
        a2 = _assistant_entry("Use pytest.", sid_safe, u2["uuid"])
        _write_session(proj_dir, sid_safe, [u2, a2])

        rules_file = tmp_path / "rules.txt"
        rules_file.write_text("secret\n", encoding="utf-8")

        proc = _run_export(
            base_dir=tmp_path / "projects",
            out_dir=out_dir,
            rules_path=rules_file,
        )
        assert proc.returncode == 0, proc.stderr

        md_files = _collect_md(out_dir)
        assert len(md_files) == 1
        content = md_files[0].read_text(encoding="utf-8").lower()
        assert "unit test" in content or "pytest" in content
        assert "secret roadmap" not in content

    def test_short_flag_e_works(self, tmp_path):
        """-e must be accepted as an alias for --exclude-rules."""
        proj_dir = tmp_path / "projects" / "-home-user-proj"
        proj_dir.mkdir(parents=True)
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        sid = "cccc3333-0000-0000-0000-000000000003"
        u = _user_entry("Discuss confidential merger plans.", sid)
        a = _assistant_entry("OK.", sid, u["uuid"])
        _write_session(proj_dir, sid, [u, a])

        rules_file = tmp_path / "rules.txt"
        rules_file.write_text("confidential\n", encoding="utf-8")

        cmd = [
            sys.executable,
            str(EXPORT_SCRIPT),
            "--base-dir", str(tmp_path / "projects"),
            "--since", "all",
            "--no-zip",
            "--out", str(out_dir),
            "-e", str(rules_file),
        ]
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr

        md_files = _collect_md(out_dir)
        assert len(md_files) == 0, "Session matching rule should have been excluded"

    def test_no_rules_file_exports_all(self, tmp_path):
        """Without --exclude-rules all sessions must be exported."""
        proj_dir = tmp_path / "projects" / "-home-user-proj"
        proj_dir.mkdir(parents=True)
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        for i, text in enumerate(["alpha content", "beta content"]):
            sid = f"dddd{i:04d}-0000-0000-0000-00000000000{i}"
            u = _user_entry(text, sid)
            a = _assistant_entry("Acknowledged.", sid, u["uuid"])
            _write_session(proj_dir, sid, [u, a])

        proc = _run_export(
            base_dir=tmp_path / "projects",
            out_dir=out_dir,
            rules_path=None,
        )
        assert proc.returncode == 0, proc.stderr
        md_files = _collect_md(out_dir)
        assert len(md_files) == 2

    def test_and_rule_requires_both_terms(self, tmp_path):
        """An AND rule must exclude only sessions containing BOTH terms."""
        proj_dir = tmp_path / "projects" / "-home-user-proj"
        proj_dir.mkdir(parents=True)
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        sid_both = "eeee1111-0000-0000-0000-000000000001"
        sid_one = "ffff2222-0000-0000-0000-000000000002"

        u1 = _user_entry("This is a private AND confidential matter.", sid_both)
        a1 = _assistant_entry("Understood.", sid_both, u1["uuid"])
        _write_session(proj_dir, sid_both, [u1, a1])

        u2 = _user_entry("This is a private note but nothing else.", sid_one)
        a2 = _assistant_entry("Noted.", sid_one, u2["uuid"])
        _write_session(proj_dir, sid_one, [u2, a2])

        rules_file = tmp_path / "rules.txt"
        rules_file.write_text("private AND confidential\n", encoding="utf-8")

        proc = _run_export(
            base_dir=tmp_path / "projects",
            out_dir=out_dir,
            rules_path=rules_file,
        )
        assert proc.returncode == 0, proc.stderr

        md_files = _collect_md(out_dir)
        # Only the session with just "private" should survive
        assert len(md_files) == 1
        content = md_files[0].read_text(encoding="utf-8").lower()
        assert "nothing else" in content

    def test_exclude_rules_subcommand(self, tmp_path):
        """--exclude-rules must also work on the explicit 'export' subcommand."""
        proj_dir = tmp_path / "projects" / "-home-user-proj"
        proj_dir.mkdir(parents=True)
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        sid = "9999aaaa-0000-0000-0000-000000000001"
        u = _user_entry("Top secret mission briefing.", sid)
        a = _assistant_entry("Copy that.", sid, u["uuid"])
        _write_session(proj_dir, sid, [u, a])

        rules_file = tmp_path / "rules.txt"
        rules_file.write_text("secret\n", encoding="utf-8")

        cmd = [
            sys.executable,
            str(EXPORT_SCRIPT),
            "export",
            "--base-dir", str(tmp_path / "projects"),
            "--since", "all",
            "--no-zip",
            "--out", str(out_dir),
            "--exclude-rules", str(rules_file),
        ]
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        assert len(_collect_md(out_dir)) == 0

    def test_state_saved_after_export_with_rules(self, tmp_path):
        """State file must be written and include cursor-parity keys."""
        proj_dir = tmp_path / "projects" / "-home-user-proj"
        proj_dir.mkdir(parents=True)
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        sid = "1a2b3c4d-0000-0000-0000-000000000001"
        u = _user_entry("Hello world.", sid)
        a = _assistant_entry("Hi there.", sid, u["uuid"])
        _write_session(proj_dir, sid, [u, a])

        # Patch STATE_FILE inside subprocess via env is complex; instead verify
        # by running with a custom STATE_DIR via monkeypatching in the same
        # process — we test the _save_state API directly.
        import scripts.export as exp
        original_state_file = exp.STATE_FILE
        original_state_dir = exp.STATE_DIR
        exp.STATE_FILE = str(state_dir / "export_state.json")
        exp.STATE_DIR = str(state_dir)
        try:
            exp._save_state(
                sessions={sid: 1740000000.0}, count=1, out_dir=str(out_dir)
            )
            with open(exp.STATE_FILE) as f:
                state = json.load(f)
            for key in ("lastExportTime", "exportedCount", "exportDir", "sessions"):
                assert key in state, f"Missing required state key: {key}"
        finally:
            exp.STATE_FILE = original_state_file
            exp.STATE_DIR = original_state_dir
