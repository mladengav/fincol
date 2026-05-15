"""Direct yfinance access: progressive load (ticker -> dividends -> history as needed)."""

from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
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


@dataclass
class YfTickerSnapshot:
    """Live bundle built by :meth:`YahooFinance.load_ticker` and follow-up loaders; implements :class:`ITickerSnapshot`."""

    snapshotDate: date
    symbol: str
    ticker: yf.Ticker = field(repr=False)
    sectorKey: str = ""
    industryKey: str = ""
    exDividendDateUtc: date = date(1900, 1, 1)
    divs: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    longName: str = ""
    currentPrice: Decimal = _EMPTY_DECIMAL
    dividendRate: Decimal = _EMPTY_DECIMAL
    dividendYield: float = 0.0
    marketCap: int = 0
    payoutRatio: float = 0.0

    def with_dividends(self) -> YfTickerSnapshot:
        """Populate ``YfTickerSnapshot.divs`` from the bound ticker (ex-dividend series)."""
        self.divs = self.ticker.dividends
        return self

    def get_history(self, history_start: date, end: date) -> YfTickerSnapshot:
        """Populate ``YfTickerSnapshot.hist`` for the snapshot's date window (daily bars, ``auto_adjust=False``)."""
        hist = self.ticker.history(
            start = history_start.isoformat(),
            end= (end + timedelta(days=1)).isoformat(),
            interval="1d",
            auto_adjust=False
        )
        return hist
    
    def with_info(self) -> YfTickerSnapshot:
        """Populate sector, industry, ex-dividend date, and quote fields from ``ticker.info``."""
        _sleep_before_yf()
        info = self.ticker.info
        self.sectorKey = str(info.get("sectorKey") or "")
        self.industryKey = str(info.get("industryKey") or "")
        self.exDividendDateUtc = info["exDividendDate"]
        self.longName = str(info.get("longName") or "")
        self.currentPrice = _decimal_from_info(info.get("currentPrice"))
        self.dividendRate = _decimal_from_info(info.get("dividendRate"))
        self.dividendYield = float(info.get("dividendYield") or 0.0)
        raw_cap = info.get("marketCap")
        self.marketCap = int(raw_cap) if raw_cap is not None else 0
        self.payoutRatio = float(info.get("payoutRatio") or 0.0)
        return self


class YahooFinance:
    """Yahoo Finance client backed by ``yfinance``; implements :class:`~application.iyahoo_finance.IYahooFinance`."""

    def load_ticker(
        self,
        symbol: str,
        withDividends: bool = False,
        withInfo: bool = False,
    ) -> YfTickerSnapshot:
        """Create a yfinance :class:`yf.Ticker` and date window; optionally load dividends and/or ticker info."""
        snap = YfTickerSnapshot(
            snapshotDate=datetime.now().date(),
            symbol=symbol,
            sectorKey="",
            industryKey="",
            exDividendDateUtc=date(1900, 1, 1),
            ticker=yf.Ticker(symbol),
        )
        if withDividends:
            snap.with_dividends()
        if withInfo:
            snap.with_info()
        return snap

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
