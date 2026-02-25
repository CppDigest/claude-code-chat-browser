"""Regression tests for null usage token fields.

When the Claude API emits a usage object where a token field is present but
null (e.g. ``"cache_read_input_tokens": null``), the old code raised:

    TypeError: unsupported operand type(s) for +=: 'int' and 'NoneType'

because ``dict.get(key, 0)`` returns ``None`` when the key exists with a null
value -- the default only fires when the key is *absent*.
"""

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.jsonl_parser import parse_session, _process_assistant
from utils.session_stats import _estimate_cost


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_metadata() -> dict:
    """Return a minimal metadata dict matching what parse_session initialises."""
    return {
        "models_used": set(),
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cache_read_tokens": 0,
        "total_cache_creation_tokens": 0,
        "total_tool_calls": 0,
        "tool_call_counts": {},
        "first_timestamp": None,
        "last_timestamp": None,
        "total_ephemeral_5m_tokens": 0,
        "total_ephemeral_1h_tokens": 0,
        "service_tiers": set(),
        "stop_reasons": {},
        "api_errors": 0,
        "files_read": set(),
        "files_written": set(),
        "files_created": set(),
        "bash_commands": [],
        "web_fetches": [],
        "sidechain_messages": 0,
        "entry_counts": {},
        "compactions": 0,
        "compact_boundaries": [],
        "session_wall_time_seconds": None,
        "version": None,
        "cwd": None,
        "git_branch": None,
        "permission_mode": None,
    }


def _assistant_entry(usage: dict) -> dict:
    """Build a minimal assistant JSONL entry with the given usage dict."""
    return {
        "type": "assistant",
        "uuid": "test-uuid",
        "parentUuid": None,
        "timestamp": "2026-01-01T00:00:00.000Z",
        "message": {
            "model": "claude-sonnet-4-5",
            "content": [{"type": "text", "text": "Hello"}],
            "stop_reason": "end_turn",
            "usage": usage,
        },
    }


# ---------------------------------------------------------------------------
# _process_assistant: null fields must not raise
# ---------------------------------------------------------------------------

class TestProcessAssistantNullUsage:
    """Unit tests for _process_assistant with null token values."""

    def test_null_cache_read_tokens(self):
        meta = _fresh_metadata()
        entry = _assistant_entry({"input_tokens": 100, "output_tokens": 50,
                                  "cache_read_input_tokens": None,
                                  "cache_creation_input_tokens": 0})
        _process_assistant(entry, [], meta)
        assert meta["total_input_tokens"] == 100
        assert meta["total_output_tokens"] == 50
        assert meta["total_cache_read_tokens"] == 0

    def test_null_cache_creation_tokens(self):
        meta = _fresh_metadata()
        entry = _assistant_entry({"input_tokens": 200, "output_tokens": 80,
                                  "cache_read_input_tokens": 0,
                                  "cache_creation_input_tokens": None})
        _process_assistant(entry, [], meta)
        assert meta["total_cache_creation_tokens"] == 0

    def test_null_input_tokens(self):
        meta = _fresh_metadata()
        entry = _assistant_entry({"input_tokens": None, "output_tokens": 30})
        _process_assistant(entry, [], meta)
        assert meta["total_input_tokens"] == 0
        assert meta["total_output_tokens"] == 30

    def test_null_output_tokens(self):
        meta = _fresh_metadata()
        entry = _assistant_entry({"input_tokens": 10, "output_tokens": None})
        _process_assistant(entry, [], meta)
        assert meta["total_input_tokens"] == 10
        assert meta["total_output_tokens"] == 0

    def test_all_null_usage_fields(self):
        meta = _fresh_metadata()
        entry = _assistant_entry({
            "input_tokens": None,
            "output_tokens": None,
            "cache_read_input_tokens": None,
            "cache_creation_input_tokens": None,
        })
        _process_assistant(entry, [], meta)
        assert meta["total_input_tokens"] == 0
        assert meta["total_output_tokens"] == 0
        assert meta["total_cache_read_tokens"] == 0
        assert meta["total_cache_creation_tokens"] == 0

    def test_null_ephemeral_tokens(self):
        meta = _fresh_metadata()
        entry = _assistant_entry({
            "input_tokens": 10,
            "output_tokens": 5,
            "cache_creation": {
                "ephemeral_5m_input_tokens": None,
                "ephemeral_1h_input_tokens": None,
            },
        })
        _process_assistant(entry, [], meta)
        assert meta["total_ephemeral_5m_tokens"] == 0
        assert meta["total_ephemeral_1h_tokens"] == 0

    def test_per_message_usage_dict_has_no_null(self):
        """The usage dict stored on the message itself must never contain None."""
        messages = []
        meta = _fresh_metadata()
        entry = _assistant_entry({
            "input_tokens": None,
            "output_tokens": None,
            "cache_read_input_tokens": None,
            "cache_creation_input_tokens": None,
        })
        _process_assistant(entry, messages, meta)
        assert len(messages) == 1
        usage = messages[0]["usage"]
        assert usage["input_tokens"] == 0
        assert usage["output_tokens"] == 0
        assert usage["cache_read"] == 0
        assert usage["cache_creation"] == 0

    def test_normal_values_still_accumulate(self):
        """Sanity check: valid integer values are accumulated correctly."""
        meta = _fresh_metadata()
        for _ in range(3):
            entry = _assistant_entry({
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_read_input_tokens": 20,
                "cache_creation_input_tokens": 10,
            })
            _process_assistant(entry, [], meta)
        assert meta["total_input_tokens"] == 300
        assert meta["total_output_tokens"] == 150
        assert meta["total_cache_read_tokens"] == 60
        assert meta["total_cache_creation_tokens"] == 30


# ---------------------------------------------------------------------------
# parse_session (integration): null usage survives round-trip via temp file
# ---------------------------------------------------------------------------

class TestParseSessionNullUsage:
    """Integration tests: parse_session must not raise on null usage fields."""

    def _write_session(self, entries: list) -> str:
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        )
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
        f.close()
        return f.name

    def test_null_cache_read_does_not_crash(self):
        path = self._write_session([
            _assistant_entry({
                "input_tokens": 500,
                "output_tokens": 100,
                "cache_read_input_tokens": None,
                "cache_creation_input_tokens": None,
            })
        ])
        try:
            session = parse_session(path)
            assert session["metadata"]["total_input_tokens"] == 500
            assert session["metadata"]["total_cache_read_tokens"] == 0
        finally:
            os.unlink(path)

    def test_mixed_null_and_normal_entries(self):
        """A session with some null-usage entries and some normal ones should
        accumulate only the non-null values."""
        path = self._write_session([
            _assistant_entry({"input_tokens": 100, "output_tokens": 40,
                              "cache_read_input_tokens": None}),
            _assistant_entry({"input_tokens": 200, "output_tokens": 80,
                              "cache_read_input_tokens": 30}),
        ])
        try:
            session = parse_session(path)
            assert session["metadata"]["total_input_tokens"] == 300
            assert session["metadata"]["total_output_tokens"] == 120
            assert session["metadata"]["total_cache_read_tokens"] == 30
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# _estimate_cost: null tokens must not crash cost calculation
# ---------------------------------------------------------------------------

class TestEstimateCostNullUsage:
    """Unit tests for _estimate_cost with null token values."""

    def _make_messages(self, usage_list: list) -> list:
        return [
            {"role": "assistant", "model": model, "usage": usage}
            for model, usage in usage_list
        ]

    def test_null_output_tokens_with_valid_input(self):
        messages = self._make_messages([
            ("claude-sonnet-4-5", {"input_tokens": 1_000_000, "output_tokens": None}),
        ])
        cost = _estimate_cost(messages, {})
        assert cost is not None
        assert cost == pytest.approx(3.0, rel=1e-3)

    def test_null_input_tokens_with_valid_output(self):
        messages = self._make_messages([
            ("claude-sonnet-4-5", {"input_tokens": None, "output_tokens": 1_000_000}),
        ])
        cost = _estimate_cost(messages, {})
        assert cost is not None
        assert cost == pytest.approx(15.0, rel=1e-3)

    def test_all_null_tokens_returns_none(self):
        messages = self._make_messages([
            ("claude-sonnet-4-5", {"input_tokens": None, "output_tokens": None}),
        ])
        cost = _estimate_cost(messages, {})
        assert cost is None

    def test_normal_values_unaffected(self):
        messages = self._make_messages([
            ("claude-sonnet-4-5", {"input_tokens": 1_000_000, "output_tokens": 1_000_000}),
        ])
        cost = _estimate_cost(messages, {})
        assert cost == pytest.approx(18.0, rel=1e-3)
