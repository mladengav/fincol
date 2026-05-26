from datetime import date

import pandas as pd
import pytest

from application import fincol_math as fm
from constants import (
    BCE_TO,
    BNS_TO,
    TESTCACHE_DIVIDEND_HISTORY_CSV,
)


def test_dividends_by_year_from_history_matches_expected() -> None:
    """``dividends_by_year_from_history`` matches manual sum for BNS.TO in 2025."""

    div_hist = pd.read_csv(TESTCACHE_DIVIDEND_HISTORY_CSV)
    bns = div_hist.loc[div_hist["ticker"] == BNS_TO, ["ticker", "date", "amount"]]
    by_year = fm.dividends_by_year_from_history(bns)
    bns_divs = by_year.loc[(by_year["symbol"] == BNS_TO) & (by_year["year"] == 2025)]
    assert len(bns_divs) == 1

    calculated_dividend = float(bns_divs["dividend"].iloc[0])

    expected_dividend = 4.32
    assert calculated_dividend == pytest.approx(expected_dividend)


def test_last_dividend_decrease_when_no_dividends_returns_today() -> None:
    """Tickers with no dividend rows get today's date."""

    empty = pd.DataFrame(columns=["ticker", "date", "amount"])
    assert fm.last_dividend_decrease_date_for_ticker("MISSING", empty) == date.today()


@pytest.mark.parametrize(
    "ticker, expected_years_increasing",
    [
        (BCE_TO, 0),
        (BNS_TO, 15),
    ],
    ids=[
        "bce_to_dividend_increase_streak_is_0",
        "bns_to_dividend_increase_streak_is_15",
    ],
)
def test_years_consecutive_dividend_increase(ticker, expected_years_increasing) -> None:
    """
    BCE.TO streak is 0 after the 2025-06-16 payment decrease.
    BNS.TO streak is 15 (resets in 2010 on flat/down-total year, rebuilds through 2025).
    """

    div_hist = pd.read_csv(TESTCACHE_DIVIDEND_HISTORY_CSV)
    assert (
        fm.years_consecutive_dividend_increase_for_ticker(ticker, div_hist)
        == expected_years_increasing
    )
