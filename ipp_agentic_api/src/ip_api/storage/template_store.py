"""Default template library: ``{folder_name}/{template_name}``.

The library is not per-customer. The default folder is ``ipp_pricing_default_template``.
``FILE_STORAGE_BACKEND=local`` writes under ``{STORAGE_BASE_PATH}/templates``;
``azure_blob`` writes under ``AZURE_BLOB_TEMPLATE_PREFIX``. The SQL row still
uses the ``customer_name`` column as the folder name (no schema migration).
"""

from __future__ import annotations

import hashlib
import logging
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
from ip_api.storage.blob_store import blob_name_for_template, blob_template_prefix, get_blob_store, is_blob_ref
from ip_api.storage.db import ensure_schema, get_session_factory
from ip_api.storage.models import TemplateAsset

TEMPLATE_SUFFIX = ".docx"
TEMPLATE_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
_SEGMENT_ALLOWED = re.compile(r"[^A-Za-z0-9._-]+")


logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE_FOLDER = "ipp_pricing_default_template"


class TemplateNameError(ValueError):
    """Raised when a folder or template name cannot be used as a path segment."""


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


def resolve_folder_name(raw: str | None) -> str:
    """Use ``ipp_pricing_default_template`` when the folder is omitted."""
    value = (raw or "").strip() or DEFAULT_TEMPLATE_FOLDER
    return sanitize_segment(value, label="folder_name")


def normalize_template_name(raw: str) -> str:
    """Sanitize and force the .docx suffix (Word templates only)."""
    name = sanitize_segment(raw, label="template_name")
    if name.lower().endswith(TEMPLATE_SUFFIX):
        return f"{name[: -len(TEMPLATE_SUFFIX)]}{TEMPLATE_SUFFIX}"
    return f"{name}{TEMPLATE_SUFFIX}"


@dataclass(frozen=True)
class TemplateRecord:
    folder_name: str
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
        return f"{self.folder_name}/{self.template_name}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "folder_name": self.folder_name,
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
        folder_name=row.customer_name,
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
    """Read/write templates in the default library folder."""

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

    def local_path(self, folder_name: str, template_name: str) -> Path:
        return self.cfg.templates_root / folder_name / template_name

    def save(
        self,
        *,
        folder_name: str | None = None,
        template_name: str,
        content: bytes,
        uploaded_by: str | None = None,
    ) -> TemplateRecord:
        """Store (or replace) one template and upsert its metadata row."""
        folder = resolve_folder_name(folder_name)
        template = normalize_template_name(template_name)
        blob = get_blob_store()
        if blob.enabled:
            ref = blob.upload_bytes(content, blob_name_for_template(folder, template))
            backend = "azure_blob"
        else:
            dest = self.local_path(folder, template)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
            ref = str(dest)
            backend = "local"

        now = _now_iso()
        checksum = hashlib.sha256(content).hexdigest()
        with self._session() as session:
            row = session.scalars(
                select(TemplateAsset).where(
                    TemplateAsset.customer_name == folder,
                    TemplateAsset.template_name == template,
                )
            ).first()
            if row is None:
                row = TemplateAsset(
                    id=str(uuid.uuid4()),
                    customer_name=folder,
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

    def get(self, folder_name: str | None, template_name: str) -> TemplateRecord:
        folder = resolve_folder_name(folder_name)
        template = normalize_template_name(template_name)
        with self._session() as session:
            row = session.scalars(
                select(TemplateAsset).where(
                    TemplateAsset.customer_name == folder,
                    TemplateAsset.template_name == template,
                )
            ).first()
            if row is None:
                loose = self._loose_record(folder, template)
                if loose is not None:
                    return loose
                raise KeyError(f"Template not found: {folder}/{template}")
            return _to_record(row)

    def _loose_record(self, folder: str, template: str) -> TemplateRecord | None:
        """Disk or blob file that has no SQL row yet."""
        local = self.local_path(folder, template)
        if local.is_file():
            return self._file_record(folder, template, backend="local", ref=str(local))
        blob = get_blob_store()
        if blob.enabled:
            blob_name = blob_name_for_template(folder, template)
            if blob.exists(blob_name):
                return self._file_record(
                    folder, template, backend="azure_blob", ref=blob.to_ref(blob_name)
                )
        return None

    def _file_record(
        self,
        folder: str,
        template: str,
        *,
        backend: str,
        ref: str,
    ) -> TemplateRecord:
        now = _now_iso()
        return TemplateRecord(
            folder_name=folder,
            template_name=template,
            storage_backend=backend,
            storage_ref=ref,
            size_bytes=None,
            checksum_sha256=None,
            uploaded_by=None,
            created_at=now,
            updated_at=now,
        )

    def list_library(
        self, *, folder_name: str | None = None, limit: int = 200
    ) -> list[TemplateRecord]:
        """SQL catalog plus .docx files on disk / Blob (same folder layout)."""
        capped = max(1, min(int(limit), 500))
        filtered = bool((folder_name or "").strip())
        folder = resolve_folder_name(folder_name) if filtered else None
        by_key: dict[tuple[str, str], TemplateRecord] = {}
        for rec in self.list(folder_name=folder if filtered else None, limit=capped):
            by_key[(rec.folder_name, rec.template_name)] = rec
        scan = {folder} if folder else {DEFAULT_TEMPLATE_FOLDER, *self.list_folders()}
        for item in scan:
            self._merge_local_docx(item, by_key)
            self._merge_blob_docx(item, by_key)
        rows = sorted(by_key.values(), key=lambda r: (r.folder_name, r.template_name.lower()))
        return rows[:capped]

    def _merge_local_docx(
        self, folder: str, by_key: dict[tuple[str, str], TemplateRecord]
    ) -> None:
        directory = self.local_path(folder, "_").parent
        if not directory.is_dir():
            return
        for path in sorted(directory.glob(f"*{TEMPLATE_SUFFIX}")):
            name = path.name
            key = (folder, name)
            if key not in by_key:
                by_key[key] = self._file_record(folder, name, backend="local", ref=str(path))

    def _merge_blob_docx(
        self, folder: str, by_key: dict[tuple[str, str], TemplateRecord]
    ) -> None:
        blob = get_blob_store()
        if not blob.enabled:
            return
        prefix = f"{blob_template_prefix()}/{folder}/"
        try:
            names = blob.list_names(prefix)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not list blob templates at %s: %s", prefix, exc)
            return
        for blob_name in names:
            fname = blob_name.rsplit("/", 1)[-1]
            if not fname.lower().endswith(TEMPLATE_SUFFIX):
                continue
            key = (folder, fname)
            if key not in by_key:
                by_key[key] = self._file_record(
                    folder, fname, backend="azure_blob", ref=blob.to_ref(blob_name)
                )

    def list(
        self, *, folder_name: str | None = None, limit: int = 200
    ) -> list[TemplateRecord]:
        capped = max(1, min(int(limit), 500))
        query = select(TemplateAsset)
        if folder_name:
            query = query.where(
                TemplateAsset.customer_name == resolve_folder_name(folder_name)
            )
        query = query.order_by(
            TemplateAsset.customer_name.asc(), TemplateAsset.template_name.asc()
        ).limit(capped)
        with self._session() as session:
            return [_to_record(row) for row in session.scalars(query).all()]

    def list_folders(self) -> list[str]:
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

    def delete(self, folder_name: str | None, template_name: str) -> TemplateRecord:
        record = self.get(folder_name, template_name)
        if is_blob_ref(record.storage_ref):
            get_blob_store().delete_ref(record.storage_ref)
        else:
            Path(record.storage_ref).unlink(missing_ok=True)
        with self._session() as session:
            row = session.scalars(
                select(TemplateAsset).where(
                    TemplateAsset.customer_name == record.folder_name,
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
