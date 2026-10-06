"""Tests for composition-root helpers in :mod:`presentation_cli.fincol`."""

from __future__ import annotations

import os

import pytest
from pytest_mock import MockerFixture

from presentation_cli import fincol


@pytest.fixture(autouse=True)
def _no_dotenv(mocker: MockerFixture) -> None:
    """Keep a developer's real ``.env`` from leaking into the environment."""
    mocker.patch.object(fincol, "load_dotenv")


def test_mssql_conn_str_reads_environment(mocker: MockerFixture) -> None:
    url = "mssql+pymssql://u:p@h:1433/db"
    mocker.patch.dict(os.environ, {"MSSQL_CONN_STR": url})

    assert fincol._mssql_conn_str() == url


def test_mssql_conn_str_missing_exits_with_hint(mocker: MockerFixture) -> None:
    mocker.patch.dict(os.environ, clear=True)

    with pytest.raises(SystemExit, match=r"MSSQL_CONN_STR is not set.*\.env\.sample"):
        fincol._mssql_conn_str()
