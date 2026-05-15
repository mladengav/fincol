"""Public snapshot surface used by math helpers and Yahoo-backed loaders."""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class ITickerSnapshot(Protocol):
    """Bundle of symbol, date window, price history, and dividend series from Yahoo."""

    snapshotDate: date
    symbol: str
    sectorKey: str
    industryKey: str
    exDividendDateUtc: date
    hist: pd.DataFrame
    divs: pd.Series

    def get_history(self, history_start: date, end: date) -> ITickerSnapshot: ...
