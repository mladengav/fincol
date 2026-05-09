"""Tests for dividend loading (live Yahoo Finance + cache CSV).

These tests perform a live network call to Yahoo Finance via
:class:`~dividend_loader.DividendLoader`, persist via :class:`~csv_io.CsvFincolIo`,
refresh TTM aggregations via :class:`~application.aggregation_updater.AggregationUpdater`,
and verify cache CSV output against the ``testcache`` dividend fixture for ``BNS.TO``.
"""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import pytest

from application.aggregation_updater import AggregationUpdater
from csv_io import CsvFincolIo
from dividend_loader import DividendLoader
from yfinance_client import YahooFinance

DIVIDEND_HISTORY_CSV = Path(__file__).resolve().parent / "testcache" / "dividend_history.csv"

# CSV amounts are stored to 4 decimal places, so anything closer than that is noise.
# A small relative tolerance covers historical splits/rounding drift in the live feed.
_AMOUNT_REL_TOL = 1e-3
_AMOUNT_ABS_TOL = 1e-4

BNS_TO_TICKER = "BNS.TO"


@pytest.fixture(scope="module")
def expected_dividends_bns_to() -> pd.DataFrame:
    """Return the ``(date, amount)`` rows for BNS.TO from the cached CSV fixture."""
    df = pd.read_csv(DIVIDEND_HISTORY_CSV)
    rows = df.loc[df["ticker"] == BNS_TO_TICKER, ["date", "amount"]].copy()
    assert not rows.empty, (
        f"Test fixture is empty for {BNS_TO_TICKER}: no rows in {DIVIDEND_HISTORY_CSV}"
    )
    rows["date"] = rows["date"].astype(str)
    rows["amount"] = rows["amount"].astype(float)
    return rows.sort_values("date").reset_index(drop=True)


@pytest.fixture(scope="module")
def bns_load_cache_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Ephemeral cache: dividend history load + TTM aggregation for BNS.TO."""
    tmp_folder = tmp_path_factory.mktemp("dividend_loader_bns_cache")
    fincol_io = CsvFincolIo(tmp_folder)
    dividend_loader = DividendLoader(YahooFinance(), fincol_io)
    dividend_loader.update_dividend_history([BNS_TO_TICKER])
    AggregationUpdater().update_aggregations(fincol_io)
    return tmp_folder


def test_run_load_dividend_history_bns_to_output_contains_all_fixture_rows(
    bns_load_cache_dir: Path,
    expected_dividends_bns_to: pd.DataFrame,
) -> None:
    """Every BNS.TO dividend in the CSV fixture must appear in written ``dividend_history.csv``.

    Extra (likely more recent) rows from the live feed are allowed.
    """
    out_path = bns_load_cache_dir / "dividend_history.csv"
    assert out_path.is_file(), f"Expected {out_path} to exist after dividend history update"

    written = pd.read_csv(out_path)
    bns = written.loc[written["ticker"] == BNS_TO_TICKER, ["date", "amount"]].copy()
    bns["date"] = bns["date"].astype(str)
    bns["amount"] = bns["amount"].astype(float)

    actual_dividends: dict[str, float] = {
        str(row.date): float(row.amount) for row in bns.itertuples(index=False)
    }

    for row in expected_dividends_bns_to.itertuples(index=False):
        actual_amount = actual_dividends.get(row.date)
        if actual_amount is None or not math.isclose(
            actual_amount, row.amount, rel_tol=_AMOUNT_REL_TOL, abs_tol=_AMOUNT_ABS_TOL
        ):
            got = "not present" if actual_amount is None else f"{actual_amount:.4f}"
            pytest.fail(
                f"{BNS_TO_TICKER} {row.date}: expected {row.amount:.4f}, got {got} "
                f"in {out_path.name} (fixture: {DIVIDEND_HISTORY_CSV.name})"
            )


def test_run_load_dividend_history_bns_to_ttm_income_non_negative(
    bns_load_cache_dir: Path,
) -> None:
    """``ttm_income.csv`` must list BNS.TO with a non-negative TTM dividend total."""

    ttm_path = bns_load_cache_dir / "ttm_income.csv"
    assert ttm_path.is_file(), f"Expected {ttm_path} after aggregation update"

    df = pd.read_csv(ttm_path)
    assert "ticker" in df.columns and "ttm_dividend" in df.columns

    row = df.loc[df["ticker"] == BNS_TO_TICKER]
    assert not row.empty, f"No TTM row for {BNS_TO_TICKER} in {ttm_path}"

    bns_to_ttm_div = float(row["ttm_dividend"].iloc[0])
    assert bns_to_ttm_div >= 0.0, f"Expected non-negative ttm_dividend for {BNS_TO_TICKER}, got {bns_to_ttm_div}"
