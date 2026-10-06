"""Protocols for symbol inputs and fincol cache persistence."""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

import pandas as pd

from domain.ticker_snapshot import TickerSnapshot


@runtime_checkable
class ISymbolLoader(Protocol):
    """Source of symbol / position records consumed by CLIs (for example :mod:`fincol`)."""

    def load_symbols(self) -> list[str]: ...

    def load_symbols_with_quantities(self) -> list[tuple[str, float]]: ...


@runtime_checkable
class IFincolIo(Protocol):
    """Read/write the CSV-backed dividend and TTM cache layout used by :mod:`fincol` and tools."""

    def read_cached_tickers(
        self, ticker_symbols: list[str]
    ) -> list[TickerSnapshot]: ...

    def write_tickers_to_cache(self, snapshots: list[TickerSnapshot]) -> None: ...

    def begin_aggregation_updates(self) -> None:
        """Mark the start of a batch of aggregation writes.

        Implementations may prepare for the writes here (for example by taking
        exclusive locks). If this raises, the implementation must not be left holding anything.
        """
        ...

    def commit_aggregation_updates(
        self, snapshots: list[TickerSnapshot], dividends_by_year: pd.DataFrame
    ) -> None:
        """Persist a batch of recomputed aggregations.

        ``snapshots`` carry the per-ticker aggregation fields; ``dividends_by_year`` holds the
        yearly dividends for those tickers. Aggregations of
        tickers outside the batch are left unchanged. Called once between ``begin``
        and ``finish``, and only when every aggregation step succeeded.
        """
        ...

    def finish_aggregation_updates(self) -> None:
        """Mark the end of a batch of aggregation writes, releasing what ``begin`` set up.

        Must be idempotent (safe without a matching or after a failed ``begin``) and
        should not raise for cleanup failures, so it never masks the batch's error.
        """
        ...

    def read_ttm_income(self) -> dict[str, float]: ...

    # def write_ttm_income(self, ttm_by_ticker: Mapping[str, float]) -> None: ...

    def read_last_dividend_decrease(self) -> dict[str, date]: ...

    # def write_last_dividend_decrease(
    #     self, last_decrease_by_ticker: Mapping[str, date]
    # ) -> None: ...

    def read_years_since_dividend_decrease(self) -> dict[str, int]: ...

    # def write_years_since_dividend_decrease(
    #     self, years_since_by_ticker: Mapping[str, int]
    # ) -> None: ...

    def read_dividends_by_year(self) -> pd.DataFrame: ...

    # def write_dividends_by_year(self, dividends_by_year: pd.DataFrame) -> None: ...

    def read_years_consecutive_dividend_increase(self) -> dict[str, int]: ...

    # def write_years_consecutive_dividend_increase(
    #     self, years_consecutive_by_ticker: Mapping[str, int]
    # ) -> None: ...

    def read_dividend_history(self) -> pd.DataFrame: ...

    # def write_dividend_history(self, body: pd.DataFrame) -> None: ...

    def update_dividend_history(self, new_dividends: pd.DataFrame) -> int: ...
