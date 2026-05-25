"""Load Yahoo dividend snapshots and merge them into dividend history via :class:`~domain.fincol_io.IFincolIo`."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime
from typing import Protocol, runtime_checkable

import pandas as pd

from application.debug_utils import debug_print_divs_structure
from application.iyahoo_finance import IYahooFinance
from domain.fincol_io import IFincolIo

logger = logging.getLogger(__name__)


@runtime_checkable
class IDividendLoader(Protocol):
    """Loads dividend snapshots and persists dividend history via :class:`IFincolIo`."""

    def retrieve_ticker_dividends(
        self, symbol: str, *, verbose: bool = False
    ) -> pd.Series: ...  # TODO Decouple from YahooFinance schema

    def update_dividend_history(self, symbols: list[str]) -> None: ...


class DividendLoader:
    """Concrete Yahoo-based dividend loader."""

    def __init__(self, yahoo_finance: IYahooFinance, fincol_io: IFincolIo) -> None:
        self.yahoo_finance = yahoo_finance
        self.fincol_io = fincol_io

    def retrieve_ticker_dividends(
        self, symbol: str, *, verbose: bool = False
    ) -> pd.Series:
        """``load_ticker_dividends``; print raw ex-dividend series."""
        # snapshot = self.yahoo_finance.load_ticker_info(symbol)
        logger.info(f"Dividends (ex-dates) for {symbol}")
        divs = self.yahoo_finance.load_ticker_dividends(symbol)
        if verbose:
            debug_print_divs_structure(divs)
        logger.info(divs.to_string() if not divs.empty else "(no dividends in series)")

        return divs

    def update_dividend_history(self, symbols: list[str]) -> None:
        """Like :meth:`retrieve_ticker_dividends`, plus write update to fincol_io.

        Loads data per ticker, concatenates new rows, then reads/writes cache once.
        Input symbols are deduplicated (first occurrence wins) before fetch.
        """
        unique = list[str](dict.fromkeys(symbols))
        if not unique:
            return

        logger.info(f"Updating dividend history for symbols: {unique}")

        known_tickers = self.fincol_io.read_cached_tickers(unique)
        logger.info(f"Known symbols: {[t.symbol for t in known_tickers]}")

        known_symbols = {t.symbol for t in known_tickers}

        unknown_symbols = [t for t in unique if t not in known_symbols]
        logger.info(f"Unknown symbols: {unknown_symbols}")

        known_symbols_to_update = []
        by_last_dividend_date: defaultdict[date, list[str]] = defaultdict(list)
        for kt in known_tickers:
            by_last_dividend_date[kt.lastDividendDate].append(kt.symbol)
        for last_dividend_date in sorted(by_last_dividend_date):
            symbols = sorted(by_last_dividend_date[last_dividend_date])
            logger.info(f"Last dividend date {last_dividend_date}: {symbols}")

            if last_dividend_date >= datetime.now().date():
                logger.info(
                    f"Last dividend date {last_dividend_date} must be at least 1 day in the past, skipping"
                )
                continue

            symbols_to_update = self._filter_for_new_dividend_events(
                symbols, last_dividend_date
            )
            known_symbols_to_update.extend(symbols_to_update)

        logger.info(f"Known tickers to update: {known_symbols_to_update}")
        symbols_to_update = list(set(known_symbols_to_update + unknown_symbols))
        logger.info(f"Symbols to update: {symbols_to_update}")

        if not symbols_to_update:
            logger.info("No symbols to update")
            return

        updated_snapshots = []
        for symbol_to_update in symbols_to_update:
            updated_snapshots.append(
                self.yahoo_finance.load_ticker_info(symbol_to_update)
            )

        self.fincol_io.write_tickers_to_cache(updated_snapshots)

        frames: list[pd.DataFrame] = []
        for symbol in symbols_to_update:
            divs = self.retrieve_ticker_dividends(symbol)
            frames.append(self._dividends_to_history_frame(symbol, divs))

        new_df = pd.concat(frames, ignore_index=True)
        x_retrieved = len(new_df)

        rows_added = self.fincol_io.update_dividend_history(new_df)

        z_filtered = x_retrieved - rows_added

        ticker_note = (
            symbols_to_update[0]
            if len(symbols_to_update) == 1
            else f"{len(symbols_to_update)} ticker(s)"
        )
        logger.info(
            f"{x_retrieved} rows retrieved ({ticker_note}), "
            f"{rows_added} rows added, {z_filtered} duplicate rows filtered out"
        )

    def _filter_for_new_dividend_events(
        self, tickers: list[str], ex_date: date
    ) -> list[str]:
        sums_after = self.yahoo_finance.dividend_sum_after_ex_date(tickers, ex_date)
        tickers_to_update = [s for s in tickers if sums_after.get(s, 0.0) > 0.0]
        logger.info(f"  Dividend sums after {ex_date}: {sums_after}")
        logger.info(f"  Tickers with sum > 0: {tickers_to_update}")
        return tickers_to_update

    def _dividends_to_history_frame(self, symbol: str, divs: pd.Series) -> pd.DataFrame:
        """One row per dividend: ticker, calendar date (YYYY-MM-DD), amount (from ``Date`` / ``Dividends`` columns)."""
        if divs.empty:
            return pd.DataFrame(columns=["ticker", "date", "amount"])
        tab = divs.reset_index()
        date_col, amt_col = tab.columns[0], tab.columns[1]
        return pd.DataFrame(
            {
                "ticker": symbol,
                "date": pd.to_datetime(tab[date_col]).dt.strftime("%Y-%m-%d"),
                "amount": tab[amt_col].astype(float),
            }
        )
