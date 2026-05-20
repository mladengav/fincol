"""Public snapshot surface used by math helpers and Yahoo-backed loaders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

import pandas as pd


@dataclass
class TickerSnapshot():
    """Bundle of symbol, data from Yahoo."""

    snapshotDate: date
    symbol: str
    sectorKey: str
    industryKey: str
    industry: str
    sector: str
    exDividendDate: date
    lastDividendDate: date
    longName: str
    regularMarketPrice: Decimal
    regularMarketTime: datetime
    dividendRate: Decimal
    dividendYield: float
    marketCap: int
    payoutRatio: float
    heldPercentInsiders: float
    heldPercentInstitutions: float
    quoteType: str
    typeDisp: str
