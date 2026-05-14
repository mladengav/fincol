"""Tests for :mod:`infrastructure.csv_io` cache readers."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from infrastructure.csv_io import CsvFincolIo

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
