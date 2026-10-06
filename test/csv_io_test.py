"""Tests for :mod:`infrastructure.csv.io` cache readers."""

from __future__ import annotations

import shutil
from dataclasses import fields
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from constants import TESTCACHE_DIR
from domain.ticker_snapshot import TickerSnapshot
from infrastructure.csv import CsvFincolIo
from infrastructure.errors import AggregationLockError

_TICKERS_FIXTURE = TESTCACHE_DIR / "tickers.csv"
_AGGREGATION_LOCK_NAMES = [
    "ttm_income.csv.lock",
    "last_dividend_decrease.csv.lock",
    "years_since_dividend_decrease.csv.lock",
    "dividends_by_year.csv.lock",
    "years_consecutive_dividend_increase.csv.lock",
]


def _aggregation_lock_paths(cache: Path) -> list[Path]:
    return [cache / "aggregations" / name for name in _AGGREGATION_LOCK_NAMES]


def _default_ticker_snapshot(
    SnapshotDate: date,
    Symbol: str,
    SectorKey: str,
    IndustryKey: str,
    ExDividendDate: date,
) -> TickerSnapshot:

    return TickerSnapshot(
        SnapshotDate=SnapshotDate,
        Symbol=Symbol,
        SectorKey=SectorKey,
        IndustryKey=IndustryKey,
        Industry="",
        Sector="",
        ExDividendDate=ExDividendDate,
        LastDividendDate=date(1900, 1, 1),
        LongName="",
        RegularMarketPrice=Decimal("0.00"),
        RegularMarketTime=datetime(1900, 1, 1, tzinfo=UTC),
        DividendRate=Decimal("0.00"),
        DividendYield=0.0,
        MarketCap=0,
        PayoutRatio=0.0,
        HeldPercentInsiders=0.0,
        HeldPercentInstitutions=0.0,
        QuoteType="",
        TypeDisp="",
        LastDividendDecrease=date.min,
        YearsSinceDividendDecrease=-1,
        YearsConsecutiveDividendIncrease=-1,
        TtmDivs=Decimal(0.0),
    )


def test_read_cached_tickers_from_testcache_fixture() -> None:
    """``read_cached_tickers`` maps ``testcache/tickers.csv`` rows onto :class:`~domain.ticker_snapshot.TickerSnapshot` fields."""
    assert _TICKERS_FIXTURE.is_file(), f"missing fixture: {_TICKERS_FIXTURE}"

    fincol_io = CsvFincolIo(TESTCACHE_DIR)
    snapshots = fincol_io.read_cached_tickers(["RY.TO"])

    assert len(snapshots) == 1
    snap = snapshots[0]
    assert snap.Symbol == "RY.TO"
    assert snap.SnapshotDate == date(2026, 5, 19)
    assert snap.SectorKey == "financial-services"
    assert snap.IndustryKey == "banks-diversified"
    assert snap.Industry == "Banks - Diversified"
    assert snap.Sector == "Financial Services"
    assert snap.ExDividendDate == date(2026, 4, 23)
    assert snap.LastDividendDate == date(2026, 4, 23)
    assert snap.LongName == "Royal Bank of Canada"
    assert snap.RegularMarketPrice == Decimal("252.53")
    assert snap.RegularMarketTime == datetime(2026, 5, 19, 20, 00, 00, tzinfo=UTC)
    assert snap.DividendRate == Decimal("6.56")
    assert snap.DividendYield == 2.6
    assert snap.MarketCap == 351370215424
    assert snap.PayoutRatio == 0.42580003
    assert snap.HeldPercentInsiders == pytest.approx(0.00027)
    assert snap.HeldPercentInstitutions == pytest.approx(0.49071997)
    assert snap.QuoteType == "EQUITY"
    assert snap.TypeDisp == "Equity"


def test_write_tickers_to_cache_roundtrip_preserves_header_and_mapped_fields(
    tmp_path: Path,
) -> None:
    """Rewrite fixture-shaped ``tickers.csv``; mapped columns round-trip, extra columns become blank."""
    assert _TICKERS_FIXTURE.is_file(), f"missing fixture: {_TICKERS_FIXTURE}"

    cache = tmp_path / "cache"
    cache.mkdir()
    dest = cache / "tickers.csv"
    shutil.copy(_TICKERS_FIXTURE, dest)

    fincol_io = CsvFincolIo(cache)
    snapshots = fincol_io.read_cached_tickers(["RY.TO"])
    fincol_io.write_tickers_to_cache(snapshots)

    again = fincol_io.read_cached_tickers(["RY.TO"])
    assert len(again) == 1
    s = again[0]
    assert s.Symbol == "RY.TO"
    assert s.SnapshotDate == date(2026, 5, 19)
    assert s.SectorKey == "financial-services"
    assert s.IndustryKey == "banks-diversified"
    assert s.ExDividendDate == date(2026, 4, 23)
    assert s.LongName == "Royal Bank of Canada"
    assert s.RegularMarketPrice == Decimal("252.53")
    assert s.DividendRate == Decimal("6.56")


def test_write_tickers_to_cache_creates_minimal_csv(tmp_path: Path) -> None:
    """When ``tickers.csv`` is missing, write uses default headers and can be read back."""
    cache = tmp_path / "cache"
    io = CsvFincolIo(cache)
    snap = _default_ticker_snapshot(
        SnapshotDate=date(2024, 1, 2),
        Symbol="ZZ.TO",
        SectorKey="sk",
        IndustryKey="ik",
        ExDividendDate=date(2024, 3, 4),
    )
    io.write_tickers_to_cache([snap])

    out = io.read_cached_tickers(["ZZ.TO"])
    assert len(out) == 1
    r = out[0]
    assert r.Symbol == "ZZ.TO"
    assert r.SnapshotDate == date(2024, 1, 2)
    assert r.SectorKey == "sk"
    assert r.IndustryKey == "ik"
    assert r.ExDividendDate == date(2024, 3, 4)


def test_write_tickers_to_cache_merges_new_symbol_without_dropping_existing(
    tmp_path: Path,
) -> None:
    """Writing a second ticker appends; the first row remains."""
    assert _TICKERS_FIXTURE.is_file(), f"missing fixture: {_TICKERS_FIXTURE}"

    cache = tmp_path / "cache"
    cache.mkdir()
    dest = cache / "tickers.csv"
    shutil.copy(_TICKERS_FIXTURE, dest)

    io = CsvFincolIo(cache)
    ry = io.read_cached_tickers(["RY.TO"])[0]
    other = _default_ticker_snapshot(
        SnapshotDate=date(2024, 6, 1),
        Symbol="OTHER.TO",
        SectorKey="x",
        IndustryKey="y",
        ExDividendDate=date(2024, 6, 15),
    )
    io.write_tickers_to_cache([other])

    loaded = io.read_cached_tickers(["RY.TO", "OTHER.TO"])
    by_sym = {s.Symbol: s for s in loaded}
    assert set(by_sym) == {"RY.TO", "OTHER.TO"}
    assert by_sym["RY.TO"].SnapshotDate == ry.SnapshotDate
    assert by_sym["OTHER.TO"].SectorKey == "x"


def test_write_tickers_to_cache_update_one_symbol_leaves_others(tmp_path: Path) -> None:
    """Replacing one Symbol's row does not remove other symbols from the cache."""
    assert _TICKERS_FIXTURE.is_file(), f"missing fixture: {_TICKERS_FIXTURE}"

    cache = tmp_path / "cache"
    cache.mkdir()
    dest = cache / "tickers.csv"
    shutil.copy(_TICKERS_FIXTURE, dest)

    io = CsvFincolIo(cache)
    io.write_tickers_to_cache(
        [
            _default_ticker_snapshot(
                SnapshotDate=date(2024, 6, 1),
                Symbol="OTHER.TO",
                SectorKey="keep-me",
                IndustryKey="y",
                ExDividendDate=date(2024, 6, 15),
            )
        ]
    )
    io.write_tickers_to_cache(
        [
            _default_ticker_snapshot(
                SnapshotDate=date(2025, 1, 1),
                Symbol="RY.TO",
                SectorKey="updated",
                IndustryKey="updated-ik",
                ExDividendDate=date(2025, 2, 2),
            )
        ]
    )

    loaded = io.read_cached_tickers(["RY.TO", "OTHER.TO"])
    by_sym = {s.Symbol: s for s in loaded}
    assert by_sym["OTHER.TO"].SectorKey == "keep-me"
    assert by_sym["RY.TO"].SectorKey == "updated"
    assert by_sym["RY.TO"].IndustryKey == "updated-ik"


def test_begin_aggregation_updates_creates_lock_files(tmp_path: Path) -> None:
    """``begin_aggregation_updates`` creates a ``.lock`` file beside every aggregation CSV."""
    io = CsvFincolIo(tmp_path)
    io.begin_aggregation_updates()

    for lock_path in _aggregation_lock_paths(tmp_path):
        assert lock_path.is_file(), f"expected lock {lock_path}"


def test_second_instance_cannot_begin_while_locked(tmp_path: Path) -> None:
    """A second writer on the same folder is refused while the first holds the locks."""
    holder = CsvFincolIo(tmp_path)
    holder.begin_aggregation_updates()

    with pytest.raises(AggregationLockError):
        CsvFincolIo(tmp_path).begin_aggregation_updates()

    for lock_path in _aggregation_lock_paths(tmp_path):
        assert lock_path.is_file(), f"holder's lock {lock_path} was removed"


def test_finish_aggregation_updates_releases_locks(tmp_path: Path) -> None:
    """After ``finish_aggregation_updates`` the lock files are gone and another writer can lock."""
    io = CsvFincolIo(tmp_path)
    io.begin_aggregation_updates()
    io.finish_aggregation_updates()

    for lock_path in _aggregation_lock_paths(tmp_path):
        assert not lock_path.exists(), f"lock {lock_path} not released"

    other = CsvFincolIo(tmp_path)
    other.begin_aggregation_updates()
    other.finish_aggregation_updates()


def test_begin_failure_releases_partially_acquired_locks(tmp_path: Path) -> None:
    """If one lock is taken, ``begin`` releases the locks it already acquired."""
    *own_locks, foreign_lock = _aggregation_lock_paths(tmp_path)
    foreign_lock.parent.mkdir(parents=True)
    foreign_lock.write_text("someone else", encoding="utf-8")

    with pytest.raises(AggregationLockError, match=foreign_lock.name):
        CsvFincolIo(tmp_path).begin_aggregation_updates()

    for lock_path in own_locks:
        assert not lock_path.exists(), f"partial lock {lock_path} left behind"
    assert foreign_lock.read_text(encoding="utf-8") == "someone else"


def test_aggregation_write_requires_lock(tmp_path: Path) -> None:
    """Aggregation writes are refused unless this instance holds the locks."""
    io = CsvFincolIo(tmp_path)

    with pytest.raises(AggregationLockError):
        io.write_ttm_income({"ZZ.TO": 1.0})

    io.begin_aggregation_updates()
    io.write_ttm_income({"ZZ.TO": 1.0})
    io.finish_aggregation_updates()
    assert io.read_ttm_income() == {"ZZ.TO": 1.0}

    with pytest.raises(AggregationLockError):
        io.write_ttm_income({"ZZ.TO": 2.0})


def test_begin_twice_raises_and_finish_without_begin_is_noop(tmp_path: Path) -> None:
    """Re-entering ``begin`` is refused; ``finish`` with nothing held does nothing."""
    io = CsvFincolIo(tmp_path)
    io.finish_aggregation_updates()

    io.begin_aggregation_updates()
    with pytest.raises(AggregationLockError):
        io.begin_aggregation_updates()
    for lock_path in _aggregation_lock_paths(tmp_path):
        assert lock_path.is_file(), f"re-entrant begin removed {lock_path}"

    io.finish_aggregation_updates()
    io.finish_aggregation_updates()
    for lock_path in _aggregation_lock_paths(tmp_path):
        assert not lock_path.exists()


def test_write_tickers_to_cache_migrates_camel_case_header(tmp_path: Path) -> None:
    """An old camelCase header is rewritten with field names; unknown columns are kept."""
    cache = tmp_path / "cache"
    cache.mkdir()
    dest = cache / "tickers.csv"
    header, *rows = _TICKERS_FIXTURE.read_text(encoding="utf-8").splitlines()
    assert header.startswith("snapshotDate,symbol,"), "fixture should be camelCase"
    dest.write_text(
        "\n".join([header + ",legacyNote", *(row + ",keep" for row in rows)]) + "\n",
        encoding="utf-8",
    )

    io = CsvFincolIo(cache)
    original = io.read_cached_tickers(["RY.TO", "BCE.TO"])
    io.write_tickers_to_cache([original[0]])

    new_header = dest.read_text(encoding="utf-8").splitlines()[0].split(",")
    assert new_header[:2] == ["SnapshotDate", "Symbol"]
    assert new_header[-1] == "legacyNote"
    assert (
        new_header[:-1]
        == [f.name for f in fields(TickerSnapshot)][: len(new_header) - 1]
    )
    assert io.read_cached_tickers(["RY.TO", "BCE.TO"]) == original
