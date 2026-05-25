import math
from datetime import date

import pandas as pd

from application import fincol_math as fm
from constants import (
    FIXTURE_BCE_TO_TICKER,
    FIXTURE_BNS_TO_TICKER,
    FIXTURE_DIVIDEND_HISTORY_CSV,
)


def test_fincol_math_dividends_by_year_from_history_bns_2025() -> None:
    """``dividends_by_year_from_history`` matches manual sum for BNS.TO in 2025."""

    div_hist = pd.read_csv(FIXTURE_DIVIDEND_HISTORY_CSV)
    bns = div_hist.loc[
        div_hist["ticker"] == FIXTURE_BNS_TO_TICKER, ["ticker", "date", "amount"]
    ]
    by_year = fm.dividends_by_year_from_history(bns)
    row = by_year.loc[
        (by_year["symbol"] == FIXTURE_BNS_TO_TICKER) & (by_year["year"] == 2025)
    ]
    assert len(row) == 1

    expected_dividend = 4.32
    assert math.isclose(float(row["dividend"].iloc[0]), expected_dividend)


def test_fincol_math_last_dividend_decrease_no_dividends_uses_today() -> None:
    """Tickers with no dividend rows get today's date."""

    empty = pd.DataFrame(columns=["ticker", "date", "amount"])
    assert fm.last_dividend_decrease_date_for_ticker("MISSING", empty) == date.today()


def test_fincol_math_years_consecutive_dividend_increase_bce_to_is_zero() -> None:
    """BCE.TO streak is 0 after the 2025-06-16 payment decrease."""

    div_hist = pd.read_csv(FIXTURE_DIVIDEND_HISTORY_CSV)
    assert (
        fm.years_consecutive_dividend_increase_for_ticker(
            FIXTURE_BCE_TO_TICKER, div_hist
        )
        == 0
    )


def test_fincol_mathyears_consecutive_dividend_increase_bns_to_is_15() -> None:
    """BNS.TO streak is 15 (resets in 2010 on flat/down-total year, rebuilds through 2025)."""

    div_hist = pd.read_csv(FIXTURE_DIVIDEND_HISTORY_CSV)
    assert (
        fm.years_consecutive_dividend_increase_for_ticker(
            FIXTURE_BNS_TO_TICKER, div_hist
        )
        == 15
    )
