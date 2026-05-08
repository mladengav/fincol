"""
Domain logic: period-return math, TTM dividend computation, and
dividend/position transforms.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from yfinance_client import ITickerSnapshot

TTM_NUM_PAYMENTS = 4


def _get_price_on_or_after(df: pd.DataFrame, d: date) -> pd.Series:
    df2 = df[df.index.date >= d]
    return df2.iloc[0] if not df2.empty else df.iloc[0]


def _get_price_on_or_before(df: pd.DataFrame, d: date) -> pd.Series:
    df2 = df[df.index.date <= d]
    return df2.iloc[-1] if not df2.empty else df.iloc[-1]


def compute_return_periods(snapshot: ITickerSnapshot) -> dict[str, dict[str, object]]:
    """1d, 1m, YTD metrics using ``snapshot.hist`` and ``snapshot.divs``."""
    hist = snapshot.hist
    divs = snapshot.divs
    today = snapshot.end
    periods: dict[str, tuple[date, date]] = {
        "1d": (today - timedelta(days=1), today),
        "1m": (today - timedelta(days=30), today),
        "YTD": (date(today.year, 1, 1), today),
    }
    results: dict[str, dict[str, object]] = {}
    for name, (sdate, edate) in periods.items():
        start_row = _get_price_on_or_after(hist, sdate)
        end_row = _get_price_on_or_before(hist, edate)
        div_sum = divs[(divs.index.date >= sdate) & (divs.index.date <= edate)].sum()
        price_return = (end_row["Close"] - start_row["Close"]) / start_row["Close"]
        total_return = (end_row["Close"] - start_row["Close"] + div_sum) / start_row["Close"]
        adj_return = (end_row["Adj Close"] - start_row["Adj Close"]) / start_row["Adj Close"]
        results[name] = {
            "start_date": start_row.name.date(),
            "end_date": end_row.name.date(),
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
    s = sub.assign(_d=pd.to_datetime(sub["date"])).sort_values("_d", ascending=False).head(TTM_NUM_PAYMENTS)
    return float(s["amount"].sum())


def aggregate_positions_by_ticker(positions: list[tuple[str, float]]) -> list[tuple[str, float]]:
    acc: dict[str, float] = {}
    for sym, q in positions:
        acc[sym] = acc.get(sym, 0.0) + q
    return sorted(acc.items(), key=lambda x: x[0])
