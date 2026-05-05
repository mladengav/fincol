"""CSV IO for fincol input files.

Defines :class:`CsvSymbolLoader`, a concrete :class:`~json_io.ISymbolLoader`
backed by a CSV file whose header includes at least ``symbol`` and
``quantity`` columns. Mirrors :class:`json_io.JsonSymbolLoader` in shape and
validation, using only the standard library.
"""
from __future__ import annotations

import csv
from pathlib import Path
import pandas as pd

from fincol_io import ISymbolLoader, IFincolIo


class CsvSymbolLoader(ISymbolLoader):
    """:class:`ISymbolLoader` backed by a CSV file with ``symbol`` and ``quantity`` columns at a fixed path."""

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
    
    _DEFAULT_FOLDER = Path(__file__).resolve().parent / "cache"
    _TTM_INCOME_CSV = "ttm_income.csv"
    _DIVIDEND_HISTORY_CSV = "dividend_history.csv"


    def __init__(self, folder: Path | None = None) -> None:
        self._folder = folder if folder is not None else self._DEFAULT_FOLDER
    

    def __repr__(self) -> str:
        return f"CsvFincolIo({self._folder!s})"

    
    def read_ttm_income(self) -> pd.DataFrame:
        path = self._folder / self._TTM_INCOME_CSV
        
        if path.exists() and path.stat().st_size > 0:
            try:
                ttm_income = pd.read_csv(path)
            except (pd.errors.EmptyDataError, pd.errors.ParserError):
                ttm_income = pd.DataFrame(columns=["ticker", "ttm_dividend"])
        else:
            ttm_income = pd.DataFrame(columns=["ticker", "ttm_dividend"])

        return ttm_income


    def write_ttm_income(self, body: pd.DataFrame) -> None:
        path = self._folder / self._TTM_INCOME_CSV

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as f:
            f.write('"ticker","ttm_dividend"\n')
            for _, row in body.iterrows():
                f.write(f'"{row["ticker"]}",{row["ttm_dividend"]:.4f}\n')


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

