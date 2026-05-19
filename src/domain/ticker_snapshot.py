"""Public snapshot surface used by math helpers and Yahoo-backed loaders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pandas as pd


@dataclass
class TickerSnapshot():
    """Bundle of symbol, date window, price history, and dividend series from Yahoo."""

    snapshotDate: date
    symbol: str
    sectorKey: str
    industryKey: str
    exDividendDateUtc: date
    longName: str
    currentPrice: Decimal
    dividendRate: Decimal
    dividendYield: float
    marketCap: int
    payoutRatio: float
