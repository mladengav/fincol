"""
Aggregation Updater
"""
from __future__ import annotations

from application import fincol_math as fm
from typing import Protocol, runtime_checkable

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
            print(f"  TTM dividend income (last {fm.TTM_NUM_PAYMENTS} payments): {sym} = {ttm_by_ticker[sym]:.4f}")

        print(f"Wrote TTM income to {fincol_io!r}")
