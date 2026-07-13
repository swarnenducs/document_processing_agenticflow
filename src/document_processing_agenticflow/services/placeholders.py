"""Shared Word placeholder token patterns (syntax only — no domain field names)."""

from __future__ import annotations

import re

# Token syntax forms only — NOT business field aliases
_FIELD = r"([a-zA-Z_][a-zA-Z0-9_]*(?:\[[0-9]+\])?(?:\.[a-zA-Z_][a-zA-Z0-9_]*(?:\[[0-9]+\])?)*)"
_ANGLE_FIELD = r"([A-Za-z][A-Za-z0-9 _/\-]{0,80}?)"

PLACEHOLDER_REGEXES = [
    re.compile(r"\{\{\s*" + _FIELD + r"\s*\}\}"),
    re.compile(r"\$\{\s*" + _FIELD + r"\s*\}"),
    re.compile(r"«\s*" + _FIELD + r"\s*»"),
    re.compile(r"<\s*" + _ANGLE_FIELD + r"\s*>"),
]

PLACEHOLDER_PATTERNS = [
    (re.compile(r"\{\{\s*" + _FIELD + r"\s*\}\}"), "{{", "}}"),
    (re.compile(r"\$\{\s*" + _FIELD + r"\s*\}"), "${", "}"),
    (re.compile(r"«\s*" + _FIELD + r"\s*»"), "«", "»"),
    (re.compile(r"<\s*" + _ANGLE_FIELD + r"\s*>"), "<", ">"),
]


def normalize_placeholder_key(raw: str) -> str:
    key = raw.strip()
    return re.sub(r"\s+", " ", key)


def find_placeholders(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for pattern in PLACEHOLDER_REGEXES:
        for match in pattern.findall(text):
            key = normalize_placeholder_key(match)
            if key not in seen:
                seen.add(key)
                found.append(key)
    return found
