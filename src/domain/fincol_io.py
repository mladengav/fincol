"""Protocols for symbol inputs and fincol cache persistence."""

from __future__ import annotations

from collections.abc import Mapping
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

    def read_cached_tickers(self, ticker_symbols: list[str]) -> list[TickerSnapshot]: ...

    def write_tickers_to_cache(self, snapshots: list[TickerSnapshot]) -> None: ...

    def read_ttm_income(self) -> dict[str, float]: ...

    def write_ttm_income(self, ttm_by_ticker: Mapping[str, float]) -> None: ...

    def read_last_dividend_decrease(self) -> dict[str, date]: ...

    def write_last_dividend_decrease(
        self, last_decrease_by_ticker: Mapping[str, date]
    ) -> None: ...

    def read_dividend_history(self) -> pd.DataFrame: ...

    def write_dividend_history(self, body: pd.DataFrame) -> None: ...

    def update_dividend_history(self, new_dividends: pd.DataFrame) -> int: ...
