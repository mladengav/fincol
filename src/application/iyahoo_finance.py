"""Protocol for Yahoo Finance snapshot loading (:class:`~infrastructure.yfinance_client.YahooFinance`)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from domain.iticker_snapshot import ITickerSnapshot


class IYahooFinance(Protocol):
    """Structural contract for Yahoo Finance data access (yfinance-backed)."""

    def load_ticker(self, symbol: str) -> ITickerSnapshot:
        """Create a yfinance ticker and date window; ``hist``/``divs`` are empty (no dividends loaded)."""
        ...

    def load_ticker_with_dividends(self, symbol: str) -> ITickerSnapshot:
        """Create a yfinance ticker and date window; Dividends are loaded."""
        ...