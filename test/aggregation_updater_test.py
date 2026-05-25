"""Tests for :class:`~application.aggregation_updater.AggregationUpdater`."""

from __future__ import annotations

import math
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from application.aggregation_updater import AggregationUpdater
from application.dividend_loader import DividendLoader
from constants import (
    FIXTURE_BCE_TO_TICKER,
    FIXTURE_BNS_TO_TICKER,
    FIXTURE_DIVIDEND_HISTORY_CSV,
    FIXTURE_TESTCACHE_DIR,
)
from dividend_loader_test import CsvBackedYahooFinance
from infrastructure.csv import CsvFincolIo

AGGREGATIONS_FOLDER = FIXTURE_TESTCACHE_DIR / "aggregations"  # type: ignore[assignment]

TTM_INCOME_FIXTURE_CSV = AGGREGATIONS_FOLDER / "ttm_income.csv"


@pytest.fixture(scope="module")
def generated_bns_cache_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Ephemeral cache with dividend history and TTM aggregation for BNS.TO."""
    tmp_folder = tmp_path_factory.mktemp("aggregation_updater_bns_cache")
    fincol_io = CsvFincolIo(tmp_folder)
    dividend_loader = DividendLoader(CsvBackedYahooFinance(), fincol_io)
    dividend_loader.update_dividend_history([FIXTURE_BNS_TO_TICKER])
    AggregationUpdater(fincol_io).update_aggregations([FIXTURE_BNS_TO_TICKER])
    return tmp_folder


def test_bns_ttm_dividend_matches_fixture(
    generated_bns_cache_dir: Path,
) -> None:
    """Written ``aggregations/ttm_income.csv`` ``ttm_dividend`` for BNS.TO must match the testcache fixture."""

    ttm_path = generated_bns_cache_dir / "aggregations" / "ttm_income.csv"
    assert ttm_path.is_file(), f"Expected {ttm_path} after aggregation update"

    actual_df = pd.read_csv(ttm_path)
    assert "ticker" in actual_df.columns and "ttm_dividend" in actual_df.columns

    actual_row = actual_df.loc[actual_df["ticker"] == FIXTURE_BNS_TO_TICKER]
    assert not actual_row.empty, f"No TTM row for {FIXTURE_BNS_TO_TICKER} in {ttm_path}"

    actual_ttm = float(actual_row["ttm_dividend"].iloc[0])

    expected_ttm = float(4.4000)
    assert math.isclose(actual_ttm, expected_ttm), (
        f"{FIXTURE_BNS_TO_TICKER} ttm_dividend: expected {expected_ttm} from "
        f"{TTM_INCOME_FIXTURE_CSV.name}, got {actual_ttm} in {ttm_path.name}"
    )


def test_bns_last_decrease_matches_first_payment_date(
    generated_bns_cache_dir: Path,
) -> None:
    """``aggregations/last_dividend_decrease.csv`` for BNS.TO must match the first payment date, as BNS has had no decreases."""

    path = generated_bns_cache_dir / "aggregations" / "last_dividend_decrease.csv"
    assert path.is_file(), f"Expected {path} after aggregation update"

    actual_df = pd.read_csv(path)
    assert (
        "ticker" in actual_df.columns and "last_dividend_decrease" in actual_df.columns
    )

    actual_row = actual_df.loc[actual_df["ticker"] == FIXTURE_BNS_TO_TICKER]
    assert (
        not actual_row.empty
    ), f"No last-decrease row for {FIXTURE_BNS_TO_TICKER} in {path}"

    actual_date = str(actual_row["last_dividend_decrease"].iloc[0])

    expected_date = "1995-03-29"
    assert (
        actual_date == expected_date
    ), f"{FIXTURE_BNS_TO_TICKER} last_dividend_decrease: expected {expected_date}, got {actual_date} in {path.name}"


def test_bns_years_since_decrease_matches_fixture(
    generated_bns_cache_dir: Path,
) -> None:
    """``aggregations/years_since_dividend_decrease.csv`` for BNS.TO must match the testcache fixture."""

    path = (
        generated_bns_cache_dir / "aggregations" / "years_since_dividend_decrease.csv"
    )
    assert path.is_file(), f"Expected {path} after aggregation update"

    actual_df = pd.read_csv(path)
    assert (
        "ticker" in actual_df.columns
        and "years_since_dividend_decrease" in actual_df.columns
    )

    actual_row = actual_df.loc[actual_df["ticker"] == FIXTURE_BNS_TO_TICKER]
    assert (
        not actual_row.empty
    ), f"No years-since row for {FIXTURE_BNS_TO_TICKER} in {path}"

    actual_years = int(actual_row["years_since_dividend_decrease"].iloc[0])

    expected_years = 31
    assert (
        actual_years == expected_years
    ), f"{FIXTURE_BNS_TO_TICKER} years_since_dividend_decrease: expected {expected_years} from, got {actual_years} in {path.name}"


def test_bce_last_dividend_decrease_uses_latest_cut_date(tmp_path: Path) -> None:
    """BCE.TO last cut date from testcache dividend history matches the aggregation fixture."""

    div_hist = pd.read_csv(FIXTURE_DIVIDEND_HISTORY_CSV)
    bce = div_hist.loc[
        div_hist["ticker"] == FIXTURE_BCE_TO_TICKER, ["ticker", "date", "amount"]
    ]
    assert (
        not bce.empty
    ), f"No dividend rows for {FIXTURE_BCE_TO_TICKER} in {FIXTURE_DIVIDEND_HISTORY_CSV}"

    fincol_io = CsvFincolIo(tmp_path)
    fincol_io.write_dividend_history(bce)
    AggregationUpdater(fincol_io).update_aggregations([FIXTURE_BCE_TO_TICKER])

    result = fincol_io.read_last_dividend_decrease()

    expected_date = date(2025, 6, 16)
    assert result[FIXTURE_BCE_TO_TICKER] == expected_date


def test_bns_dividends_by_year_2025_matches_expected(tmp_path: Path) -> None:
    """BNS.TO 2025 annual dividend total from testcache history is 4.32."""

    div_hist = pd.read_csv(FIXTURE_DIVIDEND_HISTORY_CSV)
    bns = div_hist.loc[
        div_hist["ticker"] == FIXTURE_BNS_TO_TICKER, ["ticker", "date", "amount"]
    ]
    assert (
        not bns.empty
    ), f"No dividend rows for {FIXTURE_BNS_TO_TICKER} in {FIXTURE_DIVIDEND_HISTORY_CSV}"

    fincol_io = CsvFincolIo(tmp_path)
    fincol_io.write_dividend_history(bns)
    AggregationUpdater(fincol_io).update_aggregations([FIXTURE_BNS_TO_TICKER])

    path = tmp_path / "aggregations" / "dividends_by_year.csv"
    assert path.is_file(), f"Expected {path} after aggregation update"

    actual_df = pd.read_csv(path)
    row = actual_df.loc[
        (actual_df["symbol"] == FIXTURE_BNS_TO_TICKER) & (actual_df["year"] == 2025)
    ]
    assert not row.empty, f"No 2025 row for {FIXTURE_BNS_TO_TICKER} in {path}"

    expected_dividend = 4.32
    assert math.isclose(
        float(row["dividend"].iloc[0]), expected_dividend
    ), f"{FIXTURE_BNS_TO_TICKER} 2025 dividend: expected 4.32, got {row['dividend'].iloc[0]}"


def test_bce_years_since_dividend_decrease_matches_expected(tmp_path: Path) -> None:
    """BCE.TO years since last cut from testcache dividend history matches the fixture."""

    div_hist = pd.read_csv(FIXTURE_DIVIDEND_HISTORY_CSV)
    bce = div_hist.loc[
        div_hist["ticker"] == FIXTURE_BCE_TO_TICKER, ["ticker", "date", "amount"]
    ]
    assert (
        not bce.empty
    ), f"No dividend rows for {FIXTURE_BCE_TO_TICKER} in {FIXTURE_DIVIDEND_HISTORY_CSV}"

    fincol_io = CsvFincolIo(tmp_path)
    fincol_io.write_dividend_history(bce)
    AggregationUpdater(fincol_io).update_aggregations([FIXTURE_BCE_TO_TICKER])

    result = fincol_io.read_years_since_dividend_decrease()

    expected_years = 1
    assert result[FIXTURE_BCE_TO_TICKER] == expected_years


def test_bns_years_consecutive_dividend_increase_matches_expected(
    tmp_path: Path,
) -> None:
    """BNS.TO years consecutive dividend increase from testcache dividend history matches the fixture."""

    div_hist = pd.read_csv(FIXTURE_DIVIDEND_HISTORY_CSV)
    bns = div_hist.loc[
        div_hist["ticker"] == FIXTURE_BNS_TO_TICKER, ["ticker", "date", "amount"]
    ]
    assert (
        not bns.empty
    ), f"No dividend rows for {FIXTURE_BNS_TO_TICKER} in {FIXTURE_DIVIDEND_HISTORY_CSV}"

    fincol_io = CsvFincolIo(tmp_path)
    fincol_io.write_dividend_history(bns)
    AggregationUpdater(fincol_io).update_aggregations([FIXTURE_BNS_TO_TICKER])

    result = fincol_io.read_years_consecutive_dividend_increase()

    expected_years = 15
    assert result[FIXTURE_BNS_TO_TICKER] == expected_years


def test_bce_years_consecutive_dividend_increase_matches_expected(
    tmp_path: Path,
) -> None:
    """BCE.TO years consecutive dividend increase from testcache dividend history matches the fixture."""

    div_hist = pd.read_csv(FIXTURE_DIVIDEND_HISTORY_CSV)
    bce = div_hist.loc[
        div_hist["ticker"] == FIXTURE_BCE_TO_TICKER, ["ticker", "date", "amount"]
    ]
    assert (
        not bce.empty
    ), f"No dividend rows for {FIXTURE_BCE_TO_TICKER} in {FIXTURE_DIVIDEND_HISTORY_CSV}"

    fincol_io = CsvFincolIo(tmp_path)
    fincol_io.write_dividend_history(bce)
    AggregationUpdater(fincol_io).update_aggregations([FIXTURE_BCE_TO_TICKER])

    result = fincol_io.read_years_consecutive_dividend_increase()

    expected_years = 0
    assert result[FIXTURE_BCE_TO_TICKER] == expected_years


def test_years_consecutive_dividend_increase_written_for_bns(
    generated_bns_cache_dir: Path,
) -> None:
    """Aggregation writes BNS.TO years_consecutive_dividend_increase to cache CSV."""

    path = (
        generated_bns_cache_dir
        / "aggregations"
        / "years_consecutive_dividend_increase.csv"
    )
    assert path.is_file(), f"Expected {path} after aggregation update"

    actual_df = pd.read_csv(path)
    row = actual_df.loc[actual_df["ticker"] == FIXTURE_BNS_TO_TICKER]
    assert not row.empty

    expected_years = 15
    assert int(row["years_consecutive_dividend_increase"].iloc[0]) == expected_years
