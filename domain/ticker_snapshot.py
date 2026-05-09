"""Public snapshot surface used by domain math and loaders."""
from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class ITickerSnapshot(Protocol):
    """Public snapshot surface used by domain math and loaders."""

    symbol: str
    history_start: date
    end: date
    hist: pd.DataFrame
    divs: pd.Series

    def with_dividends(self) -> ITickerSnapshot: ...

    def with_history(self) -> ITickerSnapshot: ...
