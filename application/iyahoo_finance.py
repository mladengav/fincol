"""Protocol for Yahoo Finance snapshot loading (implementation lives in :mod:`infrastructure.yfinance_client`)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from infrastructure.yfinance_client import TickerSnapshot


class IYahooFinance(Protocol):
    """Structural contract for Yahoo Finance data access (yfinance-backed)."""

    def load_ticker(self, symbol: str) -> TickerSnapshot:
        """Create a yfinance ticker and date window; ``hist``/``divs`` are empty until loaded."""
        ...
