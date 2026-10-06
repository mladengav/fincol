"""SQL Server testcontainer with the ``fincol_test`` schema, served by ``conftest.py``."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from testcontainers.community.mssql import SqlServerContainer

_INITIAL_SQL = Path(__file__).resolve().parent / "sql" / "Initial.sql"


def _sql_batches(script: str) -> list[str]:
    """Split a T-SQL script into batches on ``GO`` lines, like sqlcmd does."""
    batches = re.split(r"(?im)^\s*GO\s*$", script)
    return [b.strip() for b in batches if b.strip()]


def start_mssql() -> tuple[SqlServerContainer, str]:
    """Start SQL Server, create ``fincol_test`` from ``Initial.sql``.

    Returns ``(container, SQLAlchemy URL of fincol_test)``. Skips when Docker /
    testcontainers / pymssql are unavailable so local runs don't hard-fail.
    """
    try:
        import pymssql  # noqa: F401
        from sqlalchemy import create_engine
        from sqlalchemy.engine import make_url
        from testcontainers.community.mssql import SqlServerContainer

        container = SqlServerContainer("mcr.microsoft.com/mssql/server:2025-latest")
        container.start()
    except Exception as exc:  # pragma: no cover - dev extra / Docker / image pull
        pytest.skip(f"SQL Server testcontainer unavailable: {exc}")

    try:
        server_url = make_url(container.get_connection_url())
        master = create_engine(server_url.set(database="master"))
        with master.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.exec_driver_sql("CREATE DATABASE fincol_test")
        master.dispose()

        db_url = server_url.set(database="fincol_test")
        engine = create_engine(db_url)
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            for batch in _sql_batches(_INITIAL_SQL.read_text(encoding="utf-8")):
                conn.exec_driver_sql(batch)
        engine.dispose()
    except BaseException:
        container.stop()
        raise
    return container, db_url.render_as_string(hide_password=False)
