"""Tests for dividend loading (CSV-backed Yahoo stub + cache CSV).

:class:`~application.dividend_loader.DividendLoader` is exercised with a test
:class:`~application.iyahoo_finance.IYahooFinance` that reads ``bns_divs.csv``,
persists via :class:`~infrastructure.csv.CsvFincolIo`, refreshes TTM
aggregations via :class:`~application.aggregation_updater.AggregationUpdater`,
and verifies cache CSV output against the ``testcache`` dividend fixture for
``BNS.TO``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from application.aggregation_updater import AggregationUpdater
from application.dividend_loader import DividendLoader
from domain.iticker_snapshot import ITickerSnapshot
from infrastructure.csv import CsvFincolIo

DIVIDEND_HISTORY_CSV = (
    Path(__file__).resolve().parent / "testcache" / "dividend_history.csv"
)
TTM_INCOME_FIXTURE_CSV = (
    Path(__file__).resolve().parent / "testcache" / "ttm_income.csv"
)
BNS_DIVS_CSV = Path(__file__).resolve().parent / "testinputs" / "bns_divs.csv"

BNS_TO_TICKER = "BNS.TO"


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


@dataclass
class FakeTickerSnapshot:
    """Minimal :class:`~domain.iticker_snapshot.ITickerSnapshot` for tests (no ``yfinance`` ticker)."""

    snapshotDate: date
    symbol: str
    sectorKey: str
    industryKey: str
    exDividendDateUtc: date
    hist: pd.DataFrame = field(default_factory=pd.DataFrame)
    divs: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))

    def with_dividends(self) -> ITickerSnapshot:
        return self

    def with_history(self) -> ITickerSnapshot:
        return self

    def with_info(self) -> ITickerSnapshot:
        return self


class CsvBackedYahooFinance:
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

    def load_ticker(
        self,
        symbol: str,
        withDividends: bool = False,
        withInfo: bool = False,
    ) -> FakeTickerSnapshot:
        snap = FakeTickerSnapshot(
            snapshotDate=datetime.now().date(),
            symbol=symbol,
            sectorKey="",
            industryKey="",
            exDividendDateUtc=date(1970, 1, 1)
        )
        if withDividends:
            snap.divs = self._template_divs.copy()
        if withInfo:
            snap.with_info()
        return snap

    def dividend_sum_after_ex_date(self, symbols: list[str], ex_date: date) -> dict[str, float]:
        """Per-symbol sums from ``bns_divs.csv`` (fixture amounts apply only to ``BNS.TO``)."""
        window_start = ex_date + timedelta(days=1)
        ts = pd.Timestamp(datetime.combine(window_start, datetime.min.time()), tz="UTC")
        tail = self._template_divs[self._template_divs.index >= ts]
        div_sum = float(tail.fillna(0).sum())
        return {sym: div_sum if sym == BNS_TO_TICKER else 0.0 for sym in symbols}


@pytest.fixture(scope="module")
def expected_dividends_bns_to() -> pd.DataFrame:
    """Return the ``(date, amount)`` rows for BNS.TO from the cached CSV fixture."""
    df = pd.read_csv(DIVIDEND_HISTORY_CSV)
    rows = df.loc[df["ticker"] == BNS_TO_TICKER, ["date", "amount"]].copy()
    assert (
        not rows.empty
    ), f"Test fixture is empty for {BNS_TO_TICKER}: no rows in {DIVIDEND_HISTORY_CSV}"
    rows["date"] = rows["date"].astype(str)
    rows["amount"] = rows["amount"].astype(float)
    return rows.sort_values("date").reset_index(drop=True)


@pytest.fixture(scope="module")
def generated_cache_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Ephemeral cache: dividend history load + TTM aggregation for BNS.TO."""
    tmp_folder = tmp_path_factory.mktemp("dividend_loader_bns_cache")
    fincol_io = CsvFincolIo(tmp_folder)
    dividend_loader = DividendLoader(CsvBackedYahooFinance(), fincol_io)
    dividend_loader.update_dividend_history([BNS_TO_TICKER])

    # TODO:  Separate into AggregationUpdater test
    AggregationUpdater().update_aggregations(fincol_io)

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
    bns = written.loc[written["ticker"] == BNS_TO_TICKER, ["date", "amount"]].copy()
    bns["date"] = bns["date"].astype(str)
    bns["amount"] = bns["amount"].astype(float)
    actual = bns.sort_values("date").reset_index(drop=True)
    expected = expected_dividends_bns_to.sort_values("date").reset_index(drop=True)
    pd.testing.assert_frame_equal(
        actual,
        expected,
        obj=f"{out_path.name} {BNS_TO_TICKER} vs {DIVIDEND_HISTORY_CSV.name} fixture",
    )


# TODO:  Separate into AggregationUpdater test
def test_run_load_dividend_history_bns_to_ttm_matches_fixture(
    generated_cache_dir: Path,
) -> None:
    """Written ``ttm_income.csv`` ``ttm_dividend`` for BNS.TO must match ``testcache/ttm_income.csv``."""

    ttm_path = generated_cache_dir / "ttm_income.csv"
    assert ttm_path.is_file(), f"Expected {ttm_path} after aggregation update"

    actual_df = pd.read_csv(ttm_path)
    assert "ticker" in actual_df.columns and "ttm_dividend" in actual_df.columns

    actual_row = actual_df.loc[actual_df["ticker"] == BNS_TO_TICKER]
    assert not actual_row.empty, f"No TTM row for {BNS_TO_TICKER} in {ttm_path}"

    expected_df = pd.read_csv(TTM_INCOME_FIXTURE_CSV)
    expected_row = expected_df.loc[expected_df["ticker"] == BNS_TO_TICKER]
    assert not expected_row.empty, (
        f"No TTM row for {BNS_TO_TICKER} in fixture {TTM_INCOME_FIXTURE_CSV}"
    )

    actual_ttm = float(actual_row["ttm_dividend"].iloc[0])
    expected_ttm = float(expected_row["ttm_dividend"].iloc[0])
    assert actual_ttm == expected_ttm, (
        f"{BNS_TO_TICKER} ttm_dividend: expected {expected_ttm} from "
        f"{TTM_INCOME_FIXTURE_CSV.name}, got {actual_ttm} in {ttm_path.name}"
    )
