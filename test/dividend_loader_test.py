"""Tests for dividend loading (CSV-backed Yahoo stub + cache CSV).

:class:`~application.dividend_loader.DividendLoader` is exercised with a test
:class:`~application.iyahoo_finance.IYahooFinance` that reads ``bns_divs.csv``,
persists via :class:`~infrastructure.csv.CsvFincolIo`, and verifies cache CSV
output against the ``testcache`` dividend fixture for ``BNS.TO``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from application.dividend_loader import DividendLoader
from application.iyahoo_finance import IYahooFinance
from constants import BNS_TO, TESTCACHE_DIVIDEND_HISTORY_CSV
from domain.ticker_snapshot import TickerSnapshot
from infrastructure.csv import CsvFincolIo

BNS_DIVS_CSV = Path(__file__).resolve().parent / "testinputs" / "bns_divs.csv"


def _bns_dividends_series_from_csv(path: Path = BNS_DIVS_CSV) -> pd.Series:
    """Ex-dividend series shaped like ``yfinance.Ticker.dividends`` (DatetimeIndex, ``Dividends`` name)."""
    df = pd.read_csv(path)
    idx = pd.to_datetime(df["Date"], utc=True)
    s = pd.Series(
        df["Dividends"].astype(float).to_numpy(),
        index=idx,
        name="Dividends",
    )
    return s.sort_index()


# TODO Simplify to a NotImplemented instance to prevent network calls, then mock invidual methods with pytest-mock
class CsvBackedYahooFinance(IYahooFinance):
    """Test :class:`~application.iyahoo_finance.IYahooFinance` using static ``bns_divs.csv`` dividends."""

    def __init__(self, csv_path: Path = BNS_DIVS_CSV) -> None:
        self._template_divs = _bns_dividends_series_from_csv(csv_path)
        idx = self._template_divs.index
        if len(idx) > 0:
            self._history_start = pd.Timestamp(idx.min()).date()
            self._end = pd.Timestamp(idx.max()).date()
        else:
            self._history_start = date(2000, 1, 1)
            self._end = date.today()

    def load_ticker_info(self, symbol: str) -> TickerSnapshot:
        snap = TickerSnapshot(
            snapshotDate=datetime.now().date(),
            symbol=symbol,
            sectorKey="",
            industryKey="",
            industry="",
            sector="",
            exDividendDate=date(1900, 1, 1),
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
        return snap

    def load_ticker_dividends(self, symbol: str) -> pd.Series:
        return self._template_divs.copy()

    def load_ticker_history(
        self, symbol: str, history_start: date, end: date
    ) -> pd.DataFrame:
        return NotImplemented

    def dividend_sum_after_ex_date(
        self, symbols: list[str], ex_date: date
    ) -> dict[str, float]:
        """Per-symbol sums from ``bns_divs.csv`` (fixture amounts apply only to ``BNS.TO``)."""
        window_start = ex_date + timedelta(days=1)
        ts = pd.Timestamp(datetime.combine(window_start, datetime.min.time()), tz="UTC")
        tail = self._template_divs[self._template_divs.index >= ts]
        div_sum = float(tail.fillna(0).sum())
        return {sym: div_sum if sym == BNS_TO else 0.0 for sym in symbols}


@pytest.fixture(scope="module")
def expected_dividends_bns_to() -> pd.DataFrame:
    """Return the ``(date, amount)`` rows for BNS.TO from the cached CSV fixture."""
    df = pd.read_csv(TESTCACHE_DIVIDEND_HISTORY_CSV)
    rows = df.loc[df["ticker"] == BNS_TO, ["date", "amount"]].copy()
    assert (
        not rows.empty
    ), f"Test fixture is empty for {BNS_TO}: no rows in {TESTCACHE_DIVIDEND_HISTORY_CSV}"
    rows["date"] = rows["date"].astype(str)
    rows["amount"] = rows["amount"].astype(float)
    return rows.sort_values("date").reset_index(drop=True)


@pytest.fixture(scope="module")
def generated_cache_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Ephemeral cache after dividend history load for BNS.TO."""
    tmp_folder = tmp_path_factory.mktemp("dividend_loader_bns_cache")
    fincol_io = CsvFincolIo(tmp_folder)
    dividend_loader = DividendLoader(CsvBackedYahooFinance(), fincol_io)
    dividend_loader.update_dividend_history([BNS_TO])
    return tmp_folder


def test_update_dividend_history_bns_to_output_matches_expected(
    generated_cache_dir: Path,
    expected_dividends_bns_to: pd.DataFrame,
) -> None:
    """``dividend_history.csv`` rows for BNS.TO must match ``expected_dividends_bns_to`` exactly (no extras, no gaps)."""
    out_path = generated_cache_dir / "dividend_history.csv"
    assert (
        out_path.is_file()
    ), f"Expected {out_path} to exist after dividend history update"

    written = pd.read_csv(out_path)
    bns = written.loc[written["ticker"] == BNS_TO, ["date", "amount"]].copy()
    bns["date"] = bns["date"].astype(str)
    bns["amount"] = bns["amount"].astype(float)
    actual = bns.sort_values("date").reset_index(drop=True)
    expected = expected_dividends_bns_to.sort_values("date").reset_index(drop=True)
    pd.testing.assert_frame_equal(
        actual,
        expected,
        obj=f"{out_path.name} {BNS_TO} vs {TESTCACHE_DIVIDEND_HISTORY_CSV.name} fixture",
    )
