"""Direct yfinance access: progressive load (ticker -> dividends -> history as needed)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import yfinance as yf

from domain.iticker_snapshot import ITickerSnapshot


@dataclass
class TickerSnapshot:
    """Live bundle built by :meth:`YahooFinance.load_ticker` and follow-up loaders; implements :class:`ITickerSnapshot`."""

    snapshotDate: date
    symbol: str
    sectorKey: str
    industryKey: str
    exDividendDateUtc: date
    ticker: yf.Ticker = field(repr=False)
    hist: pd.DataFrame = field(default_factory=pd.DataFrame)
    divs: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))

    def with_dividends(self) -> TickerSnapshot:
        """Populate ``TickerSnapshot.divs`` from the bound ticker (ex-dividend series)."""
        self.divs = self.ticker.dividends
        return self

    def with_history(self) -> TickerSnapshot:
        """Load price history when implemented; until then ``hist`` stays empty."""
        return self


class YahooFinance:
    """Yahoo Finance client backed by ``yfinance``; implements :class:`~application.iyahoo_finance.IYahooFinance`."""

    def load_ticker(self, symbol: str) -> TickerSnapshot:
        """Create a yfinance :class:`yf.Ticker` and date window; ``hist``/``divs`` are empty until loaded."""
        end = datetime.now(UTC).date() - timedelta(days=1)  # end = yesterday
        return TickerSnapshot(
            snapshotDate=end,
            symbol=symbol,
            sectorKey="",
            industryKey="",
            exDividendDateUtc=end,
            ticker=yf.Ticker(symbol),
        )

    def load_ticker_with_dividends(self, symbol: str) -> TickerSnapshot:
        """Create a yfinance :class:`yf.Ticker` and date window; Dividends are loaded."""
        return self.load_ticker(symbol).with_dividends()

    def load_tickers(self, symbol: str) -> yf.Tickers:
        return yf.Tickers("TD.TO BNS.TO")
