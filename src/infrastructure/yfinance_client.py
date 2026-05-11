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

    symbol: str
    history_start: date
    end: date
    ticker: yf.Ticker = field(repr=False)
    hist: pd.DataFrame = field(default_factory=pd.DataFrame)
    divs: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))

    def with_dividends(self) -> ITickerSnapshot:
        """Populate ``TickerSnapshot.divs`` from the bound ticker (ex-dividend series)."""
        self.divs = self.ticker.dividends
        return self

    def with_history(self) -> ITickerSnapshot:
        """Populate ``TickerSnapshot.hist`` for the snapshot's date window (daily bars, ``auto_adjust=False``)."""
        self.hist = self.ticker.history(
            start=self.history_start.isoformat(),
            end=(self.end + timedelta(days=1)).isoformat(),
            interval="1d",
            auto_adjust=False,
        )
        return self


class YahooFinance:
    """Yahoo Finance client backed by ``yfinance``; implements :class:`~application.iyahoo_finance.IYahooFinance`."""

    def load_ticker(self, symbol: str) -> TickerSnapshot:
        """Create a yfinance :class:`yf.Ticker` and date window; ``hist``/``divs`` are empty until loaded."""
        end = datetime.now(UTC).date() - timedelta(days=1)  # end = yesterday
        history_start = end - timedelta(days=365)
        return TickerSnapshot(
            symbol=symbol,
            history_start=history_start,
            end=end,
            ticker=yf.Ticker(symbol),
        )
