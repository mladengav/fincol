"""Direct yfinance access: progressive load (ticker -> dividends -> history as needed)."""

from __future__ import annotations

import os
import random
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from domain.ticker_snapshot import TickerSnapshot
from typing import Any

import pandas as pd
import yfinance as yf

_DEFAULT_YF_DELAY_SECONDS = 1.0
_DEFAULT_YF_JITTER_MAX_SECONDS = 1.0
_EMPTY_DECIMAL = Decimal("0.00")


def _decimal_from_info(value: Any) -> Decimal:
    if value is None:
        return _EMPTY_DECIMAL
    return Decimal(str(value))

def _sleep_before_yf() -> None:
    """Pause before yfinance network calls; delay and jitter max from env when set."""
    raw_delay = os.environ.get("FINCOL_YF_DELAY_SECONDS")
    raw_jitter = os.environ.get("FINCOL_YF_JITTER_MAX_SECONDS")
    delay = _DEFAULT_YF_DELAY_SECONDS
    jitter_max = _DEFAULT_YF_JITTER_MAX_SECONDS
    if raw_delay is not None and raw_delay.strip() != "":
        try:
            delay = float(raw_delay)
        except ValueError:
            pass
    if raw_jitter is not None and raw_jitter.strip() != "":
        try:
            jitter_max = float(raw_jitter)
        except ValueError:
            pass
    time.sleep(max(0.0, delay) + random.uniform(0.0, max(0.0, jitter_max)))


def _history_dividends_slice(df: pd.DataFrame) -> pd.DataFrame | pd.Series | None:
    cols = df.columns
    if isinstance(cols, pd.MultiIndex):
        if "Dividends" not in cols.get_level_values(0):
            return None
        return df["Dividends"]
    if "Dividends" in cols:
        return df["Dividends"]
    return None

class YahooFinance:
    """Yahoo Finance client backed by ``yfinance``; implements :class:`~application.iyahoo_finance.IYahooFinance`."""

    def load_ticker_info(
        self,
        symbol: str
    ) -> TickerSnapshot:
        """Create a yfinance :class:`yf.Ticker` and date window; optionally load dividends and/or ticker info."""
        info = yf.Ticker(symbol).info

        snap = TickerSnapshot(
            snapshotDate=datetime.now().date(),
            symbol=symbol,
            sectorKey=str(info.get("sectorKey") or ""),
            industryKey=str(info.get("industryKey") or ""),
            exDividendDate=info["exDividendDate"],
            longName=str(info.get("longName") or ""),
            currentPrice=_decimal_from_info(info.get("currentPrice")),
            dividendRate=_decimal_from_info(info.get("dividendRate")),
            dividendYield=float(info.get("dividendYield") or 0.0),
            marketCap=int(info.get("marketCap") or 0),
            payoutRatio=float(info.get("payoutRatio") or 0.0),
        )

        return snap

    def load_ticker_dividends(self, symbol: str) -> pd.Series:
        """Fetch ex-dividend series from the bound ticker."""
        return yf.Ticker(symbol).dividends


    def load_ticker_history(self, symbol: str,history_start: date, end: date) -> pd.DataFrame:
        """Fetch daily event history for the given date window (``auto_adjust=False``)."""
        hist = yf.Ticker(symbol).history(
            start = history_start.isoformat(),
            end= (end + timedelta(days=1)).isoformat(),
            interval="1d",
            auto_adjust=False
        )
        return hist

    def dividend_sum_after_ex_date(self, symbols: list[str], ex_date: date) -> dict[str, float]:
        """Per-symbol sum of ``Dividends`` from the day after ``ex_date`` (missing columns → ``0.0``)."""
        if not symbols:
            return {}
        zeros = {sym: 0.0 for sym in symbols}
        start = datetime.combine(ex_date + timedelta(days=1), datetime.min.time())
        _sleep_before_yf()
        df = yf.Tickers(" ".join(symbols)).history(start=start, progress=False)
        if df.empty:
            return zeros

        div = _history_dividends_slice(df)
        if div is None:
            return zeros

        if isinstance(div, pd.DataFrame):
            return {
                sym: float(div[sym].fillna(0).sum()) if sym in div.columns else 0.0
                for sym in symbols
            }
        if isinstance(div, pd.Series):
            total = float(div.fillna(0).sum())
            if len(symbols) == 1:
                return {symbols[0]: total}
            return {sym: 0.0 for sym in symbols}
        return zeros
