"""Direct yfinance access: progressive load (ticker -> dividends -> history as needed)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import yfinance as yf


@dataclass
class TickerSnapshot:
    """Live bundle built by :func:`load_ticker` and follow-up loaders."""

    symbol: str
    history_start: date
    end: date
    ticker: yf.Ticker = field(repr=False)
    hist: pd.DataFrame = field(default_factory=pd.DataFrame)
    divs: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))


def load_ticker(symbol: str) -> TickerSnapshot:
    """Create a yfinance :class:`yf.Ticker` and date window; ``hist``/``divs`` are empty until loaded."""
    end = datetime.now(UTC).date() - timedelta(days=1)  # end = yesterday
    history_start = end - timedelta(days=365)
    return TickerSnapshot(
        symbol=symbol,
        history_start=history_start,
        end=end,
        ticker=yf.Ticker(symbol),
    )


def load_ticker_dividends(snapshot: TickerSnapshot) -> None:
    """Populate ``snapshot.divs`` from the bound ticker (ex-dividend series)."""
    snapshot.divs = snapshot.ticker.dividends


def load_ticker_history(snapshot: TickerSnapshot) -> None:
    """Populate ``snapshot.hist`` for the snapshot's date window (daily bars, ``auto_adjust=False``)."""
    snapshot.hist = snapshot.ticker.history(
        start=snapshot.history_start.isoformat(),
        end=(snapshot.end + timedelta(days=1)).isoformat(),
        interval="1d",
        auto_adjust=False,
    )
