"""Public snapshot surface used by math helpers and Yahoo-backed loaders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass
class TickerSnapshot:
    """Bundle of symbol, data from Yahoo."""

    __ef_schema_version__ = "20261002162314_Initial"

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

    # Aggregations:  TODO separate Yahoo-populated columns into a separate object

    lastDividendDecrease: date
    yearsSinceDividendDecrease: int
    yearsConsecutiveDividendIncrease: int
    ttmDivs: Decimal
