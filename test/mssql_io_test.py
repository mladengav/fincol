"""Tests for :class:`infrastructure.mssql.MsSqlFincolIo` against SQL Server.

Backed by the session-scoped SQL Server testcontainer in ``conftest.py`` (schema
created from ``test/sql/Initial.sql``); skipped when Docker is unavailable.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from sqlalchemy import Engine, create_engine, event, text

from application.aggregation_updater import AggregationUpdater
from constants import BCE_TO, TESTCACHE_DIR, TESTCACHE_DIVIDEND_HISTORY_CSV
from domain.fincol_io import IFincolIo
from domain.ticker_snapshot import TickerSnapshot
from infrastructure.csv import CsvFincolIo
from infrastructure.errors import AggregationLockError, SchemaVersionMismatchError
from infrastructure.mssql import MsSqlFincolIo

RY_TO = "RY.TO"
_AGGREGATION_COLUMNS = [
    "TtmDivs",
    "LastDividendDecrease",
    "YearsSinceDividendDecrease",
    "YearsConsecutiveDividendIncrease",
]


@contextmanager
def _captured_sql(fincol_io: MsSqlFincolIo) -> Iterator[list[str]]:
    """Collect the SQL statements ``fincol_io`` sends to the database inside the block."""
    statements: list[str] = []

    def record(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        statements.append(statement)

    engine = fincol_io._engine
    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


@pytest.fixture(scope="module")
def db_engine(testcontainers_mssql_url: str) -> Iterator[Engine]:
    """Raw engine for seeding and inspecting the test database."""
    engine = create_engine(testcontainers_mssql_url)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_db(db_engine: Engine) -> Iterator[None]:
    """Leave an empty table and only the ``Initial`` migration after each test."""
    yield
    with db_engine.begin() as conn:
        conn.execute(text("DELETE FROM [stocko].[TickerSnapshots]"))
        conn.execute(
            text(
                "DELETE FROM [dbo].[__EFMigrationsHistory] WHERE [MigrationId] <> :id"
            ),
            {"id": TickerSnapshot.__ef_schema_version__},
        )


@pytest.fixture
def mssql_io(testcontainers_mssql_url: str, tmp_path: Path) -> Iterator[MsSqlFincolIo]:
    fincol_io = MsSqlFincolIo(testcontainers_mssql_url, csv_io=CsvFincolIo(tmp_path))
    yield fincol_io
    fincol_io.close()


def _seed_snapshots() -> list[TickerSnapshot]:
    """RY.TO and BCE.TO from ``testcache/tickers.csv`` (camelCase header)."""
    return CsvFincolIo(TESTCACHE_DIR).read_cached_tickers([RY_TO, BCE_TO])


def _snapshot(symbol: str) -> TickerSnapshot:
    return next(s for s in _seed_snapshots() if s.Symbol == symbol)


def _row_count(db_engine: Engine, symbol: str) -> int:
    with db_engine.connect() as conn:
        return int(
            conn.execute(
                text(
                    "SELECT COUNT(*) FROM [stocko].[TickerSnapshots] WHERE [Symbol] = :s"
                ),
                {"s": symbol},
            ).scalar_one()
        )


def test_schema_version_matches_initial_migration(mssql_io: MsSqlFincolIo) -> None:
    """Construction succeeds against the ``Initial.sql`` schema."""
    assert isinstance(mssql_io, IFincolIo)


def test_schema_version_mismatch_is_refused(
    testcontainers_mssql_url: str, db_engine: Engine, tmp_path: Path
) -> None:
    """A newer EF migration in the database than TickerSnapshot expects is refused."""
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO [dbo].[__EFMigrationsHistory] "
                "([MigrationId], [ProductVersion]) VALUES (:id, '10.0.12')"
            ),
            {"id": "20991231000000_Future"},
        )

    with pytest.raises(SchemaVersionMismatchError, match="20991231000000_Future"):
        MsSqlFincolIo(testcontainers_mssql_url, csv_io=CsvFincolIo(tmp_path))


def test_tickers_round_trip(mssql_io: MsSqlFincolIo) -> None:
    """Snapshots written to SQL read back equal to the originals."""
    seed = _seed_snapshots()
    mssql_io.write_tickers_to_cache(seed)

    loaded = mssql_io.read_cached_tickers([RY_TO, BCE_TO])

    by_symbol = {s.Symbol: s for s in seed}
    assert [s.Symbol for s in loaded] == sorted(by_symbol)
    for snap in loaded:
        assert snap == by_symbol[snap.Symbol]


def test_write_tickers_upserts_by_symbol_and_date(
    mssql_io: MsSqlFincolIo, db_engine: Engine
) -> None:
    """Rewriting the same (Symbol, SnapshotDate) updates the row instead of adding one."""
    ry = _snapshot(RY_TO)
    mssql_io.write_tickers_to_cache([ry])
    mssql_io.write_tickers_to_cache([replace(ry, LongName="Renamed Bank")])

    assert _row_count(db_engine, RY_TO) == 1
    assert mssql_io.read_cached_tickers([RY_TO])[0].LongName == "Renamed Bank"


def _bce_dividends_by_year() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"symbol": BCE_TO, "year": 2024, "dividend": 3.99},
            {"symbol": BCE_TO, "year": 2025, "dividend": 2.92},
        ]
    )


def test_commit_updates_latest_snapshot_and_prunes_older(
    mssql_io: MsSqlFincolIo, db_engine: Engine, tmp_path: Path
) -> None:
    """Commit writes the snapshots' aggregations to their row, deletes older snapshots
    of the ticker, and sends dividends by year to the CSV delegate."""
    newer = _snapshot(BCE_TO)
    mssql_io.write_tickers_to_cache(
        [replace(newer, SnapshotDate=date(2026, 1, 2)), newer]
    )
    assert _row_count(db_engine, BCE_TO) == 2

    mssql_io.begin_aggregation_updates()
    (snap,) = mssql_io.read_cached_tickers([BCE_TO])
    snap.TtmDivs = Decimal("1.75")
    snap.YearsSinceDividendDecrease = 3
    mssql_io.commit_aggregation_updates([snap], _bce_dividends_by_year())
    mssql_io.finish_aggregation_updates()

    assert _row_count(db_engine, BCE_TO) == 1
    (remaining,) = mssql_io.read_cached_tickers([BCE_TO])
    assert remaining.SnapshotDate == newer.SnapshotDate
    assert remaining.TtmDivs == Decimal("1.75")
    assert mssql_io.read_years_since_dividend_decrease() == {BCE_TO: 3}
    by_year = CsvFincolIo(tmp_path).read_dividends_by_year()
    assert list(by_year["year"]) == [2024, 2025]


def test_commit_is_one_transaction_with_one_update_per_ticker(
    mssql_io: MsSqlFincolIo,
) -> None:
    """Commit sends one UPDATE per ticker, each setting every aggregation column,
    inside a single transaction."""
    mssql_io.write_tickers_to_cache(_seed_snapshots())
    mssql_io.begin_aggregation_updates()
    snapshots = mssql_io.read_cached_tickers([BCE_TO, RY_TO])
    by_symbol = {s.Symbol: s for s in snapshots}
    by_symbol[BCE_TO].TtmDivs = Decimal("1.75")
    by_symbol[BCE_TO].LastDividendDecrease = date(2025, 6, 16)
    by_symbol[RY_TO].TtmDivs = Decimal("6.2")

    commits: list[object] = []

    def record_commit(conn: Any) -> None:
        commits.append(conn)

    event.listen(mssql_io._engine, "commit", record_commit)
    try:
        with _captured_sql(mssql_io) as commit_sql:
            mssql_io.commit_aggregation_updates(snapshots, _bce_dividends_by_year())
    finally:
        event.remove(mssql_io._engine, "commit", record_commit)
    mssql_io.finish_aggregation_updates()

    updates = [s for s in commit_sql if s.lstrip().upper().startswith("UPDATE")]
    assert len(updates) == 2
    for stmt in updates:
        for column in _AGGREGATION_COLUMNS:
            assert f"[{column}]" in stmt, f"{column} missing from: {stmt}"
    assert len(commits) == 1, "all updates must share one transaction"

    loaded = {s.Symbol: s for s in mssql_io.read_cached_tickers([BCE_TO, RY_TO])}
    assert loaded[BCE_TO].TtmDivs == Decimal("1.75")
    assert loaded[BCE_TO].LastDividendDecrease == date(2025, 6, 16)
    assert loaded[RY_TO].TtmDivs == Decimal("6.2")


def test_commit_requires_lock(mssql_io: MsSqlFincolIo) -> None:
    """Commit is refused unless this instance holds the applock."""
    with pytest.raises(AggregationLockError):
        mssql_io.commit_aggregation_updates([], _bce_dividends_by_year())


def test_direct_aggregation_write_targets_latest_snapshot(
    mssql_io: MsSqlFincolIo, caplog: pytest.LogCaptureFixture
) -> None:
    """The IFincolIo write_* methods still work, skipping tickers without a snapshot."""
    mssql_io.write_tickers_to_cache([_snapshot(BCE_TO)])
    mssql_io.begin_aggregation_updates()
    with caplog.at_level(logging.WARNING):
        mssql_io.write_ttm_income({BCE_TO: 1.75, "NOPE.TO": 9.0})
    mssql_io.finish_aggregation_updates()

    assert mssql_io.read_ttm_income() == {BCE_TO: 1.75}
    assert "NOPE.TO" in caplog.text


def test_aggregation_write_requires_lock(mssql_io: MsSqlFincolIo) -> None:
    """Aggregation writes are refused unless this instance holds the applock."""
    with pytest.raises(AggregationLockError):
        mssql_io.write_ttm_income({BCE_TO: 1.0})


def test_second_instance_cannot_begin_while_applock_held(
    mssql_io: MsSqlFincolIo, testcontainers_mssql_url: str, tmp_path: Path
) -> None:
    """The SQL applock refuses a second writer, even with a separate CSV cache."""
    other = MsSqlFincolIo(
        testcontainers_mssql_url, csv_io=CsvFincolIo(tmp_path / "other")
    )
    try:
        mssql_io.begin_aggregation_updates()
        with pytest.raises(AggregationLockError, match="sp_getapplock"):
            other.begin_aggregation_updates()

        mssql_io.finish_aggregation_updates()
        other.begin_aggregation_updates()
        other.finish_aggregation_updates()
    finally:
        other.close()


def test_update_aggregations_end_to_end(
    mssql_io: MsSqlFincolIo, tmp_path: Path
) -> None:
    """AggregationUpdater writes per-ticker aggregations to SQL and the rest to CSV."""
    mssql_io.write_tickers_to_cache([_snapshot(BCE_TO)])
    div_hist = pd.read_csv(TESTCACHE_DIVIDEND_HISTORY_CSV)
    mssql_io.write_dividend_history(
        div_hist.loc[div_hist["ticker"] == BCE_TO, ["ticker", "date", "amount"]]
    )

    AggregationUpdater(mssql_io).update_aggregations([BCE_TO])

    assert mssql_io.read_last_dividend_decrease()[BCE_TO] == date(2025, 6, 16)
    assert mssql_io.read_years_consecutive_dividend_increase()[BCE_TO] == 0
    assert BCE_TO in mssql_io.read_ttm_income()
    assert (tmp_path / "aggregations" / "dividends_by_year.csv").is_file()

    mssql_io.begin_aggregation_updates()
    mssql_io.finish_aggregation_updates()
