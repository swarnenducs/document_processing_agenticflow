"""SQLAlchemy JobStore against local SQLite (Azure SQL uses the same API)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from sqlalchemy.exc import OperationalError

from ip_api.core.settings import reload_settings
from ip_api.storage.job_store import JobStore


def test_sqlalchemy_insert_and_get_job(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_BASE_PATH", str(tmp_path / "storage"))
    monkeypatch.setenv("SQLITE_DATABASE_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("FILE_STORAGE_BACKEND", "local")
    monkeypatch.delenv("AZURE_SQL_SERVER", raising=False)
    monkeypatch.delenv("AZURE_SQL_PASSWORD", raising=False)
    monkeypatch.delenv("SQLALCHEMY_DATABASE_URL", raising=False)
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("AZURE_STORAGE_SAS_TOKEN", raising=False)
    monkeypatch.delenv("AZURE_STORAGE_SAS_URL", raising=False)
    reload_settings()

    store = JobStore()
    job_id, _job_dir, tpl, data, out = store.create_job_paths()
    tpl.write_bytes(b"docx")
    data.write_text("{}", encoding="utf-8")
    record = store.insert_job(job_id, tpl, data, out, xid="xid-sql")
    assert record.status == "pending"
    assert record.xid == "xid-sql"

    loaded = store.get_job(job_id)
    assert loaded.template_path == str(tpl)
    listed = store.list_document_jobs(limit=5)
    assert listed[0]["job_id"] == job_id

    store.complete_job(
        job_id,
        confidence={
            "overall_confidence": 0.87,
            "mapping_confidence": 0.9,
            "coverage_score": 1.0,
            "validation_score": 0.8,
            "validation_passed": True,
            "scores_pct": {
                "overall_confidence_pct": 87.0,
                "placeholder_mapping_confidence_pct": 90.0,
                "placeholder_coverage_pct": 100.0,
                "validation_score_pct": 80.0,
            },
            "mapper_llm": "azure_openai/gpt-4o",
            "notes": "ok",
        },
        mapper_llm="azure_openai/gpt-4o",
    )
    report = store.get_accuracy_report(job_id)
    assert report is not None
    assert report["job_id"] == job_id
    assert report["overall_confidence_pct"] == 87.0
    assert report["mapping_confidence_pct"] == 90.0
    assert report["scores_pct"]["overall_confidence_pct"] == 87.0
    reload_settings()


def test_run_read_retries_operational_error_once(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_BASE_PATH", str(tmp_path / "storage"))
    monkeypatch.setenv("SQLITE_DATABASE_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("FILE_STORAGE_BACKEND", "local")
    monkeypatch.delenv("AZURE_SQL_SERVER", raising=False)
    monkeypatch.delenv("AZURE_SQL_PASSWORD", raising=False)
    monkeypatch.delenv("SQLALCHEMY_DATABASE_URL", raising=False)
    reload_settings()

    store = JobStore()
    job_id, _job_dir, tpl, data, out = store.create_job_paths()
    tpl.write_bytes(b"docx")
    data.write_text("{}", encoding="utf-8")
    store.insert_job(job_id, tpl, data, out, xid="xid-retry")

    boom = OperationalError("stmt", {}, Exception("08S01"))
    real_session = store._session
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        if calls["n"] == 0:
            calls["n"] += 1

            class _Boom:
                def __enter__(self):
                    raise boom

                def __exit__(self, *exc):
                    return False

            return _Boom()
        return real_session(*args, **kwargs)

    with (
        patch.object(store, "_session", side_effect=flaky),
        patch.object(store, "_invalidate_sql_pool") as inv,
    ):
        loaded = store.get_job(job_id)
        assert loaded.id == job_id
        inv.assert_called_once()

    reload_settings()
