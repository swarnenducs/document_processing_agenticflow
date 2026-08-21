"""Customer template library: ``{customer_name}/{template_name}``.

One API over both file backends. ``FILE_STORAGE_BACKEND=local`` writes under
``{STORAGE_BASE_PATH}/templates``; ``azure_blob`` writes under the container's
``AZURE_BLOB_TEMPLATE_PREFIX``. Either way the row in ``template_library``
stores a ``storage_ref`` the document pipeline can already resolve, so a job can
name a stored template instead of re-uploading the .docx.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from ip_api.core.settings import settings
from ip_api.storage.blob_store import blob_name_for_template, get_blob_store, is_blob_ref
from ip_api.storage.db import ensure_schema, get_session_factory
from ip_api.storage.models import TemplateAsset

TEMPLATE_SUFFIX = ".docx"
TEMPLATE_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
_SEGMENT_ALLOWED = re.compile(r"[^A-Za-z0-9._-]+")


class TemplateNameError(ValueError):
    """Raised when a customer or template name cannot be used as a path segment."""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def sanitize_segment(raw: str, *, label: str) -> str:
    """Collapse a user-supplied name into one safe path segment.

    Rejects traversal outright rather than silently stripping it, so a caller
    never gets a template stored somewhere other than where they asked.
    """
    value = (raw or "").strip()
    if not value:
        raise TemplateNameError(f"{label} is required")
    if "/" in value or "\\" in value or value in {".", ".."}:
        raise TemplateNameError(f"{label} must not contain path separators")
    slug = _SEGMENT_ALLOWED.sub("-", value).strip("-.")
    if not slug:
        raise TemplateNameError(f"{label} has no usable characters")
    return slug


def normalize_template_name(raw: str) -> str:
    """Sanitize and force the .docx suffix (Word templates only)."""
    name = sanitize_segment(raw, label="template_name")
    if name.lower().endswith(TEMPLATE_SUFFIX):
        return f"{name[: -len(TEMPLATE_SUFFIX)]}{TEMPLATE_SUFFIX}"
    return f"{name}{TEMPLATE_SUFFIX}"


@dataclass(frozen=True)
class TemplateRecord:
    customer_name: str
    template_name: str
    storage_backend: str
    storage_ref: str
    size_bytes: int | None
    checksum_sha256: str | None
    uploaded_by: str | None
    created_at: str
    updated_at: str

    @property
    def location(self) -> str:
        """Logical library path, independent of the backend."""
        return f"{self.customer_name}/{self.template_name}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "customer_name": self.customer_name,
            "template_name": self.template_name,
            "location": self.location,
            "storage_backend": self.storage_backend,
            "storage_ref": self.storage_ref,
            "size_bytes": self.size_bytes,
            "checksum_sha256": self.checksum_sha256,
            "uploaded_by": self.uploaded_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _to_record(row: TemplateAsset) -> TemplateRecord:
    return TemplateRecord(
        customer_name=row.customer_name,
        template_name=row.template_name,
        storage_backend=row.storage_backend,
        storage_ref=row.storage_ref,
        size_bytes=row.size_bytes,
        checksum_sha256=row.checksum_sha256,
        uploaded_by=row.uploaded_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class TemplateStore:
    """Read/write customer templates and their metadata."""

    def __init__(self) -> None:
        self.cfg = settings()
        ensure_schema()

    @contextmanager
    def _session(self) -> Iterator[Session]:
        factory = get_session_factory()
        session = factory()
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise
        finally:
            session.close()

    @property
    def backend(self) -> str:
        return "azure_blob" if get_blob_store().enabled else "local"

    def local_path(self, customer_name: str, template_name: str) -> Path:
        return self.cfg.templates_root / customer_name / template_name

    def save(
        self,
        *,
        customer_name: str,
        template_name: str,
        content: bytes,
        uploaded_by: str | None = None,
    ) -> TemplateRecord:
        """Store (or replace) one customer template and upsert its metadata row."""
        customer = sanitize_segment(customer_name, label="customer_name")
        template = normalize_template_name(template_name)
        blob = get_blob_store()
        if blob.enabled:
            ref = blob.upload_bytes(content, blob_name_for_template(customer, template))
            backend = "azure_blob"
        else:
            dest = self.local_path(customer, template)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
            ref = str(dest)
            backend = "local"

        now = _now_iso()
        checksum = hashlib.sha256(content).hexdigest()
        with self._session() as session:
            row = session.scalars(
                select(TemplateAsset).where(
                    TemplateAsset.customer_name == customer,
                    TemplateAsset.template_name == template,
                )
            ).first()
            if row is None:
                row = TemplateAsset(
                    id=str(uuid.uuid4()),
                    customer_name=customer,
                    template_name=template,
                    created_at=now,
                )
                session.add(row)
            row.storage_backend = backend
            row.storage_ref = ref
            row.content_type = TEMPLATE_CONTENT_TYPE
            row.size_bytes = len(content)
            row.checksum_sha256 = checksum
            row.uploaded_by = uploaded_by
            row.updated_at = now
            session.flush()
            return _to_record(row)

    def get(self, customer_name: str, template_name: str) -> TemplateRecord:
        customer = sanitize_segment(customer_name, label="customer_name")
        template = normalize_template_name(template_name)
        with self._session() as session:
            row = session.scalars(
                select(TemplateAsset).where(
                    TemplateAsset.customer_name == customer,
                    TemplateAsset.template_name == template,
                )
            ).first()
            if row is None:
                raise KeyError(f"Template not found: {customer}/{template}")
            return _to_record(row)

    def list(
        self, *, customer_name: str | None = None, limit: int = 200
    ) -> list[TemplateRecord]:
        capped = max(1, min(int(limit), 500))
        query = select(TemplateAsset)
        if customer_name:
            query = query.where(
                TemplateAsset.customer_name == sanitize_segment(
                    customer_name, label="customer_name"
                )
            )
        query = query.order_by(
            TemplateAsset.customer_name.asc(), TemplateAsset.template_name.asc()
        ).limit(capped)
        with self._session() as session:
            return [_to_record(row) for row in session.scalars(query).all()]

    def list_customers(self) -> list[str]:
        with self._session() as session:
            rows = session.scalars(
                select(TemplateAsset.customer_name).distinct().order_by(
                    TemplateAsset.customer_name.asc()
                )
            ).all()
            return list(rows)

    def read_bytes(self, record: TemplateRecord) -> bytes:
        """Fetch template content from whichever backend holds it."""
        if is_blob_ref(record.storage_ref):
            return get_blob_store().download_bytes(record.storage_ref)
        path = Path(record.storage_ref)
        if not path.is_file():
            raise FileNotFoundError(f"Template file missing: {path}")
        return path.read_bytes()

    def materialize(self, record: TemplateRecord, dest: Path) -> Path:
        """Copy a stored template to a local path (job scratch dir)."""
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(self.read_bytes(record))
        return dest

    def delete(self, customer_name: str, template_name: str) -> TemplateRecord:
        record = self.get(customer_name, template_name)
        if is_blob_ref(record.storage_ref):
            get_blob_store().delete_ref(record.storage_ref)
        else:
            Path(record.storage_ref).unlink(missing_ok=True)
        with self._session() as session:
            row = session.scalars(
                select(TemplateAsset).where(
                    TemplateAsset.customer_name == record.customer_name,
                    TemplateAsset.template_name == record.template_name,
                )
            ).first()
            if row is not None:
                session.delete(row)
        return record


_store: TemplateStore | None = None


def get_template_store() -> TemplateStore:
    global _store
    if _store is None:
        _store = TemplateStore()
    return _store


def reset_template_store() -> None:
    global _store
    _store = None
