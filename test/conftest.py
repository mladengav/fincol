"""Shared pytest fixtures."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from azure.storage.blob import BlobServiceClient


@pytest.fixture(scope="session")
def azurite_blob_service_client() -> Iterator[BlobServiceClient]:
    """Start an Azurite blob emulator once per session and yield a client to it.

    Skipped when Docker / testcontainers are unavailable so local runs don't hard-fail.
    """
    try:
        from testcontainers.community.azurite import AzuriteContainer
    except ImportError:  # pragma: no cover - dev extra not installed
        pytest.skip("testcontainers[azurite] is not installed")

    try:
        container = AzuriteContainer()
        container.start()
    except Exception as exc:  # pragma: no cover - Docker unavailable / image pull
        pytest.skip(f"Azurite testcontainer unavailable: {exc}")

    try:
        # Pin api_version: the SDK default outruns what the Azurite image supports.
        yield BlobServiceClient.from_connection_string(
            container.get_connection_string(), api_version="2025-01-05"
        )
    finally:
        container.stop()


_INITIAL_SQL = Path(__file__).resolve().parent / "sql" / "Initial.sql"


def _sql_batches(script: str) -> list[str]:
    """Split a T-SQL script into batches on ``GO`` lines, like sqlcmd does."""
    batches = re.split(r"(?im)^\s*GO\s*$", script)
    return [b.strip() for b in batches if b.strip()]


@pytest.fixture(scope="session")
def mssql_url() -> Iterator[str]:
    """Start SQL Server once per session, create ``fincol_test`` from ``Initial.sql``.

    Yields the SQLAlchemy URL of that database. Skipped when Docker / testcontainers
    / pymssql are unavailable so local runs don't hard-fail.
    """
    try:
        import pymssql  # noqa: F401
        from sqlalchemy import create_engine
        from sqlalchemy.engine import make_url
        from testcontainers.community.mssql import SqlServerContainer
    except ImportError as exc:  # pragma: no cover - dev extra not installed
        pytest.skip(f"SQL Server test dependencies are not installed: {exc}")

    try:
        container = SqlServerContainer("mcr.microsoft.com/mssql/server:2022-latest")
        container.start()
    except Exception as exc:  # pragma: no cover - Docker unavailable / image pull
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

        yield db_url.render_as_string(hide_password=False)
    finally:
        container.stop()
