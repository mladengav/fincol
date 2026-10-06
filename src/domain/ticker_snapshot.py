"""Public snapshot surface used by math helpers and Yahoo-backed loaders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass
class TickerSnapshot:
    """Bundle of symbol, data from Yahoo.

    Field names equal the ``stocko.TickerSnapshots`` column names, so the class maps
    onto that table without renaming; ``__ef_schema_version__`` is the EF migration
    the fields correspond to.
    """

    __ef_schema_version__ = "20261002162314_Initial"

    SnapshotDate: date
    Symbol: str
    SectorKey: str
    IndustryKey: str
    Industry: str
    Sector: str
    ExDividendDate: date
    LastDividendDate: date
    LongName: str
    RegularMarketPrice: Decimal
    RegularMarketTime: datetime

    # TODO remove and use lastDividendValue instead, with yield calculated from price
    # TODO or possibly keep them but treat as announcedDivRate/announcedDivYield
    DividendRate: Decimal
    DividendYield: float

    MarketCap: int
    PayoutRatio: float
    HeldPercentInsiders: float
    HeldPercentInstitutions: float
    QuoteType: str
    TypeDisp: str

    # Aggregations:  TODO separate Yahoo-populated columns into a separate object

    LastDividendDecrease: date
    YearsSinceDividendDecrease: int
    YearsConsecutiveDividendIncrease: int
    TtmDivs: Decimal
