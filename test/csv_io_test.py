"""Tests for :mod:`infrastructure.csv.io` cache readers."""

from __future__ import annotations

import shutil
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from constants import TESTCACHE_DIR
from domain.ticker_snapshot import TickerSnapshot
from infrastructure.csv import CsvFincolIo

_TICKERS_FIXTURE = TESTCACHE_DIR / "tickers.csv"


def _default_ticker_snapshot(
    snapshotDate: date,
    symbol: str,
    sectorKey: str,
    industryKey: str,
    exDividendDate: date,
) -> TickerSnapshot:

    return TickerSnapshot(
        snapshotDate=snapshotDate,
        symbol=symbol,
        sectorKey=sectorKey,
        industryKey=industryKey,
        industry="",
        sector="",
        exDividendDate=exDividendDate,
        lastDividendDate=date(1900, 1, 1),
        longName="",
        regularMarketPrice=Decimal("0.00"),
        regularMarketTime=datetime(1900, 1, 1, tzinfo=UTC),
        dividendRate=Decimal("0.00"),
        dividendYield=0.0,
        marketCap=0,
        payoutRatio=0.0,
        heldPercentInsiders=0.0,
        heldPercentInstitutions=0.0,
        quoteType="",
        typeDisp="",
    )


def test_read_cached_tickers_from_testcache_fixture() -> None:
    """``read_cached_tickers`` maps ``testcache/tickers.csv`` rows onto :class:`~domain.ticker_snapshot.TickerSnapshot` fields."""
    assert _TICKERS_FIXTURE.is_file(), f"missing fixture: {_TICKERS_FIXTURE}"

    fincol_io = CsvFincolIo(TESTCACHE_DIR)
    snapshots = fincol_io.read_cached_tickers(["RY.TO"])

    assert len(snapshots) == 1
    snap = snapshots[0]
    assert snap.symbol == "RY.TO"
    assert snap.snapshotDate == date(2026, 5, 19)
    assert snap.sectorKey == "financial-services"
    assert snap.industryKey == "banks-diversified"
    assert snap.industry == "Banks - Diversified"
    assert snap.sector == "Financial Services"
    assert snap.exDividendDate == date(2026, 4, 23)
    assert snap.lastDividendDate == date(2026, 4, 23)
    assert snap.longName == "Royal Bank of Canada"
    assert snap.regularMarketPrice == Decimal("252.53")
    assert snap.regularMarketTime == datetime(2026, 5, 19, 20, 00, 00, tzinfo=UTC)
    assert snap.dividendRate == Decimal("6.56")
    assert snap.dividendYield == 2.6
    assert snap.marketCap == 351370215424
    assert snap.payoutRatio == 0.42580003
    assert snap.heldPercentInsiders == pytest.approx(0.00027)
    assert snap.heldPercentInstitutions == pytest.approx(0.49071997)
    assert snap.quoteType == "EQUITY"
    assert snap.typeDisp == "Equity"


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
    assert s.symbol == "RY.TO"
    assert s.snapshotDate == date(2026, 5, 19)
    assert s.sectorKey == "financial-services"
    assert s.industryKey == "banks-diversified"
    assert s.exDividendDate == date(2026, 4, 23)
    assert s.longName == "Royal Bank of Canada"
    assert s.regularMarketPrice == Decimal("252.53")
    assert s.dividendRate == Decimal("6.56")


def test_write_tickers_to_cache_creates_minimal_csv(tmp_path: Path) -> None:
    """When ``tickers.csv`` is missing, write uses default headers and can be read back."""
    cache = tmp_path / "cache"
    io = CsvFincolIo(cache)
    snap = _default_ticker_snapshot(
        snapshotDate=date(2024, 1, 2),
        symbol="ZZ.TO",
        sectorKey="sk",
        industryKey="ik",
        exDividendDate=date(2024, 3, 4),
    )
    io.write_tickers_to_cache([snap])

    out = io.read_cached_tickers(["ZZ.TO"])
    assert len(out) == 1
    r = out[0]
    assert r.symbol == "ZZ.TO"
    assert r.snapshotDate == date(2024, 1, 2)
    assert r.sectorKey == "sk"
    assert r.industryKey == "ik"
    assert r.exDividendDate == date(2024, 3, 4)


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
        snapshotDate=date(2024, 6, 1),
        symbol="OTHER.TO",
        sectorKey="x",
        industryKey="y",
        exDividendDate=date(2024, 6, 15),
    )
    io.write_tickers_to_cache([other])

    loaded = io.read_cached_tickers(["RY.TO", "OTHER.TO"])
    by_sym = {s.symbol: s for s in loaded}
    assert set(by_sym) == {"RY.TO", "OTHER.TO"}
    assert by_sym["RY.TO"].snapshotDate == ry.snapshotDate
    assert by_sym["OTHER.TO"].sectorKey == "x"


def test_write_tickers_to_cache_update_one_symbol_leaves_others(tmp_path: Path) -> None:
    """Replacing one symbol's row does not remove other symbols from the cache."""
    assert _TICKERS_FIXTURE.is_file(), f"missing fixture: {_TICKERS_FIXTURE}"

    cache = tmp_path / "cache"
    cache.mkdir()
    dest = cache / "tickers.csv"
    shutil.copy(_TICKERS_FIXTURE, dest)

    io = CsvFincolIo(cache)
    io.write_tickers_to_cache(
        [
            _default_ticker_snapshot(
                snapshotDate=date(2024, 6, 1),
                symbol="OTHER.TO",
                sectorKey="keep-me",
                industryKey="y",
                exDividendDate=date(2024, 6, 15),
            )
        ]
    )
    io.write_tickers_to_cache(
        [
            _default_ticker_snapshot(
                snapshotDate=date(2025, 1, 1),
                symbol="RY.TO",
                sectorKey="updated",
                industryKey="updated-ik",
                exDividendDate=date(2025, 2, 2),
            )
        ]
    )

    loaded = io.read_cached_tickers(["RY.TO", "OTHER.TO"])
    by_sym = {s.symbol: s for s in loaded}
    assert by_sym["OTHER.TO"].sectorKey == "keep-me"
    assert by_sym["RY.TO"].sectorKey == "updated"
    assert by_sym["RY.TO"].industryKey == "updated-ik"
