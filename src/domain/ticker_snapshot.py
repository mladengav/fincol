"""Public snapshot surface used by math helpers and Yahoo-backed loaders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

import pandas as pd


@dataclass
class TickerSnapshot:
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

    # TODO remove and use lastDividendValue instead, with yield calculated from price
    # TODO or possibly keep them but treat as announcedDivRate/announcedDivYield
    dividendRate: Decimal
    dividendYield: float

    marketCap: int
    payoutRatio: float
    heldPercentInsiders: float
    heldPercentInstitutions: float
    quoteType: str
    typeDisp: str
