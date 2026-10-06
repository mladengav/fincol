"""Derived cache fields (for example TTM dividend income per ticker)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable

import pandas as pd

from application import fincol_math as fm
from domain.fincol_io import IFincolIo
from domain.ticker_snapshot import TickerSnapshot

# TODO use logging instead of print


@runtime_checkable
class IAggregationUpdater(Protocol):
    """Updates derived aggregations via :class:`IFincolIo`."""

    def update_aggregations(self, symbols: list[str]) -> None: ...


class AggregationUpdater:
    """Concrete aggregation updater (TTM dividend, etc.)."""

    def __init__(self, fincol_io: IFincolIo) -> None:
        self.fincol_io = fincol_io

    def update_aggregations(self, symbols: list[str]) -> None:
        """Recompute aggregations for the cached tickers of ``symbols`` and commit them.

        After ``begin``, the cached snapshot of each symbol is read. Every
        ``_update_*`` step changes only those in-memory snapshots (or, for
        dividends by year, returns a frame); nothing is written until a single
        ``commit_aggregation_updates`` call once all steps have succeeded.
        """
        self.fincol_io.begin_aggregation_updates()
        try:
            snapshots = self.fincol_io.read_cached_tickers(symbols)
            missing = sorted(set(symbols) - {s.Symbol for s in snapshots})
            if missing:
                print(f"No cached ticker snapshot, skipping aggregations: {missing}")
            div_hist = self.fincol_io.read_dividend_history()

            self._update_ttm_dividend(snapshots, div_hist)
            dividends_by_year = self._update_dividends_by_year(snapshots, div_hist)
            self._update_last_dividend_decrease(snapshots, div_hist)
            self._update_years_since_dividend_decrease(snapshots)
            self._update_years_consecutive_dividend_increase(snapshots, div_hist)

            self.fincol_io.commit_aggregation_updates(snapshots, dividends_by_year)
            print(f"Committed aggregations for {len(snapshots)} ticker(s)")
        finally:
            self.fincol_io.finish_aggregation_updates()

    def _update_ttm_dividend(
        self, snapshots: list[TickerSnapshot], div_hist: pd.DataFrame
    ) -> None:
        """Set ``TtmDivs`` on each snapshot."""
        for snap in snapshots:
            ttm = fm.ttm_per_share_for_ticker(snap.Symbol, div_hist)
            snap.TtmDivs = Decimal(f"{ttm:.4f}")
            print(
                f"  TTM dividend income (last {fm.TTM_NUM_PAYMENTS} payments): "
                f"{snap.Symbol} = {snap.TtmDivs}"
            )

    def _update_dividends_by_year(
        self, snapshots: list[TickerSnapshot], div_hist: pd.DataFrame
    ) -> pd.DataFrame:
        """Return per-symbol annual dividend totals for the snapshots' symbols."""
        batch = {snap.Symbol for snap in snapshots}
        dividends_by_year = fm.dividends_by_year_from_history(
            div_hist[div_hist["ticker"].isin(batch)]
        )
        for sym in dict.fromkeys(dividends_by_year["symbol"]):
            year_count = int((dividends_by_year["symbol"] == sym).sum())
            print(f"  Dividends by year: {sym} = {year_count} year(s)")
        return dividends_by_year

    def _update_last_dividend_decrease(
        self, snapshots: list[TickerSnapshot], div_hist: pd.DataFrame
    ) -> None:
        """Set ``LastDividendDecrease`` on each snapshot."""
        for snap in snapshots:
            snap.LastDividendDecrease = fm.last_dividend_decrease_date_for_ticker(
                snap.Symbol, div_hist
            )
            print(
                f"  Last dividend decrease: {snap.Symbol} = {snap.LastDividendDecrease}"
            )

    def _update_years_since_dividend_decrease(
        self, snapshots: list[TickerSnapshot]
    ) -> None:
        """Set ``YearsSinceDividendDecrease`` from each snapshot's ``LastDividendDecrease``."""
        current_year = date.today().year
        for snap in snapshots:
            snap.YearsSinceDividendDecrease = (
                current_year - snap.LastDividendDecrease.year
            )
            print(
                f"  Years since dividend decrease: "
                f"{snap.Symbol} = {snap.YearsSinceDividendDecrease}"
            )

    def _update_years_consecutive_dividend_increase(
        self, snapshots: list[TickerSnapshot], div_hist: pd.DataFrame
    ) -> None:
        """Set ``YearsConsecutiveDividendIncrease`` on each snapshot."""
        for snap in snapshots:
            snap.YearsConsecutiveDividendIncrease = (
                fm.years_consecutive_dividend_increase_for_ticker(snap.Symbol, div_hist)
            )
            print(
                "  Years consecutive dividend increase: "
                f"{snap.Symbol} = {snap.YearsConsecutiveDividendIncrease}"
            )
