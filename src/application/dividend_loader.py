"""Load Yahoo dividend snapshots and merge them into dividend history via :class:`~domain.fincol_io.IFincolIo`."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import pandas as pd

from application.iyahoo_finance import IYahooFinance
from application.debug_utils import debug_print_divs_structure
from domain.fincol_io import IFincolIo
from domain.iticker_snapshot import ITickerSnapshot


@runtime_checkable
class IDividendLoader(Protocol):
    """Loads dividend snapshots and persists dividend history via :class:`IFincolIo`."""

    def retrieve_ticker_dividends(
        self, symbol: str, *, verbose: bool = False
    ) -> ITickerSnapshot: ...

    def update_dividend_history(self, symbols: list[str]) -> None: ...


class DividendLoader:
    """Concrete Yahoo-based dividend loader."""

    def __init__(self, yahoo_finance: IYahooFinance, fincol_io: IFincolIo) -> None:
        self.yahoo_finance = yahoo_finance
        self.fincol_io = fincol_io

    def retrieve_ticker_dividends(
        self, symbol: str, *, verbose: bool = False
    ) -> ITickerSnapshot:
        """``load_ticker`` + ``with_dividends``; print raw ex-dividend series (no price history)."""
        snapshot = self.yahoo_finance.load_ticker(symbol).with_dividends()
        print(f"Dividends (ex-dates) for {snapshot.symbol}")
        if verbose:
            debug_print_divs_structure(snapshot.divs)
        print(
            snapshot.divs.to_string()
            if not snapshot.divs.empty
            else "(no dividends in series)"
        )

        return snapshot

    def update_dividend_history(self, symbols: list[str]) -> None:
        """Like :meth:`retrieve_ticker_dividends`, plus write update to fincol_io.

        Loads data per ticker, concatenates new rows, then reads/writes cache once.
        Input symbols are deduplicated (first occurrence wins) before fetch.
        """
        unique = list(dict.fromkeys(symbols))
        if not unique:
            return

        frames: list[pd.DataFrame] = []
        for symbol in unique:
            snapshot = self.retrieve_ticker_dividends(symbol)
            frames.append(
                self._dividends_to_history_frame(snapshot.symbol, snapshot.divs)
            )

        new_df = pd.concat(frames, ignore_index=True)
        x_retrieved = len(new_df)

        rows_added = self.fincol_io.update_dividend_history(new_df)

        z_filtered = x_retrieved - rows_added

        ticker_note = unique[0] if len(unique) == 1 else f"{len(unique)} ticker(s)"
        print(
            f"{x_retrieved} rows retrieved ({ticker_note}), "
            f"{rows_added} rows added, {z_filtered} duplicate rows filtered out"
        )

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
