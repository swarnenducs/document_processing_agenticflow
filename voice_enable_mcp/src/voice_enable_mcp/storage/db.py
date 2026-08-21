"""SQLAlchemy 2.x engine for local SQLite or Azure SQL.

Same resolution order as ip_api and the document MCP, so the voice MCP follows
whatever backend the deployment configures: SQLite for local runs, Azure SQL
when ``AZURE_SQL_*`` (or an explicit ``SQLALCHEMY_DATABASE_URL``) is set.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from voice_enable_mcp.core.settings import settings

_engine_cache: dict[str, Engine] = {}
_session_cache: dict[str, sessionmaker[Session]] = {}


def _odbc_escape(value: str) -> str:
    """ODBC brace-wrap: closing braces in passwords must be doubled."""
    return value.replace("}", "}}")


def build_database_url(*, sqlite_path: Path | None = None) -> str:
    """Resolve SQLAlchemy URL: explicit URL > Azure SQL parts > SQLite file."""
    if sqlite_path is not None:
        return f"sqlite:///{Path(sqlite_path).expanduser().resolve()}"

    cfg = settings()
    if cfg.sqlalchemy_database_url:
        return cfg.sqlalchemy_database_url.strip()

    if cfg.azure_sql_server and cfg.azure_sql_password:
        host = cfg.azure_sql_server.strip()
        if host.lower().startswith("tcp:"):
            host = host[4:]
        host = host.split(",")[0]
        user = cfg.azure_sql_user
        password = cfg.azure_sql_password
        database = cfg.azure_sql_database
        dialect = (cfg.azure_sql_dialect or "pyodbc").strip().lower()
        if dialect in {"pyodbc", "odbc"}:
            odbc = (
                f"Driver={{{cfg.azure_sql_odbc_driver}}};"
                f"Server=tcp:{host},1433;"
                f"Database={database};"
                f"Uid={user};"
                f"Pwd={{{_odbc_escape(password)}}};"
                "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
            )
            return f"mssql+pyodbc:///?odbc_connect={quote_plus(odbc)}"
        return (
            f"mssql+pymssql://{quote_plus(user)}:{quote_plus(password)}"
            f"@{host}:1433/{quote_plus(database)}"
        )

    return f"sqlite:///{cfg.sqlite_database_path}"


def engine_uses_mssql(url: str | None = None) -> bool:
    raw = url or build_database_url()
    return make_url(raw).get_backend_name() in {"mssql"}


def get_engine(*, sqlite_path: Path | None = None) -> Engine:
    url = build_database_url(sqlite_path=sqlite_path)
    cached = _engine_cache.get(url)
    if cached is not None:
        return cached
    kwargs: dict = {"future": True, "pool_pre_ping": True}
    if url.startswith("sqlite:///"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["pool_recycle"] = 1800
        if url.startswith("mssql+pyodbc"):
            # Avoid empty VARCHAR(MAX) binds in Azure Portal / pyodbc.
            kwargs["use_setinputsizes"] = False
    engine = create_engine(url, **kwargs)
    _engine_cache[url] = engine
    return engine


def get_session_factory(*, sqlite_path: Path | None = None) -> sessionmaker[Session]:
    url = build_database_url(sqlite_path=sqlite_path)
    cached = _session_cache.get(url)
    if cached is not None:
        return cached
    factory = sessionmaker(
        bind=get_engine(sqlite_path=sqlite_path),
        autoflush=False,
        expire_on_commit=False,
        future=True,
    )
    _session_cache[url] = factory
    return factory


def ensure_schema(*, sqlite_path: Path | None = None) -> None:
    """Create only the tables this MCP owns; ip_api owns the document tables."""
    from voice_enable_mcp.storage.models import (
        Base,
        CallLog,
        LgCheckpoint,
        LgCheckpointBlob,
        LgCheckpointWrite,
        VoiceContract,
    )

    engine = get_engine(sqlite_path=sqlite_path)
    Base.metadata.create_all(
        engine,
        tables=[
            VoiceContract.__table__,
            CallLog.__table__,
            LgCheckpoint.__table__,
            LgCheckpointBlob.__table__,
            LgCheckpointWrite.__table__,
        ],
    )


def reset_engines() -> None:
    """Drop cached engines (tests / reload_settings)."""
    for engine in _engine_cache.values():
        engine.dispose()
    _engine_cache.clear()
    _session_cache.clear()
