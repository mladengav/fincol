"""CSV-backed cache I/O for fincol (:class:`CsvFincolIo` and helpers)."""

from __future__ import annotations

import csv
from collections.abc import Mapping
from dataclasses import fields
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast, get_type_hints

import pandas as pd
import yfinance as yf

from domain.fincol_io import IFincolIo
from domain.iticker_snapshot import ITickerSnapshot
from infrastructure.yfinance_client import YfTickerSnapshot

from infrastructure import _PROJECT_ROOT


def _parse_date_cell(raw: str) -> date:
    """Parse ISO ``YYYY-MM-DD`` or Unix epoch seconds from a CSV cell into a :class:`~datetime.date`."""
    s = raw.strip()
    if not s:
        return date(1970, 1, 1)
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
        return date(1970, 1, 1)


def _cell_for_ticker_snapshot_field(row: Mapping[str, str | None], field_name: str) -> str:
    """Return the raw string for a :class:`YfTickerSnapshot` field.

    Yahoo ``tickers.csv`` exports use ``exDividendDate`` (epoch or date) for the
    same value as :attr:`YfTickerSnapshot.exDividendDateUtc`.
    """
    v = row.get(field_name)
    if v not in (None, ""):
        return str(v)
    if field_name == "exDividendDateUtc":
        alt = row.get("exDividendDate")
        if alt not in (None, ""):
            return str(alt)
    return ""


_TICKER_SNAPSHOT_CSV_SKIP = frozenset({"ticker", "hist", "divs"})


def _default_tickers_csv_fieldnames() -> list[str]:
    """Header column order for a new ``tickers.csv`` (mirrors :class:`YfTickerSnapshot` minus skipped fields)."""
    names: list[str] = []
    for fld in fields(YfTickerSnapshot):
        if fld.name in _TICKER_SNAPSHOT_CSV_SKIP:
            continue
        if fld.name == "exDividendDateUtc":
            names.append("exDividendDate")
        else:
            names.append(fld.name)
    return names


def _attr_for_tickers_csv_column(column: str) -> str | None:
    """Map a CSV header to the :class:`~domain.iticker_snapshot.ITickerSnapshot` attribute, if any."""
    if column == "exDividendDate":
        return "exDividendDateUtc"
    if column in ("snapshotDate", "symbol", "sectorKey", "industryKey"):
        return column
    return None


def _format_value_for_tickers_csv(value: Any) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _tickers_csv_row_from_snapshot(
    snap: ITickerSnapshot, fieldnames: list[str]
) -> dict[str, str]:
    return {
        col: (
            _format_value_for_tickers_csv(getattr(snap, attr))
            if (attr := _attr_for_tickers_csv_column(col)) is not None
            else ""
        )
        for col in fieldnames
    }


class CsvFincolIo(IFincolIo):
    """IFincolIo backed by CSV files inside a cache folder."""

    _DEFAULT_FOLDER = _PROJECT_ROOT / "cache"
    _TICKERS_CSV = "tickers.csv"
    _TTM_INCOME_CSV = "ttm_income.csv"
    _DIVIDEND_HISTORY_CSV = "dividend_history.csv"

    def __init__(self, folder: Path | None = None) -> None:
        self._folder = folder if folder is not None else self._DEFAULT_FOLDER

    def __repr__(self) -> str:
        return f"CsvFincolIo({self._folder!s})"

    def read_cached_tickers(self, ticker_symbols: list[str]) -> list[ITickerSnapshot]:
        path = self._folder / self._TICKERS_CSV
        if not ticker_symbols or not path.exists() or path.stat().st_size == 0:
            return []

        wanted = set(ticker_symbols)
        hints = get_type_hints(YfTickerSnapshot)
        out: list[ITickerSnapshot] = []

        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None or "symbol" not in reader.fieldnames:
                raise ValueError(f"{path}: CSV must have a 'symbol' column")
            for row in reader:
                sym = row.get("symbol")
                if sym is None or sym == "" or sym not in wanted:
                    continue
                kwargs: dict[str, Any] = {}
                for fld in fields(YfTickerSnapshot):
                    if fld.name in _TICKER_SNAPSHOT_CSV_SKIP:
                        continue
                    raw = _cell_for_ticker_snapshot_field(row, fld.name)
                    typ = hints[fld.name]
                    if typ is date:
                        kwargs[fld.name] = _parse_date_cell(raw)
                    elif typ is str:
                        kwargs[fld.name] = raw
                    else:
                        raise TypeError(
                            f"Unsupported YfTickerSnapshot field {fld.name!r}: {typ!r}"
                        )
                kwargs["ticker"] = yf.Ticker(str(sym))
                out.append(YfTickerSnapshot(**kwargs))
        return out

    def write_tickers_to_cache(self, snapshots: list[ITickerSnapshot]) -> None:
        """Merge ``snapshots`` into ``tickers.csv``.

        Rows whose ``symbol`` matches an incoming snapshot are replaced (last snapshot
        wins for duplicate symbols in ``snapshots``). Other rows are kept in file
        order. Symbols not yet present are appended after existing rows.
        """
        if not snapshots:
            return

        path = self._folder / self._TICKERS_CSV
        path.parent.mkdir(parents=True, exist_ok=True)

        incoming_by_symbol: dict[str, ITickerSnapshot] = {}
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
