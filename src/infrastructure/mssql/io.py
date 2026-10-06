"""SQL Server-backed :class:`~domain.fincol_io.IFincolIo` (:class:`MsSqlFincolIo`)."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd
from sqlalchemy import (
    Connection,
    and_,
    create_engine,
    delete,
    func,
    select,
    text,
    update,
)
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import sessionmaker

from domain.fincol_io import IFincolIo
from domain.ticker_snapshot import TickerSnapshot
from infrastructure.csv.io import CsvFincolIo
from infrastructure.errors import AggregationLockError, SchemaVersionMismatchError
from infrastructure.mssql.models import ticker_snapshots

logger = logging.getLogger(__name__)

_SCHEMA_VERSION_SQL = text(
    "SELECT TOP 1 [MigrationId], [ProductVersion] "
    "FROM [dbo].[__EFMigrationsHistory] ORDER BY [MigrationId] DESC;"
)
_APPLOCK_RESOURCE = "fincol_aggregations"
_GET_APPLOCK_SQL = text(
    "SET NOCOUNT ON; DECLARE @r int; "
    "EXEC @r = sp_getapplock @Resource = :resource, @LockMode = 'Exclusive', "
    "@LockOwner = 'Session', @LockTimeout = 0; SELECT @r;"
)
_RELEASE_APPLOCK_SQL = text(
    "EXEC sp_releaseapplock @Resource = :resource, @LockOwner = 'Session';"
)
# Aggregation columns, all set by one UPDATE per ticker.
_AGGREGATION_COLUMNS = (
    "TtmDivs",
    "LastDividendDecrease",
    "YearsSinceDividendDecrease",
    "YearsConsecutiveDividendIncrease",
)


class MsSqlFincolIo(IFincolIo):
    """IFincolIo backed by the ``stocko.TickerSnapshots`` table in SQL Server.

    Ticker snapshots and the per-ticker aggregations live in SQL; dividend history
    and dividends-by-year have no table and are delegated to ``csv_io``. On
    construction the latest EF migration in the database must equal
    ``TickerSnapshot.__ef_schema_version__``.

    :meth:`commit_aggregation_updates` writes a batch of snapshots in one
    transaction, with one UPDATE per ticker setting every aggregation column.
    """

    def __init__(self, conn_str: str, csv_io: CsvFincolIo | None = None) -> None:
        self._engine = create_engine(conn_str)
        self._sessions = sessionmaker(self._engine, expire_on_commit=False)
        self._csv_io = csv_io if csv_io is not None else CsvFincolIo()
        self._lock_conn: Connection | None = None
        try:
            self._verify_schema_version()
        except BaseException:
            self._engine.dispose()
            raise

    def __repr__(self) -> str:
        return f"MsSqlFincolIo({self._engine.url.render_as_string(hide_password=True)})"

    def close(self) -> None:
        """Release any aggregation lock and dispose of the connection pool."""
        self.finish_aggregation_updates()
        self._engine.dispose()

    def _verify_schema_version(self) -> None:
        expected = TickerSnapshot.__ef_schema_version__
        try:
            with self._engine.connect() as conn:
                row = conn.execute(_SCHEMA_VERSION_SQL).first()
        except ProgrammingError as e:
            raise SchemaVersionMismatchError(
                f"{self!r}: cannot read [dbo].[__EFMigrationsHistory]; "
                f"expected migration {expected!r}"
            ) from e
        if row is None:
            raise SchemaVersionMismatchError(
                f"{self!r}: no EF migrations applied; expected {expected!r}"
            )
        migration_id, product_version = row
        if migration_id != expected:
            raise SchemaVersionMismatchError(
                f"{self!r}: database is at migration {migration_id!r} "
                f"(EF {product_version}), but TickerSnapshot expects {expected!r}"
            )
        logger.info(
            "Schema version %s (EF %s) matches TickerSnapshot",
            migration_id,
            product_version,
        )

    # -- Ticker snapshots ----------------------------------------------------

    def read_cached_tickers(self, ticker_symbols: list[str]) -> list[TickerSnapshot]:
        """Return the latest snapshot of each requested symbol that has one."""
        if not ticker_symbols:
            return []
        return self._load_latest_snapshots(set(ticker_symbols))

    def _load_latest_snapshots(
        self, symbols: set[str] | None = None
    ) -> list[TickerSnapshot]:
        """Latest snapshot per symbol, for ``symbols`` or for every symbol if None."""
        t = ticker_snapshots
        latest_query = select(
            t.c.Symbol, func.max(t.c.SnapshotDate).label("SnapshotDate")
        ).group_by(t.c.Symbol)
        if symbols is not None:
            latest_query = latest_query.where(t.c.Symbol.in_(symbols))
        latest = latest_query.subquery()
        stmt = (
            select(TickerSnapshot)
            .join(
                latest,
                and_(
                    t.c.Symbol == latest.c.Symbol,
                    t.c.SnapshotDate == latest.c.SnapshotDate,
                ),
            )
            .order_by(t.c.Symbol)
        )
        with self._sessions() as session:
            return list(session.scalars(stmt))

    def write_tickers_to_cache(self, snapshots: list[TickerSnapshot]) -> None:
        """Upsert ``snapshots`` by ``(Symbol, SnapshotDate)``."""
        if not snapshots:
            return
        with self._sessions.begin() as session:
            for snap in snapshots:
                session.merge(snap)

    # -- Aggregation locking -------------------------------------------------

    def begin_aggregation_updates(self) -> None:
        """Take an exclusive ``sp_getapplock``, then the delegated CSV locks.

        Raises :class:`AggregationLockError` if another writer holds the lock;
        anything acquired before a failure is released first.
        """
        if self._lock_conn is not None:
            raise AggregationLockError(
                f"{self!r}: aggregation updates already in progress"
            )
        conn = self._engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        try:
            result: int = conn.execute(
                _GET_APPLOCK_SQL, {"resource": _APPLOCK_RESOURCE}
            ).scalar_one()
        except BaseException:
            conn.close()
            raise
        if result < 0:
            conn.close()
            raise AggregationLockError(
                f"{self!r}: aggregation lock {_APPLOCK_RESOURCE!r} is held by "
                f"another writer (sp_getapplock returned {result})"
            )
        self._lock_conn = conn
        try:
            self._csv_io.begin_aggregation_updates()
        except BaseException:
            self._release_applock()
            raise

    def commit_aggregation_updates(
        self, snapshots: list[TickerSnapshot], dividends_by_year: pd.DataFrame
    ) -> None:
        """Write the batch: dividends by year to the CSV delegate, then the
        snapshots' aggregation columns in one SQL transaction (one UPDATE per ticker).
        """
        self._require_aggregation_lock()
        self._csv_io.merge_dividends_by_year(
            dividends_by_year, {s.Symbol for s in snapshots}
        )
        self._update_aggregation_columns(snapshots)
        logger.info("Committed aggregations for %d ticker(s)", len(snapshots))

    def finish_aggregation_updates(self) -> None:
        """Release the delegated CSV locks and the applock held by this instance."""
        try:
            self._csv_io.finish_aggregation_updates()
        finally:
            self._release_applock()

    def _release_applock(self) -> None:
        conn = self._lock_conn
        if conn is None:
            return
        self._lock_conn = None
        try:
            conn.execute(_RELEASE_APPLOCK_SQL, {"resource": _APPLOCK_RESOURCE})
        except Exception:
            # Drop the session so the server releases the session-owned lock.
            logger.warning("Could not release aggregation applock", exc_info=True)
            conn.invalidate()
        finally:
            conn.close()

    def _require_aggregation_lock(self) -> None:
        if self._lock_conn is None:
            raise AggregationLockError(
                f"{self!r}: call begin_aggregation_updates() before writing aggregations"
            )

    # -- Per-ticker aggregations (latest snapshot of each symbol) ------------

    def _update_aggregation_columns(self, snapshots: list[TickerSnapshot]) -> None:
        """In one transaction, per snapshot: delete the ticker's older snapshots and
        UPDATE every aggregation column of this one in a single statement."""
        self._require_aggregation_lock()
        if not snapshots:
            return
        t = ticker_snapshots
        with self._engine.begin() as conn:
            for snap in snapshots:
                conn.execute(
                    delete(t).where(
                        t.c.Symbol == snap.Symbol, t.c.SnapshotDate < snap.SnapshotDate
                    )
                )
                result = conn.execute(
                    update(t)
                    .where(
                        t.c.Symbol == snap.Symbol,
                        t.c.SnapshotDate == snap.SnapshotDate,
                    )
                    .values({col: getattr(snap, col) for col in _AGGREGATION_COLUMNS})
                )
                if result.rowcount == 0:
                    logger.warning(
                        "No ticker snapshot %s/%s to update",
                        snap.Symbol,
                        snap.SnapshotDate,
                    )

    def _write_column(self, column: str, values_by_symbol: Mapping[str, Any]) -> None:
        """Set ``column`` on each symbol's latest snapshot and write it back."""
        self._require_aggregation_lock()
        snapshots = self.read_cached_tickers(list(values_by_symbol))
        for snap in snapshots:
            setattr(snap, column, values_by_symbol[snap.Symbol])
        skipped = sorted(set(values_by_symbol) - {s.Symbol for s in snapshots})
        if skipped:
            logger.warning("No ticker snapshot to update %s for: %s", column, skipped)
        self._update_aggregation_columns(snapshots)

    def _read_latest_snapshots(self, column: str) -> dict[str, Any]:
        """Return ``{Symbol: column}`` from each symbol's latest snapshot."""
        t = ticker_snapshots
        latest = (
            select(t.c.Symbol, func.max(t.c.SnapshotDate).label("SnapshotDate"))
            .group_by(t.c.Symbol)
            .subquery()
        )
        stmt = select(t.c.Symbol, t.c[column]).join(
            latest,
            and_(
                t.c.Symbol == latest.c.Symbol,
                t.c.SnapshotDate == latest.c.SnapshotDate,
            ),
        )
        with self._engine.connect() as conn:
            return {str(symbol): value for symbol, value in conn.execute(stmt)}

    def read_ttm_income(self) -> dict[str, float]:
        return {
            sym: float(v) for sym, v in self._read_latest_snapshots("TtmDivs").items()
        }

    def write_ttm_income(self, ttm_by_ticker: Mapping[str, float]) -> None:
        self._write_column(
            "TtmDivs",
            {sym: Decimal(f"{float(v):.4f}") for sym, v in ttm_by_ticker.items()},
        )

    def read_last_dividend_decrease(self) -> dict[str, date]:
        return self._read_latest_snapshots("LastDividendDecrease")

    def write_last_dividend_decrease(
        self, last_decrease_by_ticker: Mapping[str, date]
    ) -> None:
        self._write_column("LastDividendDecrease", last_decrease_by_ticker)

    def read_years_since_dividend_decrease(self) -> dict[str, int]:
        return {
            sym: int(v)
            for sym, v in self._read_latest_snapshots(
                "YearsSinceDividendDecrease"
            ).items()
        }

    def write_years_since_dividend_decrease(
        self, years_since_by_ticker: Mapping[str, int]
    ) -> None:
        self._write_column(
            "YearsSinceDividendDecrease",
            {sym: int(v) for sym, v in years_since_by_ticker.items()},
        )

    def read_years_consecutive_dividend_increase(self) -> dict[str, int]:
        return {
            sym: int(v)
            for sym, v in self._read_latest_snapshots(
                "YearsConsecutiveDividendIncrease"
            ).items()
        }

    def write_years_consecutive_dividend_increase(
        self, years_consecutive_by_ticker: Mapping[str, int]
    ) -> None:
        self._write_column(
            "YearsConsecutiveDividendIncrease",
            {sym: int(v) for sym, v in years_consecutive_by_ticker.items()},
        )

    # -- Delegated to the CSV cache (no SQL table) ---------------------------

    def read_dividends_by_year(self) -> pd.DataFrame:
        return self._csv_io.read_dividends_by_year()

    def write_dividends_by_year(self, dividends_by_year: pd.DataFrame) -> None:
        self._csv_io.write_dividends_by_year(dividends_by_year)

    def read_dividend_history(self) -> pd.DataFrame:
        return self._csv_io.read_dividend_history()

    def write_dividend_history(self, body: pd.DataFrame) -> None:
        self._csv_io.write_dividend_history(body)

    def update_dividend_history(self, new_dividends: pd.DataFrame) -> int:
        return self._csv_io.update_dividend_history(new_dividends)
