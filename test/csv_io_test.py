"""Tests for :mod:`infrastructure.csv_io` cache readers."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import yfinance as yf

from infrastructure.csv_io import CsvFincolIo
from infrastructure.yfinance_client import TickerSnapshot

_TESTCACHE = Path(__file__).resolve().parent / "testcache"
_TICKERS_FIXTURE = _TESTCACHE / "tickers.csv"


def test_read_cached_tickers_from_testcache_fixture() -> None:
    """``read_cached_tickers`` maps ``testcache/tickers.csv`` rows onto :class:`~infrastructure.yfinance_client.TickerSnapshot` fields."""
    assert _TICKERS_FIXTURE.is_file(), f"missing fixture: {_TICKERS_FIXTURE}"

    fincol_io = CsvFincolIo(_TESTCACHE)
    snapshots = fincol_io.read_cached_tickers(["RY.TO"])

    assert len(snapshots) == 1
    snap = snapshots[0]
    assert snap.symbol == "RY.TO"
    assert snap.snapshotDate == date(2026, 5, 14)
    assert snap.sectorKey == "financial-services"
    assert snap.industryKey == "banks-diversified"
    assert snap.exDividendDateUtc == date(2026, 4, 23)


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
    assert s.snapshotDate == date(2026, 5, 14)
    assert s.sectorKey == "financial-services"
    assert s.industryKey == "banks-diversified"
    assert s.exDividendDateUtc == date(2026, 4, 23)


def test_write_tickers_to_cache_creates_minimal_csv(tmp_path: Path) -> None:
    """When ``tickers.csv`` is missing, write uses default headers and can be read back."""
    cache = tmp_path / "cache"
    io = CsvFincolIo(cache)
    snap = TickerSnapshot(
        snapshotDate=date(2024, 1, 2),
        symbol="ZZ.TO",
        sectorKey="sk",
        industryKey="ik",
        exDividendDateUtc=date(2024, 3, 4),
        ticker=yf.Ticker("ZZ.TO"),
    )
    io.write_tickers_to_cache([snap])

    out = io.read_cached_tickers(["ZZ.TO"])
    assert len(out) == 1
    r = out[0]
    assert r.symbol == "ZZ.TO"
    assert r.snapshotDate == date(2024, 1, 2)
    assert r.sectorKey == "sk"
    assert r.industryKey == "ik"
    assert r.exDividendDateUtc == date(2024, 3, 4)


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
    other = TickerSnapshot(
        snapshotDate=date(2024, 6, 1),
        symbol="OTHER.TO",
        sectorKey="x",
        industryKey="y",
        exDividendDateUtc=date(2024, 6, 15),
        ticker=yf.Ticker("OTHER.TO"),
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
            TickerSnapshot(
                snapshotDate=date(2024, 6, 1),
                symbol="OTHER.TO",
                sectorKey="keep-me",
                industryKey="y",
                exDividendDateUtc=date(2024, 6, 15),
                ticker=yf.Ticker("OTHER.TO"),
            )
        ]
    )
    io.write_tickers_to_cache(
        [
            TickerSnapshot(
                snapshotDate=date(2025, 1, 1),
                symbol="RY.TO",
                sectorKey="updated",
                industryKey="updated-ik",
                exDividendDateUtc=date(2025, 2, 2),
                ticker=yf.Ticker("RY.TO"),
            )
        ]
    )

    loaded = io.read_cached_tickers(["RY.TO", "OTHER.TO"])
    by_sym = {s.symbol: s for s in loaded}
    assert by_sym["OTHER.TO"].sectorKey == "keep-me"
    assert by_sym["RY.TO"].sectorKey == "updated"
    assert by_sym["RY.TO"].industryKey == "updated-ik"
