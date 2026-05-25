"""Tests for :mod:`infrastructure.yfinance_client`.

These tests perform a live network call to Yahoo Finance for the ticker(s) under test
and verify that the expected dividend data structures are populated correctly.
"""

from __future__ import annotations

import math
from test.constants import FIXTURE_DIVIDEND_HISTORY_CSV

import pandas as pd
import pytest

from infrastructure.yfinance_client import YahooFinance

# CSV amounts are stored to 4 decimal places, so anything closer than that is noise.
# A small relative tolerance covers historical splits/rounding drift in the live feed.
_AMOUNT_REL_TOL = 1e-3
_AMOUNT_ABS_TOL = 1e-4

TD_TO_TICKER = "TD.TO"


@pytest.fixture(scope="module")
def yahoo_finance() -> YahooFinance:
    """Shared live client for the module (one :class:`YahooFinance` per test file)."""
    return YahooFinance()


@pytest.fixture(scope="module")
def expected_dividends_td_to() -> pd.DataFrame:
    """Return the ``(date, amount)`` rows for TD.TO from the cached CSV fixture."""
    df = pd.read_csv(FIXTURE_DIVIDEND_HISTORY_CSV)
    rows = df.loc[df["ticker"] == TD_TO_TICKER, ["date", "amount"]].copy()
    assert (
        not rows.empty
    ), f"Test fixture is empty for {TD_TO_TICKER}: no rows in {FIXTURE_DIVIDEND_HISTORY_CSV}"
    rows["date"] = rows["date"].astype(str)
    rows["amount"] = rows["amount"].astype(float)
    return rows.sort_values("date").reset_index(drop=True)


def test_snapshot_td_to_dividends_contain_all_cached_entries(
    expected_dividends_td_to: pd.DataFrame,
    yahoo_finance: YahooFinance,
) -> None:
    """Every dividend in the CSV fixture must appear in ``snapshot_td_to.divs`` for TD.TO.

    Extra (likely more recent) dividends in ``snapshot_td_to.divs`` are allowed.
    """
    divs = yahoo_finance.load_ticker_dividends(TD_TO_TICKER)
    assert isinstance(
        divs, pd.Series
    ), f"Expected snapshot_td_to.get_dividends() to be a pandas.Series, got {type(divs).__name__}"
    assert not divs.empty, f"yfinance returned no dividends for {TD_TO_TICKER}"

    live_by_date: dict[str, float] = {
        ts.strftime("%Y-%m-%d"): float(amount)
        for ts, amount in zip(pd.to_datetime(divs.index), divs.tolist())
    }

    missing: list[tuple[str, float, float | None]] = []
    for row in expected_dividends_td_to.itertuples(index=False):
        live_amount = live_by_date.get(row.date)
        if live_amount is None or not math.isclose(
            live_amount, row.amount, rel_tol=_AMOUNT_REL_TOL, abs_tol=_AMOUNT_ABS_TOL
        ):
            missing.append((row.date, row.amount, live_amount))

    if missing:
        details = "\n".join(
            f"  - {d}: expected {amt:.4f}, "
            + (
                "not present in snapshot_td_to.divs"
                if live is None
                else f"got {live:.4f}"
            )
            for d, amt, live in missing
        )
        pytest.fail(
            f"{len(missing)} dividend(s) for {TD_TO_TICKER} from "
            f"{FIXTURE_DIVIDEND_HISTORY_CSV.name} are missing from snapshot_td_to.divs:\n{details}"
        )
