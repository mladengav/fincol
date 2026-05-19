"""Tests for :class:`~application.aggregation_updater.AggregationUpdater`."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from application import fincol_math as fm
from application.aggregation_updater import AggregationUpdater
from application.dividend_loader import DividendLoader
from dividend_loader_test import BNS_TO_TICKER, CsvBackedYahooFinance
from infrastructure.csv import CsvFincolIo

BCE_TO_TICKER = "BCE.TO"
TESTCACHE_DIR = Path(__file__).resolve().parent / "testcache"
DIVIDEND_HISTORY_FIXTURE_CSV = TESTCACHE_DIR / "dividend_history.csv"
AGGREGATIONS_FOLDER = TESTCACHE_DIR / "aggregations"  # type: ignore[assignment]

TTM_INCOME_FIXTURE_CSV = (
    AGGREGATIONS_FOLDER / "ttm_income.csv"
)
LAST_DIVIDEND_DECREASE_FIXTURE_CSV = (
    AGGREGATIONS_FOLDER / "last_dividend_decrease.csv"
)


@pytest.fixture(scope="module")
def aggregated_cache_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Ephemeral cache with dividend history and TTM aggregation for BNS.TO."""
    tmp_folder = tmp_path_factory.mktemp("aggregation_updater_cache")
    fincol_io = CsvFincolIo(tmp_folder)
    dividend_loader = DividendLoader(CsvBackedYahooFinance(), fincol_io)
    dividend_loader.update_dividend_history([BNS_TO_TICKER])
    AggregationUpdater().update_aggregations(fincol_io)
    return tmp_folder


def test_run_load_dividend_history_bns_to_ttm_matches_fixture(
    aggregated_cache_dir: Path,
) -> None:
    """Written ``aggregations/ttm_income.csv`` ``ttm_dividend`` for BNS.TO must match the testcache fixture."""

    ttm_path = aggregated_cache_dir / "aggregations" / "ttm_income.csv"
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


def test_run_load_dividend_history_bns_to_last_decrease_matches_fixture(
    aggregated_cache_dir: Path,
) -> None:
    """``aggregations/last_dividend_decrease.csv`` for BNS.TO must match the testcache fixture."""

    path = aggregated_cache_dir / "aggregations" / "last_dividend_decrease.csv"
    assert path.is_file(), f"Expected {path} after aggregation update"

    actual_df = pd.read_csv(path)
    assert (
        "ticker" in actual_df.columns and "last_dividend_decrease" in actual_df.columns
    )

    actual_row = actual_df.loc[actual_df["ticker"] == BNS_TO_TICKER]
    assert not actual_row.empty, f"No last-decrease row for {BNS_TO_TICKER} in {path}"

    expected_df = pd.read_csv(LAST_DIVIDEND_DECREASE_FIXTURE_CSV)
    expected_row = expected_df.loc[expected_df["ticker"] == BNS_TO_TICKER]
    assert not expected_row.empty, (
        f"No last-decrease row for {BNS_TO_TICKER} in fixture "
        f"{LAST_DIVIDEND_DECREASE_FIXTURE_CSV}"
    )

    actual_date = str(actual_row["last_dividend_decrease"].iloc[0])
    expected_date = str(expected_row["last_dividend_decrease"].iloc[0])
    assert actual_date == expected_date, (
        f"{BNS_TO_TICKER} last_dividend_decrease: expected {expected_date} from "
        f"{LAST_DIVIDEND_DECREASE_FIXTURE_CSV.name}, got {actual_date} in {path.name}"
    )


def test_last_dividend_decrease_uses_latest_cut_date(tmp_path: Path) -> None:
    """BCE.TO last cut date from testcache dividend history matches the aggregation fixture."""

    div_hist = pd.read_csv(DIVIDEND_HISTORY_FIXTURE_CSV)
    bce = div_hist.loc[div_hist["ticker"] == BCE_TO_TICKER, ["ticker", "date", "amount"]]
    assert not bce.empty, f"No dividend rows for {BCE_TO_TICKER} in {DIVIDEND_HISTORY_FIXTURE_CSV}"

    fincol_io = CsvFincolIo(tmp_path)
    fincol_io.write_dividend_history(bce)
    AggregationUpdater().update_aggregations(fincol_io)

    result = fincol_io.read_last_dividend_decrease()
    expected_df = pd.read_csv(LAST_DIVIDEND_DECREASE_FIXTURE_CSV)
    expected_row = expected_df.loc[expected_df["ticker"] == BCE_TO_TICKER]
    assert not expected_row.empty, (
        f"No last-decrease row for {BCE_TO_TICKER} in {LAST_DIVIDEND_DECREASE_FIXTURE_CSV}"
    )
    expected_date = date.fromisoformat(str(expected_row["last_dividend_decrease"].iloc[0]))
    assert result[BCE_TO_TICKER] == expected_date


def test_last_dividend_decrease_no_dividends_uses_today() -> None:
    """Tickers with no dividend rows get today's date."""

    empty = pd.DataFrame(columns=["ticker", "date", "amount"])
    assert fm.last_dividend_decrease_date_for_ticker("MISSING", empty) == date.today()


def test_last_dividend_decrease_no_cut_uses_first_payment_date() -> None:
    """Tickers that never cut use the earliest ex-date."""

    div_hist = pd.DataFrame(
        [
            {"ticker": "RISE", "date": "2010-06-01", "amount": 0.5},
            {"ticker": "RISE", "date": "2010-09-01", "amount": 0.6},
        ]
    )
    assert fm.last_dividend_decrease_date_for_ticker("RISE", div_hist) == date(2010, 6, 1)
