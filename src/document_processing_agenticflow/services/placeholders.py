"""Shared Word placeholder token patterns (syntax only — no domain field names)."""

from __future__ import annotations

import re

# Token syntax forms only — NOT business field aliases
_FIELD = r"([a-zA-Z_][a-zA-Z0-9_]*(?:\[[0-9]+\])?(?:\.[a-zA-Z_][a-zA-Z0-9_]*(?:\[[0-9]+\])?)*)"
_ANGLE_FIELD = r"([A-Za-z][A-Za-z0-9 _/\-]{0,80}?)"
# Bare contract fill markers: XX% / X% (no angle brackets).
# Do not use \b after % — % is non-word so trailing \b never matches.
_BARE_PCT = r"(?<![A-Za-z0-9_])(XX%|X%)(?![A-Za-z0-9_])"

PLACEHOLDER_REGEXES = [
    re.compile(r"\{\{\s*" + _FIELD + r"\s*\}\}"),
    re.compile(r"\$\{\s*" + _FIELD + r"\s*\}"),
    re.compile(r"«\s*" + _FIELD + r"\s*»"),
    re.compile(r"<\s*" + _ANGLE_FIELD + r"\s*>"),
    re.compile(_BARE_PCT, re.IGNORECASE),
]

PLACEHOLDER_PATTERNS = [
    (re.compile(r"\{\{\s*" + _FIELD + r"\s*\}\}"), "{{", "}}"),
    (re.compile(r"\$\{\s*" + _FIELD + r"\s*\}"), "${", "}"),
    (re.compile(r"«\s*" + _FIELD + r"\s*»"), "«", "»"),
    (re.compile(r"<\s*" + _ANGLE_FIELD + r"\s*>"), "<", ">"),
    # Replace whole bare token (e.g. XX% → 93%)
    (re.compile(_BARE_PCT, re.IGNORECASE), "", ""),
]


def normalize_placeholder_key(raw: str) -> str:
    key = raw.strip()
    # Normalize bare percent tokens to canonical upper form
    if re.fullmatch(r"XX%|X%", key, flags=re.IGNORECASE):
        return key.upper()
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
