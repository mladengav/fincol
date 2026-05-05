"""CSV IO for fincol input files.

Defines :class:`CsvSymbolLoader`, a concrete :class:`~json_io.ISymbolLoader`
backed by a CSV file whose header includes at least ``symbol`` and
``quantity`` columns. Mirrors :class:`json_io.JsonSymbolLoader` in shape and
validation, using only the standard library.
"""
from __future__ import annotations

import csv
from pathlib import Path

from json_io import ISymbolLoader


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
