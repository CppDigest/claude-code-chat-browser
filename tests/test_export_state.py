"""
Regression tests for export state storage format.

The state file at ~/.claude-code-chat-browser/export_state.json must contain
the same standardised keys as cursor-chat-browser-python's export_state.json
so that any tooling or cross-app checks on "lastExportTime" / "exportedCount"
/ "exportDir" work identically.

Run:
    pytest tests/test_export_state.py -v
"""

import json
import os
import sys
import tempfile
from datetime import datetime

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

# Patch STATE_FILE before importing the module so we don't touch the real one.
import scripts.export as _export_mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tmp_state_file(tmp_path):
    """Return a temporary state file path and patch the module to use it."""
    path = str(tmp_path / "export_state.json")
    _export_mod.STATE_FILE = path
    _export_mod.STATE_DIR = str(tmp_path)
    return path


# ---------------------------------------------------------------------------
# _save_state tests
# ---------------------------------------------------------------------------

class TestSaveState:
    def test_writes_last_export_time(self, tmp_path):
        _tmp_state_file(tmp_path)
        before = datetime.now()
        _export_mod._save_state(sessions={}, count=0, out_dir="/tmp/out")
        after = datetime.now()

        with open(_export_mod.STATE_FILE) as f:
            state = json.load(f)

        assert "lastExportTime" in state
        ts = datetime.fromisoformat(state["lastExportTime"])
        assert before <= ts <= after

    def test_writes_exported_count(self, tmp_path):
        _tmp_state_file(tmp_path)
        _export_mod._save_state(sessions={}, count=17, out_dir="/tmp/out")
        with open(_export_mod.STATE_FILE) as f:
            state = json.load(f)
        assert state["exportedCount"] == 17

    def test_writes_export_dir(self, tmp_path):
        _tmp_state_file(tmp_path)
        _export_mod._save_state(sessions={}, count=0, out_dir="/custom/export/path")
        with open(_export_mod.STATE_FILE) as f:
            state = json.load(f)
        assert state["exportDir"] == "/custom/export/path"

    def test_writes_sessions_sub_key(self, tmp_path):
        _tmp_state_file(tmp_path)
        sessions = {"uuid-aaa": 1740000000.0, "uuid-bbb": 1740001000.0}
        _export_mod._save_state(sessions=sessions, count=2, out_dir="/tmp")
        with open(_export_mod.STATE_FILE) as f:
            state = json.load(f)
        assert state["sessions"] == sessions

    def test_all_cursor_keys_present(self, tmp_path):
        """Every key that cursor-chat-browser stores must also appear here."""
        _tmp_state_file(tmp_path)
        _export_mod._save_state(sessions={}, count=5, out_dir="/tmp/exports")
        with open(_export_mod.STATE_FILE) as f:
            state = json.load(f)
        for key in ("lastExportTime", "exportedCount", "exportDir"):
            assert key in state, f"Missing cursor-parity key: {key}"

    def test_sessions_not_at_top_level(self, tmp_path):
        """Session UUIDs must be nested under 'sessions', not at top level."""
        _tmp_state_file(tmp_path)
        sessions = {"some-uuid-123": 1740000000.0}
        _export_mod._save_state(sessions=sessions, count=1, out_dir="/tmp")
        with open(_export_mod.STATE_FILE) as f:
            state = json.load(f)
        # The UUID must not be a top-level key
        assert "some-uuid-123" not in state
        assert "some-uuid-123" in state["sessions"]


# ---------------------------------------------------------------------------
# _load_state tests
# ---------------------------------------------------------------------------

class TestLoadState:
    def test_returns_empty_dict_when_no_file(self, tmp_path):
        _tmp_state_file(tmp_path)
        result = _export_mod._load_state()
        assert result == {}

    def test_reads_current_format(self, tmp_path):
        _tmp_state_file(tmp_path)
        saved = {
            "lastExportTime": "2026-02-25T12:00:00",
            "exportedCount": 3,
            "exportDir": "/tmp/exports",
            "sessions": {"uuid-x": 1740000000.0},
        }
        with open(_export_mod.STATE_FILE, "w") as f:
            json.dump(saved, f)

        result = _export_mod._load_state()
        assert result["lastExportTime"] == "2026-02-25T12:00:00"
        assert result["exportedCount"] == 3
        assert result["exportDir"] == "/tmp/exports"
        assert result["sessions"] == {"uuid-x": 1740000000.0}

    def test_migrates_legacy_flat_format(self, tmp_path):
        """Old state files that are flat dicts of session_id→mtime are migrated."""
        _tmp_state_file(tmp_path)
        legacy = {"uuid-1": 1740000000.0, "uuid-2": 1740001000.0}
        with open(_export_mod.STATE_FILE, "w") as f:
            json.dump(legacy, f)

        result = _export_mod._load_state()
        # After migration, sessions are under the "sessions" key
        assert "sessions" in result
        assert result["sessions"] == legacy
        # The old keys must not be at the top level after migration
        assert "uuid-1" not in result
        assert "uuid-2" not in result

    def test_migration_does_not_overwrite_file(self, tmp_path):
        """_load_state is read-only; it must not modify the file on disk."""
        _tmp_state_file(tmp_path)
        legacy = {"uuid-1": 1740000000.0}
        with open(_export_mod.STATE_FILE, "w") as f:
            json.dump(legacy, f)

        _export_mod._load_state()

        with open(_export_mod.STATE_FILE) as f:
            on_disk = json.load(f)
        # File unchanged after load
        assert on_disk == legacy

    def test_roundtrip_save_then_load(self, tmp_path):
        _tmp_state_file(tmp_path)
        sessions = {"sess-abc": 1740010000.0}
        _export_mod._save_state(sessions=sessions, count=1, out_dir="/roundtrip")
        loaded = _export_mod._load_state()
        assert loaded["sessions"] == sessions
        assert loaded["exportedCount"] == 1
        assert loaded["exportDir"] == "/roundtrip"
        assert "lastExportTime" in loaded


# ---------------------------------------------------------------------------
# _save_state → _load_state → since-last filtering integration
# ---------------------------------------------------------------------------

class TestSinceLastFiltering:
    """Verify the since-last flow: save state, reload, new session skipped."""

    def test_session_skipped_after_save(self, tmp_path):
        _tmp_state_file(tmp_path)
        mtime = 1740000000.0
        _export_mod._save_state(
            sessions={"sess-known": mtime}, count=1, out_dir="/tmp"
        )

        state = _export_mod._load_state()
        last_export = state.get("sessions", {})

        # A session whose mtime has NOT changed since the save should be skipped
        assert last_export.get("sess-known", 0) >= mtime

    def test_new_session_not_in_state(self, tmp_path):
        _tmp_state_file(tmp_path)
        _export_mod._save_state(sessions={}, count=0, out_dir="/tmp")

        state = _export_mod._load_state()
        last_export = state.get("sessions", {})

        # A brand-new session has no entry → prev_mtime = 0 → will be exported
        assert last_export.get("brand-new-session", 0) == 0
