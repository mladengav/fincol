"""Debug-only utilities for verbose CLI output."""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def debug_print_divs_structure(divs: pd.Series | pd.DataFrame) -> None:
    """Print ``divs`` dtype, column-like fields, and first-row values (not ``to_string()``)."""
    logger.info("[verbose] snapshot.divs structure")
    logger.info(f"[verbose]   type: {type(divs).__module__}.{type(divs).__name__}")
    logger.info(f"[verbose]   empty: {getattr(divs, 'empty', True)}")
    if getattr(divs, "empty", True):
        return
    if isinstance(divs, pd.DataFrame):
        cols = list(divs.columns)
        logger.info(f"[verbose]   columns ({len(cols)}): {cols}")
        row0 = divs.iloc[0]
        for col in cols:
            logger.info(
                f"[verbose]   first row [{col!r}]: {row0[col]!r}  (column dtype: {divs[col].dtype})"
            )
        return
    # Series (typical for yfinance ``Ticker.dividends``)
    logger.info(f"[verbose]   Series.name: {divs.name!r}")
    logger.info(f"[verbose]   Series.dtype: {divs.dtype}")
    logger.info(
        f"[verbose]   index: {type(divs.index).__name__}, name={divs.index.name!r}"
    )
    if isinstance(divs.index, pd.MultiIndex):
        logger.info(f"[verbose]   MultiIndex level names: {list(divs.index.names)}")
    tab = divs.head(1).reset_index()
    cols = list(tab.columns)
    logger.info(f"[verbose]   columns after reset_index() ({len(cols)}): {cols}")
    row0 = tab.iloc[0]
    for col in cols:
        logger.info(f"[verbose]   first row [{col!r}]: {row0[col]!r}")
