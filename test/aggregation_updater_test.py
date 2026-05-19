"""Tests for :class:`~application.aggregation_updater.AggregationUpdater`."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from application.aggregation_updater import AggregationUpdater
from application.dividend_loader import DividendLoader
from dividend_loader_test import BNS_TO_TICKER, CsvBackedYahooFinance
from infrastructure.csv import CsvFincolIo

TTM_INCOME_FIXTURE_CSV = (
    Path(__file__).resolve().parent / "testcache" / "aggregations" / "ttm_income.csv"
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
