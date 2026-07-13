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


def generic_key_variants(text: str) -> list[str]:
    """
    Mechanical string variants only (camelCase / snake_case).
    No hardcoded business synonyms — LLM decides semantic matches.
    """
    h = text.strip()
    if not h:
        return []
    lower = h.lower().replace("/", " ")
    snake = re.sub(r"[^a-z0-9]+", "_", lower).strip("_")
    parts = snake.split("_")
    camel = parts[0] + "".join(p.title() for p in parts[1:]) if parts else snake
    out: list[str] = []
    for item in (h, h.strip(), snake, camel, lower):
        if item and item not in out:
            out.append(item)
    return out


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
