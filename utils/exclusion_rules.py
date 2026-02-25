"""
Exclusion rules for filtering sensitive projects/sessions.

Rule file: UTF-8 text. Lines starting with # or empty are ignored.
Each other line is one rule. If ANY rule matches the combined searchable text
(project title, session title, model names, content), the item is excluded.

Rule syntax:
  - Terms separated by AND or OR (case-insensitive).
  - AND has higher precedence: "a OR b AND c" means (a) OR (b AND c).
  - Term = single word (substring match, case-insensitive) or "exact phrase".
  - One rule per line.

Example exclusion-rules.txt:
  # Exclude anything mentioning secret or internal
  secret OR internal
  "project alpha" AND confidential
  password

Note: Rules are loaded once at startup (or at the start of a CLI export run).
Changes to the exclusion rules file require an application restart (or
re-running the CLI export) to take effect.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

_logger = logging.getLogger(__name__)

DEFAULT_EXCLUSION_RULES_FILENAME = "exclusion-rules.txt"


def get_default_exclusion_rules_path() -> str:
    """Return the path to the default exclusion rules file."""
    return os.path.join(
        str(Path.home()), ".claude-code-chat-browser", DEFAULT_EXCLUSION_RULES_FILENAME
    )


def resolve_exclusion_rules_path(cli_path: str | None) -> str | None:
    """
    Resolve the exclusion rules file path.

    - If *cli_path* is given: expand and return its absolute path.  Emits a
      warning when the file does not exist so the user knows filtering is off.
    - If *cli_path* is None and the default file
      (``~/.claude-code-chat-browser/exclusion-rules.txt``) exists, return it.
    - Otherwise return None (no filtering).
    """
    if cli_path:
        p = os.path.abspath(os.path.expanduser(cli_path))
        if not os.path.isfile(p):
            _logger.warning(
                "Exclusion rules file not found: %s — no filtering will be applied.", p
            )
        return p
    default = get_default_exclusion_rules_path()
    if os.path.isfile(default):
        return default
    return None


def _tokenize_rule(line: str) -> list:
    """
    Tokenize a rule line into terms and operators.

    Returns a list where each element is ``"AND"``, ``"OR"``, or a
    ``(kind, value)`` tuple (kind is ``"word"`` or ``"phrase"``).
    """
    tokens = []
    rest = line.strip()
    while rest:
        m = re.match(r"\s+", rest)
        if m:
            rest = rest[m.end():]
            continue
        if re.match(r"\bAND\b", rest, re.IGNORECASE):
            tokens.append("AND")
            rest = rest[3:].lstrip()
            continue
        if re.match(r"\bOR\b", rest, re.IGNORECASE):
            tokens.append("OR")
            rest = rest[2:].lstrip()
            continue
        if rest.startswith('"'):
            end = rest.find('"', 1)
            if end == -1:
                tokens.append(("word", rest[1:].strip()))
                break
            tokens.append(("phrase", rest[1:end]))
            rest = rest[end + 1:].lstrip()
            continue
        m = re.match(r"\S+", rest)
        if m:
            tokens.append(("word", m.group(0)))
            rest = rest[m.end():].lstrip()
            continue
        break
    return tokens


def _term_matches(term: tuple, text: str) -> bool:
    """Case-insensitive substring match for a single term."""
    _kind, value = term
    if not value:
        return False
    return value.lower() in text.lower()


def _rule_matches(tokens: list, text: str) -> bool:
    """
    Evaluate a tokenized rule against *text*.

    Operator precedence: AND binds tighter than OR.
    Adjacent terms without an explicit operator are treated as AND.
    """
    if not tokens:
        return False
    clauses: list[list] = []
    current: list = []
    for t in tokens:
        if t == "OR":
            if current:
                clauses.append(current)
            current = []
        elif t == "AND":
            continue
        else:
            current.append(t)
    if current:
        clauses.append(current)

    for clause in clauses:
        if not clause:
            continue
        terms = [t for t in clause if isinstance(t, tuple)]
        if terms and all(_term_matches(term, text) for term in terms):
            return True
    return False


def load_rules(path: str | None) -> list[list]:
    """
    Load and parse the exclusion rule file at *path*.

    Returns a list of tokenized rules.  Returns ``[]`` when *path* is
    ``None``, the file doesn't exist, or it cannot be read.
    """
    if not path or not os.path.isfile(path):
        return []
    rules = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                tokens = _tokenize_rule(line)
                if tokens:
                    rules.append(tokens)
    except (OSError, UnicodeDecodeError) as e:
        _logger.warning(
            "Failed to read exclusion rules from %s (%s)",
            path,
            e.__class__.__name__,
            exc_info=True,
        )
        return []
    return rules


def is_excluded_by_rules(rules: list[list], searchable_text: str) -> bool:
    """
    Return ``True`` if *searchable_text* matches any exclusion rule.

    Returns ``False`` when *rules* is empty or *searchable_text* is empty.
    """
    if not searchable_text or not rules:
        return False
    for tokenized in rules:
        if _rule_matches(tokenized, searchable_text):
            return True
    return False


def build_searchable_text(
    *,
    project_name: str | None = None,
    session_title: str | None = None,
    model_names: list[str] | None = None,
    content_snippet: str | None = None,
) -> str:
    """
    Combine session/project metadata into a single string for rule matching.

    All non-empty, non-None parts are joined with newlines.
    """
    parts = []
    if project_name:
        parts.append(project_name)
    if session_title:
        parts.append(session_title)
    if model_names:
        parts.extend(model_names)
    if content_snippet:
        parts.append(content_snippet)
    return "\n".join(p for p in parts if p)
