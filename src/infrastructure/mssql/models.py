"""SQLAlchemy mapping of :class:`~domain.ticker_snapshot.TickerSnapshot` onto ``stocko.TickerSnapshots``.

The table is owned by an EF Core migration; the columns below mirror its DDL. The
dataclass field names equal the column names, so the imperative mapping needs no
renaming. Importing this module maps :class:`TickerSnapshot` process-wide.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    Float,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    Table,
    Unicode,
)
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import registry
from sqlalchemy.types import TypeDecorator

from domain.ticker_snapshot import TickerSnapshot

# Sentinel the CSV cache uses for "no date" (see ``infrastructure.csv.io``).
_NO_DATE = date(1900, 1, 1)


class EpochSeconds(TypeDecorator[datetime]):
    """``datetime`` in Python, Unix epoch seconds (``bigint``) in the database."""

    impl = BigInteger
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> int | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            dt = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
            return int(dt.timestamp())
        return int(value)

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return datetime.fromtimestamp(int(value), tz=UTC)


class SentinelNullDate(TypeDecorator[date]):
    """Nullable ``date`` column: NULL in the database is :data:`_NO_DATE` in Python."""

    impl = Date
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> date | None:
        if not isinstance(value, date) or value == _NO_DATE:
            return None
        return value

    def process_result_value(self, value: Any, dialect: Dialect) -> date:
        return _NO_DATE if value is None else value


mapper_registry = registry()

ticker_snapshots = Table(
    "TickerSnapshots",
    mapper_registry.metadata,
    Column("SnapshotDate", Date, nullable=False),
    Column("Symbol", Unicode(10), nullable=False),
    Column("SectorKey", Unicode(255), nullable=False),
    Column("IndustryKey", Unicode(255), nullable=False),
    Column("Industry", Unicode(255), nullable=False),
    Column("Sector", Unicode(255), nullable=False),
    Column("ExDividendDate", SentinelNullDate, nullable=True),
    Column("LastDividendDate", Date, nullable=False),
    Column("LongName", Unicode(255), nullable=False),
    Column("RegularMarketPrice", Numeric(19, 4), nullable=False),
    Column("RegularMarketTime", EpochSeconds, nullable=False),
    Column("DividendRate", Numeric(19, 4), nullable=False),
    Column("DividendYield", Float, nullable=False),
    Column("MarketCap", BigInteger, nullable=False),
    Column("PayoutRatio", Float, nullable=False),
    Column("HeldPercentInsiders", Float, nullable=False),
    Column("HeldPercentInstitutions", Float, nullable=False),
    Column("QuoteType", Unicode(255), nullable=False),
    Column("TypeDisp", Unicode(255), nullable=False),
    Column("LastDividendDecrease", Date, nullable=False),
    Column("YearsSinceDividendDecrease", Integer, nullable=False),
    Column("YearsConsecutiveDividendIncrease", Integer, nullable=False),
    Column("TtmDivs", Numeric(19, 4), nullable=False),
    PrimaryKeyConstraint("Symbol", "SnapshotDate", name="PK_TickerSnapshots"),
    schema="stocko",
)

mapper_registry.map_imperatively(TickerSnapshot, ticker_snapshots)
