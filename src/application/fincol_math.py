"""
Math primitives: period-return computation, TTM dividend computation, and
dividend/position transforms.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

import pandas as pd

TTM_NUM_PAYMENTS = 4


def _get_price_on_or_after(df: pd.DataFrame, d: date) -> pd.Series:
    ts_index = pd.DatetimeIndex(pd.to_datetime(df.index))
    df2 = df[ts_index.date >= d]
    return df2.iloc[0] if not df2.empty else df.iloc[0]


def _get_price_on_or_before(df: pd.DataFrame, d: date) -> pd.Series:
    ts_index = pd.DatetimeIndex(pd.to_datetime(df.index))
    df2 = df[ts_index.date <= d]
    return df2.iloc[-1] if not df2.empty else df.iloc[-1]


def compute_return_periods(symbol: str, divs: pd.Series, history: pd.DataFrame) -> dict[str, dict[str, object]]:
    """1d, 1m, YTD metrics using ``snapshot.get_history`` and ``snapshot.divs``."""
    if history.empty:
        raise RuntimeError("No price data returned for " + symbol)

    today = datetime.now().date()

    periods: dict[str, tuple[date, date]] = {
        "1d": (today - timedelta(days=1), today),
        "1m": (today - timedelta(days=30), today),
        "YTD": (date(today.year, 1, 1), today),
    }
    results: dict[str, dict[str, object]] = {}
    for name, (sdate, edate) in periods.items():
        start_row = _get_price_on_or_after(history, sdate)
        end_row = _get_price_on_or_before(history, edate)
        div_idx = pd.DatetimeIndex(pd.to_datetime(divs.index))
        div_sum = divs[(div_idx.date >= sdate) & (div_idx.date <= edate)].sum()
        price_return = (end_row["Close"] - start_row["Close"]) / start_row["Close"]
        total_return = (end_row["Close"] - start_row["Close"] + div_sum) / start_row[
            "Close"
        ]
        adj_return = (end_row["Adj Close"] - start_row["Adj Close"]) / start_row[
            "Adj Close"
        ]
        results[name] = {
            "start_date": pd.Timestamp(cast(Any, start_row.name)).date(),
            "end_date": pd.Timestamp(cast(Any, end_row.name)).date(),
            "start_close": float(start_row["Close"]),
            "end_close": float(end_row["Close"]),
            "dividends": float(div_sum),
            "price_return": float(price_return),
            "total_return": float(total_return),
            "adj_return": float(adj_return),
        }
    return results


def ttm_per_share_for_ticker(ticker: str, div_hist: pd.DataFrame) -> float:
    """Sum per-share amounts for the most recent ``TTM_NUM_PAYMENTS`` ex-dates (quarterly TTM)."""
    sub = div_hist[div_hist["ticker"] == ticker]
    if sub.empty:
        return 0.0
    s = (
        sub.assign(_d=pd.to_datetime(sub["date"]))
        .sort_values("_d", ascending=False)
        .head(TTM_NUM_PAYMENTS)
    )
    return float(s["amount"].sum())


def last_dividend_decrease_date_for_ticker(ticker: str, div_hist: pd.DataFrame) -> date:
    """Latest ex-date where amount fell vs the prior payment; else earliest ex-date, or today if none."""
    sub = div_hist[div_hist["ticker"] == ticker]
    if sub.empty:
        return datetime.now().date()
    s = sub.assign(_d=pd.to_datetime(sub["date"])).sort_values("_d")
    first_date = pd.Timestamp(s["_d"].iloc[0]).date()
    if len(s) < 2:
        return first_date
    prev_amount = s["amount"].shift(1)
    decreases = s[s["amount"] < prev_amount]
    if decreases.empty:
        return first_date
    return pd.Timestamp(decreases["_d"].iloc[-1]).date()


def aggregate_positions_by_ticker(
    positions: list[tuple[str, float]],
) -> list[tuple[str, float]]:
    acc: dict[str, float] = {}
    for sym, q in positions:
        acc[sym] = acc.get(sym, 0.0) + q
    return sorted(acc.items(), key=lambda x: x[0])
