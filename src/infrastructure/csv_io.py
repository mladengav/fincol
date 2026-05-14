"""CSV IO for fincol input files.

Defines :class:`CsvSymbolLoader`, a concrete :class:`~domain.fincol_io.ISymbolLoader`
backed by a CSV file whose header includes at least ``symbol`` and
``quantity`` columns.
"""

from __future__ import annotations

import csv
import os
from collections.abc import Mapping
from dataclasses import fields
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast, get_type_hints

import pandas as pd
import yfinance as yf
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

from domain.fincol_io import IFincolIo, ISymbolLoader
from domain.iticker_snapshot import ITickerSnapshot
from infrastructure.yfinance_client import TickerSnapshot

# Repo / install layout root (parent of ``infrastructure/``): default cache and ``.env`` live here.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class CsvSymbolLoader(ISymbolLoader):
    """:class:`~domain.fincol_io.ISymbolLoader` backed by a CSV file with ``symbol`` and ``quantity`` columns at a fixed path."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def __repr__(self) -> str:
        return f"CsvSymbolLoader({self._path!s})"

    def load_symbols(self) -> list[str]:
        """Load ticker symbols from the configured CSV file; the header must include a ``symbol`` column."""
        with self._path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None or "symbol" not in reader.fieldnames:
                raise ValueError("CSV must have a 'symbol' column")
            symbols: list[str] = []
            for row in reader:
                sym = row.get("symbol")
                if sym is None or sym == "":
                    continue
                symbols.append(str(sym))
        return symbols

    def load_symbols_with_quantities(self) -> list[tuple[str, float]]:
        """Load ``(symbol, quantity)`` from the configured CSV file; the header must include both columns."""
        with self._path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None or "symbol" not in reader.fieldnames:
                raise ValueError("CSV must have a 'symbol' column")
            if "quantity" not in reader.fieldnames:
                raise ValueError("CSV must have a 'quantity' column")
            rows: list[tuple[str, float]] = []
            for row in reader:
                sym = row.get("symbol")
                if sym is None or sym == "":
                    continue
                q = row.get("quantity")
                if q is None or q == "":
                    raise ValueError(
                        f"Row with 'symbol' must include 'quantity': {row!r}"
                    )
                rows.append((str(sym), float(q)))
        return rows


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
    """Return the raw string for a :class:`TickerSnapshot` field.

    Yahoo ``tickers.csv`` exports use ``exDividendDate`` (epoch or date) for the
    same value as :attr:`TickerSnapshot.exDividendDateUtc`.
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
    """Header column order for a new ``tickers.csv`` (mirrors :class:`TickerSnapshot` minus skipped fields)."""
    names: list[str] = []
    for fld in fields(TickerSnapshot):
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
        hints = get_type_hints(TickerSnapshot)
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
                for fld in fields(TickerSnapshot):
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
                            f"Unsupported TickerSnapshot field {fld.name!r}: {typ!r}"
                        )
                kwargs["ticker"] = yf.Ticker(str(sym))
                out.append(TickerSnapshot(**kwargs))
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


class AzBlobCsvFincolIo(CsvFincolIo):
    """CsvFincolIo backed by Azure Blob Storage with a local cache folder mirror."""

    _CONTAINER_NAME = "csvcache"

    def __init__(self, folder: Path | None = None) -> None:
        super().__init__(folder=folder)
        self._folder.mkdir(parents=True, exist_ok=True)

        load_dotenv(_PROJECT_ROOT / ".env")
        storage_url = os.environ["AZURE_STORAGE_BLOB_URL"]
        credential = DefaultAzureCredential()
        self._container_client = BlobServiceClient(
            account_url=storage_url,
            credential=credential,
        ).get_container_client(self._CONTAINER_NAME)

        self._sync_from_azure()

    def _sync_from_azure(self) -> None:
        for blob in self._container_client.list_blobs():
            target = self._folder / blob.name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb") as f:
                download_stream = self._container_client.download_blob(blob.name)
                f.write(download_stream.readall())

    def _sync_to_azure(self) -> None:
        for path in self._folder.rglob("*"):
            if not path.is_file():
                continue
            blob_name = str(path.relative_to(self._folder)).replace("\\", "/")
            with path.open("rb") as data:
                self._container_client.upload_blob(
                    name=blob_name, data=data, overwrite=True
                )

    def write_ttm_income(self, ttm_by_ticker: Mapping[str, float]) -> None:
        super().write_ttm_income(ttm_by_ticker)
        self._sync_to_azure()

    def write_dividend_history(self, body: pd.DataFrame) -> None:
        super().write_dividend_history(body)
        self._sync_to_azure()

    def write_tickers_to_cache(self, snapshots: list[ITickerSnapshot]) -> None:
        super().write_tickers_to_cache(snapshots)
        self._sync_to_azure()
