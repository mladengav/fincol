"""JSON IO for fincol input files.

Defines the :class:`ISymbolLoader` Protocol (the abstract surface used by
:mod:`fincol`) and :class:`JsonSymbolLoader`, the concrete JSON-backed
implementation that encapsulates its source path.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class ISymbolLoader(Protocol):
    """Source of symbol / position records consumed by :mod:`fincol`."""

    def load_symbols(self) -> list[str]:
        ...

    def load_symbols_with_quantities(self) -> list[tuple[str, float]]:
        ...


class JsonSymbolLoader(ISymbolLoader):
    """:class:`ISymbolLoader` backed by a JSON array of ``{"symbol", "quantity"}`` objects at a fixed path."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def __repr__(self) -> str:
        return f"JsonSymbolLoader({self._path!s})"

    def load_symbols(self) -> list[str]:
        """Load ticker symbols from the configured JSON file; each object should have a ``symbol`` key."""
        data = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError(f"JSON root must be an array, got {type(data).__name__}")
        symbols: list[str] = []
        for item in data:
            if isinstance(item, dict) and "symbol" in item and item["symbol"] is not None:
                symbols.append(str(item["symbol"]))
        return symbols

    def load_symbols_with_quantities(self) -> list[tuple[str, float]]:
        """Load ``(symbol, quantity)`` from the configured JSON file; each object needs ``symbol`` and ``quantity``."""
        data = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError(f"JSON root must be an array, got {type(data).__name__}")
        rows: list[tuple[str, float]] = []
        for item in data:
            if not isinstance(item, dict) or "symbol" not in item or item["symbol"] is None:
                continue
            q = item.get("quantity")
            if q is None:
                raise ValueError(
                    f"Each object with 'symbol' must include 'quantity': {item!r}"
                )
            rows.append((str(item["symbol"]), float(q)))
        return rows
