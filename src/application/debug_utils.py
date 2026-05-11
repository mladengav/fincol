"""Debug-only utilities for verbose CLI output."""
from __future__ import annotations

import pandas as pd


def debug_print_divs_structure(divs: pd.Series | pd.DataFrame) -> None:
    """Print ``divs`` dtype, column-like fields, and first-row values (not ``to_string()``)."""
    print("[debug] snapshot.divs structure")
    print(f"[debug]   type: {type(divs).__module__}.{type(divs).__name__}")
    print(f"[debug]   empty: {getattr(divs, 'empty', True)}")
    if getattr(divs, "empty", True):
        return
    if isinstance(divs, pd.DataFrame):
        cols = list(divs.columns)
        print(f"[debug]   columns ({len(cols)}): {cols}")
        row0 = divs.iloc[0]
        for col in cols:
            print(f"[debug]   first row [{col!r}]: {row0[col]!r}  (column dtype: {divs[col].dtype})")
        return
    # Series (typical for yfinance ``Ticker.dividends``)
    print(f"[debug]   Series.name: {divs.name!r}")
    print(f"[debug]   Series.dtype: {divs.dtype}")
    print(f"[debug]   index: {type(divs.index).__name__}, name={divs.index.name!r}")
    if isinstance(divs.index, pd.MultiIndex):
        print(f"[debug]   MultiIndex level names: {list(divs.index.names)}")
    tab = divs.head(1).reset_index()
    cols = list(tab.columns)
    print(f"[debug]   columns after reset_index() ({len(cols)}): {cols}")
    row0 = tab.iloc[0]
    for col in cols:
        print(f"[debug]   first row [{col!r}]: {row0[col]!r}")
