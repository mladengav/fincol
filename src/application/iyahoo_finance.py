"""Protocol for Yahoo Finance snapshot loading (:class:`~infrastructure.yfinance_client.YahooFinance`)."""

from __future__ import annotations

from datetime import date
from typing import Protocol

import pandas as pd

from domain.ticker_snapshot import TickerSnapshot


class IYahooFinance(Protocol):
    """Structural contract for Yahoo Finance data access (yfinance-backed)."""

    def load_ticker_info(self, symbol: str) -> TickerSnapshot:
        """Create a yfinance ticker snapshot"""
        ...

    def load_ticker_dividends(self, symbol: str) -> pd.Series:
        """Fetch ex-dividend series from the bound ticker."""
        ...

    def load_ticker_history(self, symbol: str) -> pd.DataFrame:
        """Fetch event history from the bound ticker."""
        ...

    def dividend_sum_after_ex_date(
        self, symbols: list[str], ex_date: date
    ) -> dict[str, float]:
        """Per-symbol sum of Yahoo ``Dividends`` from the calendar day after ``ex_date`` through the latest bar."""
        ...
