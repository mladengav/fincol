"""Derived cache fields (for example TTM dividend income per ticker)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Protocol, runtime_checkable

from application import fincol_math as fm
from domain.fincol_io import IFincolIo

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
        """Update aggregations for ``symbols`` via ``fincol_io``.

        ``symbols`` is not yet used to limit work; callers must pass the tickers
        that were updated so partial recomputation can be added later.
        """
        self._update_ttm_dividend()
        self._update_dividends_by_year()
        last_decrease_by_ticker = self._update_last_dividend_decrease()
        self._update_years_since_dividend_decrease(last_decrease_by_ticker)
        self._update_years_consecutive_dividend_increase()

    def _update_ttm_dividend(self) -> None:
        """Write TTM income via ``fincol_io``."""

        div_hist = self.fincol_io.read_dividend_history()
        ttm_by_ticker: dict[str, float] = {}

        unique_tickers = list(dict.fromkeys(div_hist["ticker"]))

        for sym in unique_tickers:
            ttm_by_ticker[sym] = fm.ttm_per_share_for_ticker(sym, div_hist)
        self.fincol_io.write_ttm_income(ttm_by_ticker)

        print(f"Loaded {len(unique_tickers)} ticker(s) from {self.fincol_io!r}")
        for sym in unique_tickers:
            print(
                f"  TTM dividend income (last {fm.TTM_NUM_PAYMENTS} payments): {sym} = {ttm_by_ticker[sym]:.4f}"
            )

        print(f"Wrote TTM income to {self.fincol_io!r}")

    def _update_dividends_by_year(self) -> None:
        """Write per-symbol annual dividend totals via ``fincol_io``."""

        div_hist = self.fincol_io.read_dividend_history()
        dividends_by_year = fm.dividends_by_year_from_history(div_hist)
        self.fincol_io.write_dividends_by_year(dividends_by_year)

        symbols = list(dict.fromkeys(dividends_by_year["symbol"]))
        print(f"Loaded {len(symbols)} symbol(s) from {self.fincol_io!r}")
        for sym in symbols:
            sub = dividends_by_year[dividends_by_year["symbol"] == sym]
            year_count = len(sub)
            print(f"  Dividends by year: {sym} = {year_count} year(s)")
        print(f"Wrote dividends by year to {self.fincol_io!r}")

    def _update_last_dividend_decrease(self) -> dict[str, date]:
        """Write last dividend decrease date per ticker via ``fincol_io``."""

        div_hist = self.fincol_io.read_dividend_history()
        last_decrease_by_ticker: dict[str, date] = {}

        unique_tickers = list(dict.fromkeys(div_hist["ticker"]))

        for sym in unique_tickers:
            last_decrease_by_ticker[sym] = fm.last_dividend_decrease_date_for_ticker(
                sym, div_hist
            )
        self.fincol_io.write_last_dividend_decrease(last_decrease_by_ticker)

        print(f"Loaded {len(unique_tickers)} ticker(s) from {self.fincol_io!r}")
        for sym in unique_tickers:
            print(f"  Last dividend decrease: {sym} = {last_decrease_by_ticker[sym]}")

        print(f"Wrote last dividend decrease to {self.fincol_io!r}")
        return last_decrease_by_ticker

    def _update_years_since_dividend_decrease(
        self,
        last_decrease_by_ticker: Mapping[str, date],
    ) -> None:
        """Write years since last dividend decrease per ticker via ``fincol_io``."""

        current_year = date.today().year
        years_since_by_ticker = {
            sym: current_year - last_decrease.year
            for sym, last_decrease in last_decrease_by_ticker.items()
        }
        self.fincol_io.write_years_since_dividend_decrease(years_since_by_ticker)

        print(f"Loaded {len(years_since_by_ticker)} ticker(s) from {self.fincol_io!r}")
        for sym in sorted(years_since_by_ticker):
            print(
                f"  Years since dividend decrease: {sym} = {years_since_by_ticker[sym]}"
            )

        print(f"Wrote years since dividend decrease to {self.fincol_io!r}")

    def _update_years_consecutive_dividend_increase(self) -> None:
        """Write consecutive years of dividend increases per ticker via ``fincol_io``."""

        div_hist = self.fincol_io.read_dividend_history()
        years_consecutive_by_ticker: dict[str, int] = {}

        unique_tickers = list(dict.fromkeys(div_hist["ticker"]))

        for sym in unique_tickers:
            years_consecutive_by_ticker[sym] = (
                fm.years_consecutive_dividend_increase_for_ticker(sym, div_hist)
            )
        self.fincol_io.write_years_consecutive_dividend_increase(
            years_consecutive_by_ticker
        )

        print(f"Loaded {len(unique_tickers)} ticker(s) from {self.fincol_io!r}")
        for sym in sorted(years_consecutive_by_ticker):
            print(
                "  Years consecutive dividend increase: "
                f"{sym} = {years_consecutive_by_ticker[sym]}"
            )

        print(f"Wrote years consecutive dividend increase to {self.fincol_io!r}")
