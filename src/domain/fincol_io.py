"""Protocols for symbol inputs and fincol cache persistence."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class ISymbolLoader(Protocol):
    """Source of symbol / position records consumed by CLIs (for example :mod:`fincol`)."""

    def load_symbols(self) -> list[str]: ...

    def load_symbols_with_quantities(self) -> list[tuple[str, float]]: ...


@runtime_checkable
class IFincolIo(Protocol):
    """Read/write the CSV-backed dividend and TTM cache layout used by :mod:`fincol` and tools."""

    def read_ttm_income(self) -> dict[str, float]: ...

    def write_ttm_income(self, ttm_by_ticker: Mapping[str, float]) -> None: ...

    def read_dividend_history(self) -> pd.DataFrame: ...

    def write_dividend_history(self, body: pd.DataFrame) -> None: ...

    def update_dividend_history(self, new_dividends: pd.DataFrame) -> int: ...
