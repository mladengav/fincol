"""Protocol for Yahoo Finance snapshot loading (:class:`~infrastructure.yfinance_client.YahooFinance`)."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from domain.iticker_snapshot import ITickerSnapshot


class IYahooFinance(Protocol):
    """Structural contract for Yahoo Finance data access (yfinance-backed)."""

    def load_ticker(
        self,
        symbol: str,
        withDividends: bool = False,
        withInfo: bool = False,
    ) -> ITickerSnapshot:
        """Create a yfinance ticker and date window; optional dividend/info loading when flags are true."""
        ...

    def dividend_sum_after_ex_date(self, symbols: list[str], ex_date: date) -> dict[str, float]:
        """Per-symbol sum of Yahoo ``Dividends`` from the calendar day after ``ex_date`` through the latest bar."""
        ...