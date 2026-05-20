"""CSV-backed cache I/O for fincol (:class:`CsvFincolIo` and helpers)."""

from __future__ import annotations

import csv
from collections.abc import Mapping
from dataclasses import fields
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast, get_type_hints

import pandas as pd
import yfinance as yf

from domain.fincol_io import IFincolIo
from domain.ticker_snapshot import TickerSnapshot
from infrastructure import _PROJECT_ROOT

def _parse_date_cell(raw: str) -> date:
    """Parse ISO ``YYYY-MM-DD`` or Unix epoch seconds from a CSV cell into a :class:`~datetime.date`."""
    s = raw.strip()
    if not s:
        return date(1900, 1, 1)
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            pass
    try:
        ts = float(s)
        if ts > 1e12:
            ts /= 1000.0
        return datetime.fromtimestamp(ts, tz=UTC).date()
    except (ValueError, OSError, OverflowError):
        return date(1900, 1, 1)


def _parse_datetime_cell(raw: str) -> datetime:
    """Parse ISO datetime or Unix epoch seconds from a CSV cell into UTC :class:`~datetime.datetime`."""
    s = raw.strip()
    if not s:
        return datetime(1900, 1, 1, tzinfo=UTC)
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            pass
    try:
        ts = float(s)
        if ts > 1e12:
            ts /= 1000.0
        return datetime.fromtimestamp(ts, tz=UTC)
    except (ValueError, OSError, OverflowError):
        return datetime(1900, 1, 1, tzinfo=UTC)


_EMPTY_DECIMAL = Decimal("0.00")
_TICKER_SNAPSHOT_CSV_ATTRS = frozenset(
    f.name for f in fields(TickerSnapshot)
)


def _parse_decimal_cell(raw: str) -> Decimal:
    s = raw.strip()
    if not s:
        return _EMPTY_DECIMAL
    return Decimal(s)


def _parse_int_cell(raw: str) -> int:
    s = raw.strip()
    if not s:
        return 0
    return int(float(s))


def _parse_float_cell(raw: str) -> float:
    s = raw.strip()
    if not s:
        return 0.0
    return float(s)


def _default_tickers_csv_fieldnames() -> list[str]:
    """Header column order for a new ``tickers.csv`` (mirrors :class:`TickerSnapshot`)."""
    return [fld.name for fld in fields(TickerSnapshot)]


def _format_value_for_tickers_csv(value: Any) -> str:
    if isinstance(value, datetime):
        dt = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return str(int(dt.timestamp()))
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value)
    return str(value)


def _tickers_csv_row_from_snapshot(
    snap: TickerSnapshot, fieldnames: list[str]
) -> dict[str, str]:
    return {
        col: (
            _format_value_for_tickers_csv(getattr(snap, col))
            if col in _TICKER_SNAPSHOT_CSV_ATTRS
            else ""
        )
        for col in fieldnames
    }


class CsvFincolIo(IFincolIo):
    """IFincolIo backed by CSV files inside a cache folder."""

    _DEFAULT_FOLDER = _PROJECT_ROOT / "cache"
    _TICKERS_CSV = "tickers.csv"
    _AGGREGATIONS_SUBDIR = "aggregations"
    _TTM_INCOME_CSV = Path(_AGGREGATIONS_SUBDIR) / "ttm_income.csv"
    _LAST_DIVIDEND_DECREASE_CSV = (
        Path(_AGGREGATIONS_SUBDIR) / "last_dividend_decrease.csv"
    )
    _YEARS_SINCE_DIVIDEND_DECREASE_CSV = (
        Path(_AGGREGATIONS_SUBDIR) / "years_since_dividend_decrease.csv"
    )
    _DIVIDENDS_BY_YEAR_CSV = Path(_AGGREGATIONS_SUBDIR) / "dividends_by_year.csv"
    _YEARS_CONSECUTIVE_DIVIDEND_INCREASE_CSV = (
        Path(_AGGREGATIONS_SUBDIR) / "years_consecutive_dividend_increase.csv"
    )
    _DIVIDEND_HISTORY_CSV = "dividend_history.csv"

    def __init__(self, folder: Path | None = None) -> None:
        self._folder = folder if folder is not None else self._DEFAULT_FOLDER

    def __repr__(self) -> str:
        return f"CsvFincolIo({self._folder!s})"

    def read_cached_tickers(self, ticker_symbols: list[str]) -> list[TickerSnapshot]:
        path = self._folder / self._TICKERS_CSV
        if not ticker_symbols or not path.exists() or path.stat().st_size == 0:
            return []

        wanted = set(ticker_symbols)
        hints = get_type_hints(TickerSnapshot)
        out: list[TickerSnapshot] = []

        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None or "symbol" not in reader.fieldnames:
                raise ValueError(f"{path}: CSV must have a 'symbol' column")
            for row in reader:
                sym = row.get("symbol")
                if sym is None or sym == "" or sym not in wanted:
                    continue
                kwargs: dict[str, Any] = {}
                for fld in fields(TickerSnapshot):
                    raw = str(row.get(fld.name) or "")
                    typ = hints[fld.name]
                    if typ is date:
                        kwargs[fld.name] = _parse_date_cell(raw)
                    elif typ is datetime:
                        kwargs[fld.name] = _parse_datetime_cell(raw)
                    elif typ is str:
                        kwargs[fld.name] = raw
                    elif typ is Decimal:
                        kwargs[fld.name] = _parse_decimal_cell(raw)
                    elif typ is int:
                        kwargs[fld.name] = _parse_int_cell(raw)
                    elif typ is float:
                        kwargs[fld.name] = _parse_float_cell(raw)
                    else:
                        raise TypeError(
                            f"Unsupported TickerSnapshot field {fld.name!r}: {typ!r}"
                        )
                out.append(TickerSnapshot(**kwargs))
        return out

    def write_tickers_to_cache(self, snapshots: list[TickerSnapshot]) -> None:
        """Merge ``snapshots`` into ``tickers.csv``.

        Rows whose ``symbol`` matches an incoming snapshot are replaced (last snapshot
        wins for duplicate symbols in ``snapshots``). Other rows are kept in file
        order. Symbols not yet present are appended after existing rows.
        """
        if not snapshots:
            return

        path = self._folder / self._TICKERS_CSV
        path.parent.mkdir(parents=True, exist_ok=True)

        incoming_by_symbol: dict[str, TickerSnapshot] = {}
        incoming_order: list[str] = []
        for snap in snapshots:
            sym = snap.symbol
            if sym not in incoming_by_symbol:
                incoming_order.append(sym)
            incoming_by_symbol[sym] = snap

        if path.exists() and path.stat().st_size > 0:
            with path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                fieldnames = (
                    list(reader.fieldnames)
                    if reader.fieldnames
                    else _default_tickers_csv_fieldnames()
                )
                if "symbol" not in fieldnames:
                    raise ValueError(f"{path}: CSV must have a 'symbol' column")
                existing_rows = list(reader)

            replaced_emitted: set[str] = set()
            out_rows: list[dict[str, str]] = []
            for row in existing_rows:
                sym = (row.get("symbol") or "").strip()
                if sym in incoming_by_symbol:
                    if sym not in replaced_emitted:
                        out_rows.append(
                            _tickers_csv_row_from_snapshot(
                                incoming_by_symbol[sym], fieldnames
                            )
                        )
                        replaced_emitted.add(sym)
                    continue
                out_rows.append({k: (row.get(k) or "") for k in fieldnames})

            for sym in incoming_order:
                if sym not in replaced_emitted:
                    out_rows.append(
                        _tickers_csv_row_from_snapshot(
                            incoming_by_symbol[sym], fieldnames
                        )
                    )
        else:
            fieldnames = _default_tickers_csv_fieldnames()
            out_rows = [
                _tickers_csv_row_from_snapshot(incoming_by_symbol[sym], fieldnames)
                for sym in incoming_order
            ]

        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=fieldnames,
                extrasaction="ignore",
                quoting=csv.QUOTE_MINIMAL,
            )
            writer.writeheader()
            for row in out_rows:
                writer.writerow(row)

    def read_ttm_income(self) -> dict[str, float]:
        path = self._folder / self._TTM_INCOME_CSV

        if not (path.exists() and path.stat().st_size > 0):
            return {}

        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            missing = {"ticker", "ttm_dividend"} - set(reader.fieldnames or [])
            if missing:
                raise ValueError(
                    f"{path}: missing required column(s): {sorted(missing)}"
                )
            result: dict[str, float] = {}
            for i, row in enumerate(reader, start=2):
                ticker = row.get("ticker")
                value = row.get("ttm_dividend")
                if not ticker:
                    raise ValueError(f"{path}:{i}: empty ticker")
                if value in (None, ""):
                    amount = 0.0
                else:
                    try:
                        amount = float(cast(str, value))
                    except (TypeError, ValueError) as e:
                        raise ValueError(
                            f"{path}:{i}: bad ttm_dividend value {value!r} for {ticker!r}"
                        ) from e
                result[str(ticker)] = amount
        return result

    def write_ttm_income(self, ttm_by_ticker: Mapping[str, float]) -> None:
        path = self._folder / self._TTM_INCOME_CSV

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as f:
            f.write('"ticker","ttm_dividend"\n')
            for ticker in sorted(ttm_by_ticker):
                f.write(f'"{ticker}",{float(ttm_by_ticker[ticker]):.4f}\n')

    def read_last_dividend_decrease(self) -> dict[str, date]:
        path = self._folder / self._LAST_DIVIDEND_DECREASE_CSV

        if not (path.exists() and path.stat().st_size > 0):
            return {}

        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            missing = {"ticker", "last_dividend_decrease"} - set(reader.fieldnames or [])
            if missing:
                raise ValueError(
                    f"{path}: missing required column(s): {sorted(missing)}"
                )
            result: dict[str, date] = {}
            for i, row in enumerate(reader, start=2):
                ticker = row.get("ticker")
                value = row.get("last_dividend_decrease")
                if not ticker:
                    raise ValueError(f"{path}:{i}: empty ticker")
                if value in (None, ""):
                    result[str(ticker)] = date(1900, 1, 1)
                else:
                    result[str(ticker)] = _parse_date_cell(str(value))
        return result

    def write_last_dividend_decrease(
        self, last_decrease_by_ticker: Mapping[str, date]
    ) -> None:
        path = self._folder / self._LAST_DIVIDEND_DECREASE_CSV

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as f:
            f.write('"ticker","last_dividend_decrease"\n')
            for ticker in sorted(last_decrease_by_ticker):
                d = last_decrease_by_ticker[ticker]
                f.write(f'"{ticker}","{d.isoformat()}"\n')

    def read_years_since_dividend_decrease(self) -> dict[str, int]:
        path = self._folder / self._YEARS_SINCE_DIVIDEND_DECREASE_CSV

        if not (path.exists() and path.stat().st_size > 0):
            return {}

        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            missing = {"ticker", "years_since_dividend_decrease"} - set(
                reader.fieldnames or []
            )
            if missing:
                raise ValueError(
                    f"{path}: missing required column(s): {sorted(missing)}"
                )
            result: dict[str, int] = {}
            for i, row in enumerate(reader, start=2):
                ticker = row.get("ticker")
                value = row.get("years_since_dividend_decrease")
                if not ticker:
                    raise ValueError(f"{path}:{i}: empty ticker")
                if value in (None, ""):
                    years = 0
                else:
                    try:
                        years = int(float(cast(str, value)))
                    except (TypeError, ValueError) as e:
                        raise ValueError(
                            f"{path}:{i}: bad years_since_dividend_decrease "
                            f"value {value!r} for {ticker!r}"
                        ) from e
                result[str(ticker)] = years
        return result

    def write_years_since_dividend_decrease(
        self, years_since_by_ticker: Mapping[str, int]
    ) -> None:
        path = self._folder / self._YEARS_SINCE_DIVIDEND_DECREASE_CSV

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as f:
            f.write('"ticker","years_since_dividend_decrease"\n')
            for ticker in sorted(years_since_by_ticker):
                f.write(f'"{ticker}",{int(years_since_by_ticker[ticker])}\n')

    def read_years_consecutive_dividend_increase(self) -> dict[str, int]:
        path = self._folder / self._YEARS_CONSECUTIVE_DIVIDEND_INCREASE_CSV

        if not (path.exists() and path.stat().st_size > 0):
            return {}

        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            missing = {"ticker", "years_consecutive_dividend_increase"} - set(
                reader.fieldnames or []
            )
            if missing:
                raise ValueError(
                    f"{path}: missing required column(s): {sorted(missing)}"
                )
            result: dict[str, int] = {}
            for i, row in enumerate(reader, start=2):
                ticker = row.get("ticker")
                value = row.get("years_consecutive_dividend_increase")
                if not ticker:
                    raise ValueError(f"{path}:{i}: empty ticker")
                if value in (None, ""):
                    years = 0
                else:
                    try:
                        years = int(float(cast(str, value)))
                    except (TypeError, ValueError) as e:
                        raise ValueError(
                            f"{path}:{i}: bad years_consecutive_dividend_increase "
                            f"value {value!r} for {ticker!r}"
                        ) from e
                result[str(ticker)] = years
        return result

    def write_years_consecutive_dividend_increase(
        self, years_consecutive_by_ticker: Mapping[str, int]
    ) -> None:
        path = self._folder / self._YEARS_CONSECUTIVE_DIVIDEND_INCREASE_CSV

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as f:
            f.write('"ticker","years_consecutive_dividend_increase"\n')
            for ticker in sorted(years_consecutive_by_ticker):
                f.write(
                    f'"{ticker}",{int(years_consecutive_by_ticker[ticker])}\n'
                )

    def read_dividends_by_year(self) -> pd.DataFrame:
        path = self._folder / self._DIVIDENDS_BY_YEAR_CSV
        empty = pd.DataFrame(columns=["symbol", "year", "dividend"])

        if not (path.exists() and path.stat().st_size > 0):
            return empty

        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            missing = {"symbol", "year", "dividend"} - set(reader.fieldnames or [])
            if missing:
                raise ValueError(
                    f"{path}: missing required column(s): {sorted(missing)}"
                )
            rows: list[dict[str, str | int | float]] = []
            for i, row in enumerate(reader, start=2):
                symbol = row.get("symbol")
                year_raw = row.get("year")
                dividend_raw = row.get("dividend")
                if not symbol:
                    raise ValueError(f"{path}:{i}: empty symbol")
                if year_raw in (None, ""):
                    raise ValueError(f"{path}:{i}: empty year for {symbol!r}")
                if dividend_raw in (None, ""):
                    dividend = 0.0
                else:
                    try:
                        dividend = float(cast(str, dividend_raw))
                    except (TypeError, ValueError) as e:
                        raise ValueError(
                            f"{path}:{i}: bad dividend value {dividend_raw!r} for {symbol!r}"
                        ) from e
                try:
                    year = int(float(cast(str, year_raw)))
                except (TypeError, ValueError) as e:
                    raise ValueError(
                        f"{path}:{i}: bad year value {year_raw!r} for {symbol!r}"
                    ) from e
                rows.append({"symbol": str(symbol), "year": year, "dividend": dividend})
        return pd.DataFrame(rows)

    def write_dividends_by_year(self, dividends_by_year: pd.DataFrame) -> None:
        path = self._folder / self._DIVIDENDS_BY_YEAR_CSV

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as f:
            f.write('"symbol","year","dividend"\n')
            for _, row in dividends_by_year.iterrows():
                f.write(
                    f'"{row["symbol"]}",{int(row["year"])},'
                    f'{float(row["dividend"]):.4f}\n'
                )

    def read_dividend_history(self) -> pd.DataFrame:
        path = self._folder / self._DIVIDEND_HISTORY_CSV

        if path.exists() and path.stat().st_size > 0:
            try:
                dividend_history = pd.read_csv(path)
            except pd.errors.EmptyDataError, pd.errors.ParserError:
                dividend_history = pd.DataFrame(columns=["ticker", "date", "amount"])
        else:
            dividend_history = pd.DataFrame(columns=["ticker", "date", "amount"])

        return dividend_history

    def write_dividend_history(self, body: pd.DataFrame) -> None:
        path = self._folder / self._DIVIDEND_HISTORY_CSV

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as f:
            f.write('"ticker","date","amount"\n')
            for _, row in body.iterrows():
                f.write(f'"{row["ticker"]}","{row["date"]}",{row["amount"]:.4f}\n')

    def update_dividend_history(self, new_dividends: pd.DataFrame) -> int:
        existing = self.read_dividend_history()

        combined = pd.concat([existing, new_dividends], ignore_index=True)
        combined = combined.drop_duplicates(
            subset=["ticker", "date", "amount"], keep="first"
        )
        combined = combined.sort_values(
            ["ticker", "date"], kind="mergesort"
        ).reset_index(drop=True)

        rows_added = len(combined) - len(existing)

        self.write_dividend_history(combined)

        return rows_added
