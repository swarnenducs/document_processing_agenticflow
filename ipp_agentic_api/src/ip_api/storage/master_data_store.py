"""CRUD for legal/sales master-data blocks stored in Azure SQL or SQLite."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ip_api.storage.db import ensure_schema, get_session_factory
from ip_api.storage.models import MasterData

_PLACEHOLDER = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,255}$")


class MasterDataKeyError(ValueError):
    """Raised when placeholder_key is empty or illegal."""


def normalize_placeholder_key(raw: str) -> str:
    key = (raw or "").strip().replace(" ", "_")
    if not key or not _PLACEHOLDER.match(key):
        raise MasterDataKeyError(
            "placeholder_key must be letters, digits, and underscores "
            "(e.g. Legal_Department_Master_Data)"
        )
    return key


def _active_flag(value: bool | str | None, *, default: bool = True) -> str:
    if value is None:
        return "true" if default else "false"
    if isinstance(value, bool):
        return "true" if value else "false"
    return "true" if str(value).strip().lower() in {"1", "true", "yes", "on"} else "false"


def _row_to_dict(row: MasterData) -> dict[str, Any]:
    return {
        "id": row.id,
        "placeholder_key": row.placeholder_key,
        "category": row.category,
        "content": row.content,
        "active": row.active == "true",
        "updated_at": row.updated_at,
    }


class MasterDataStore:
    def __init__(self) -> None:
        ensure_schema()

    def _session(self) -> Session:
        return get_session_factory()()

    def upsert(
        self,
        *,
        placeholder_key: str,
        content: str,
        category: str | None = None,
        active: bool | str | None = True,
    ) -> dict[str, Any]:
        key = normalize_placeholder_key(placeholder_key)
        text = (content or "").strip()
        if not text:
            raise MasterDataKeyError("content is required")
        now = datetime.now(UTC).isoformat()
        with self._session() as session:
            row = session.scalar(select(MasterData).where(MasterData.placeholder_key == key))
            if row is None:
                cat = (category or "").strip().lower() or _default_category(key)
                row = MasterData(
                    id=str(uuid.uuid4()),
                    placeholder_key=key,
                    category=cat,
                    content=text,
                    active=_active_flag(active),
                    updated_at=now,
                )
                session.add(row)
            else:
                if category and category.strip():
                    row.category = category.strip().lower()
                row.content = text
                row.active = _active_flag(active, default=row.active == "true")
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return _row_to_dict(row)

    def list(self, *, category: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        stmt = select(MasterData).order_by(MasterData.placeholder_key)
        if category:
            stmt = stmt.where(MasterData.category == category.strip().lower())
        stmt = stmt.limit(limit)
        with self._session() as session:
            return [_row_to_dict(row) for row in session.scalars(stmt).all()]

    def get(self, placeholder_key: str) -> dict[str, Any]:
        key = normalize_placeholder_key(placeholder_key)
        with self._session() as session:
            row = session.scalar(select(MasterData).where(MasterData.placeholder_key == key))
            if row is None:
                raise KeyError(f"No master_data row for {key}")
            return _row_to_dict(row)

    def delete(self, placeholder_key: str) -> dict[str, Any]:
        key = normalize_placeholder_key(placeholder_key)
        with self._session() as session:
            row = session.scalar(select(MasterData).where(MasterData.placeholder_key == key))
            if row is None:
                raise KeyError(f"No master_data row for {key}")
            payload = _row_to_dict(row)
            session.delete(row)
            session.commit()
            return payload


def _default_category(placeholder_key: str) -> str:
    lowered = placeholder_key.lower()
    if "legal" in lowered:
        return "legal"
    if "sales" in lowered:
        return "sales"
    return "general"
