"""Derived cache fields (for example TTM dividend income per ticker)."""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from application import fincol_math as fm
from domain.fincol_io import IFincolIo


@runtime_checkable
class IAggregationUpdater(Protocol):
    """Updates derived aggregations via :class:`IFincolIo`."""

    def update_aggregations(self, fincol_io: IFincolIo) -> None: ...


class AggregationUpdater:
    """Concrete aggregation updater (TTM dividend, etc.)."""

    def update_aggregations(self, fincol_io: IFincolIo) -> None:
        """Update all aggregations via ``fincol_io``."""
        self._update_ttm_dividend(fincol_io)
        self._update_last_dividend_decrease(fincol_io)

    def _update_ttm_dividend(self, fincol_io: IFincolIo) -> None:
        """Write TTM income via ``fincol_io``."""

        div_hist = fincol_io.read_dividend_history()
        ttm_by_ticker: dict[str, float] = {}

        unique_tickers = list(dict.fromkeys(div_hist["ticker"]))

        for sym in unique_tickers:
            ttm_by_ticker[sym] = fm.ttm_per_share_for_ticker(sym, div_hist)
        fincol_io.write_ttm_income(ttm_by_ticker)

        print(f"Loaded {len(unique_tickers)} ticker(s) from {fincol_io!r}")
        for sym in unique_tickers:
            print(
                f"  TTM dividend income (last {fm.TTM_NUM_PAYMENTS} payments): {sym} = {ttm_by_ticker[sym]:.4f}"
            )

        print(f"Wrote TTM income to {fincol_io!r}")

    def _update_last_dividend_decrease(self, fincol_io: IFincolIo) -> None:
        """Write last dividend decrease date per ticker via ``fincol_io``."""

        div_hist = fincol_io.read_dividend_history()
        last_decrease_by_ticker: dict[str, date] = {}

        unique_tickers = list(dict.fromkeys(div_hist["ticker"]))

        for sym in unique_tickers:
            last_decrease_by_ticker[sym] = fm.last_dividend_decrease_date_for_ticker(
                sym, div_hist
            )
        fincol_io.write_last_dividend_decrease(last_decrease_by_ticker)

        print(f"Loaded {len(unique_tickers)} ticker(s) from {fincol_io!r}")
        for sym in unique_tickers:
            print(
                f"  Last dividend decrease: {sym} = {last_decrease_by_ticker[sym]}"
            )

        print(f"Wrote last dividend decrease to {fincol_io!r}")
