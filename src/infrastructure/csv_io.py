"""CSV IO for fincol input files.

Defines :class:`CsvSymbolLoader`, a concrete :class:`~domain.fincol_io.ISymbolLoader`
backed by a CSV file whose header includes at least ``symbol`` and
``quantity`` columns.
"""

from __future__ import annotations

import csv
import os
from collections.abc import Mapping
from pathlib import Path

import pandas as pd
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

from domain.fincol_io import IFincolIo, ISymbolLoader

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


class CsvFincolIo(IFincolIo):
    """IFincolIo backed by CSV files inside a cache folder."""

    _DEFAULT_FOLDER = _PROJECT_ROOT / "cache"
    _TTM_INCOME_CSV = "ttm_income.csv"
    _DIVIDEND_HISTORY_CSV = "dividend_history.csv"

    def __init__(self, folder: Path | None = None) -> None:
        self._folder = folder if folder is not None else self._DEFAULT_FOLDER

    def __repr__(self) -> str:
        return f"CsvFincolIo({self._folder!s})"

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
                try:
                    result[str(ticker)] = (
                        float(value) if value not in (None, "") else 0.0
                    )
                except (TypeError, ValueError) as e:
                    raise ValueError(
                        f"{path}:{i}: bad ttm_dividend value {value!r} for {ticker!r}"
                    ) from e
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
            except (pd.errors.EmptyDataError, pd.errors.ParserError):
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
