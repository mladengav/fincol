"""
CLI entry: raw dividend output vs. return computation for a symbol.
Internal layout: :mod:`yfinance_client` snapshot → :mod:`domain` math → services → argparse.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

import domain as dom
from debug_utils import debug_print_divs_structure
from fincol_io import ISymbolLoader, IFincolIo
from csv_io import CsvSymbolLoader, CsvFincolIo
from json_io import JsonSymbolLoader

import yfinance_client as yf_client
from yfinance_client import TickerSnapshot

# ---------------------------------------------------------------------------
# Services: orchestration (each mode uses its own progressive load sequence)
# ---------------------------------------------------------------------------


def run_raw_div(symbol: str, *, verbose: bool = False) -> TickerSnapshot:
    """``load_ticker`` + ``with_dividends``; print raw ex-dividend series (no price history)."""
    snapshot = yf_client.load_ticker(symbol).with_dividends()
    print(f"Dividends (ex-dates) for {snapshot.symbol}")
    if verbose:
        debug_print_divs_structure(snapshot.divs)
    print(snapshot.divs.to_string() if not snapshot.divs.empty else "(no dividends in series)")
    
    return snapshot


_TOTAL_INCOME_LABEL = "total_income"


def run_load_dividend_history(symbols: list[str], fincol_io: IFincolIo) -> None:
    """Like :func:`run_raw_div`, plus append deduplicated rows to ``cache/dividend_history.csv``.

    Loads data per ticker, concatenates new rows, then reads/writes cache once.
    Input symbols are deduplicated (first occurrence wins) before fetch.
    """
    unique = list[str](dict.fromkeys(symbols))
    if not unique:
        return

    frames: list[pd.DataFrame] = []
    for symbol in unique:
        snapshot = run_raw_div(symbol)
        frames.append(yf_client.dividends_to_history_frame(snapshot.symbol, snapshot.divs))

    new_df = pd.concat(frames, ignore_index=True)
    x_retrieved = len(new_df)

    rows_added = fincol_io.update_dividend_history(new_df)
    
    z_filtered = x_retrieved - rows_added

    ticker_note = unique[0] if len(unique) == 1 else f"{len(unique)} ticker(s)"
    print(
        f"{x_retrieved} rows retrieved ({ticker_note}), "
        f"{rows_added} rows added, {z_filtered} duplicate rows filtered out"
    )

def _merge_and_write_ttm_income(
    processed: list[tuple[str, float]],
    ttm_by_ticker: dict[str, float],
    fincol_io: IFincolIo,
) -> float:
    """Calculate TTM income for each ticker and write to the cache. Rows for this run replace any prior rows for the same tickers; append ``total_income`` last.

    Returns the portfolio total (same value as the ``total_income`` row).
    """
    processed_set = {t for t, _ in processed}

    new_rows = pd.DataFrame(
        [
            {
                "ticker": t,
                "ttm_dividend": ttm_by_ticker.get(t, 0.0),
            }
            for t, _ in processed
        ]
    )

    existing = fincol_io.read_ttm_income()

    if not existing.empty:
        existing = existing[existing["ticker"].astype(str) != _TOTAL_INCOME_LABEL]
        existing = existing[~existing["ticker"].astype(str).isin(processed_set)]

    combined = pd.concat([existing, new_rows], ignore_index=True)
    if not combined.empty:
        combined = combined.drop_duplicates(subset=["ticker"], keep="last")
        combined = combined.sort_values("ticker", kind="mergesort").reset_index(drop=True)
        combined["ttm_dividend"] = pd.to_numeric(combined["ttm_dividend"], errors="coerce").fillna(0.0)

    ticker_total = 0.0
    if not combined.empty:
        ticker_total = float(
            combined[combined["ticker"].astype(str) != _TOTAL_INCOME_LABEL]["ttm_dividend"].sum()
        )
    out = pd.concat(
        [
            combined,
            pd.DataFrame(
                [{"ticker": _TOTAL_INCOME_LABEL, "ttm_dividend": ticker_total}]
            ),
        ],
        ignore_index=True,
    )
    fincol_io.write_ttm_income(out)
    return ticker_total


def load_symbols_with_quantities(loader_io: ISymbolLoader) -> list[tuple[str, float]]:
    """Delegate to ``loader_io.load_symbols_with_quantities`` and tolerate None/empty/malformed entries.

    Each result item must be a 2-element ``tuple``/``list`` whose first element is
    coercible to a non-empty ``str`` and whose second is coercible to ``float``;
    anything else is skipped with a stderr warning.
    """
    result = loader_io.load_symbols_with_quantities()
    if not result:
        print(f"Warning: no symbol/quantity entries returned from {loader_io!r}", file=sys.stderr)
        return []
    rows: list[tuple[str, float]] = []
    for i, item in enumerate(result):
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            print(
                f"Warning: skipping malformed entry #{i} from {loader_io!r}: {item!r}",
                file=sys.stderr,
            )
            continue
        sym, qty = item
        try:
            sym_str = str(sym)
            qty_val = float(qty)
        except (TypeError, ValueError):
            print(
                f"Warning: skipping entry #{i} with bad types from {loader_io!r}: {item!r}",
                file=sys.stderr,
            )
            continue
        if not sym_str:
            print(
                f"Warning: skipping entry #{i} with empty symbol from {loader_io!r}: {item!r}",
                file=sys.stderr,
            )
            continue
        rows.append((sym_str, qty_val))
    return rows


def run_ttm_dividend(loader_io: ISymbolLoader, fincol_io: IFincolIo) -> None:
    """Load positions via ``loader_io``; read dividend history and write TTM income via ``fincol_io``."""
    positions = load_symbols_with_quantities(loader_io)
    if not positions:
        raise SystemExit(f"No symbol/quantity entries found in {loader_io!r}")
    aggregated = dom.aggregate_positions_by_ticker(positions)
    div_hist = fincol_io.read_dividend_history()
    ttm_by_ticker: dict[str, float] = {}
    for sym, qty in aggregated:
        ttm_by_ticker[sym] = dom.ttm_per_share_for_ticker(sym, div_hist) * qty
    total_income = _merge_and_write_ttm_income(aggregated, ttm_by_ticker, fincol_io)

    print(f"Loaded {len(positions)} position(s) from {loader_io!r} ({len(aggregated)} ticker(s) after aggregating quantities)")
    for sym, qty in positions:
        print(f"  {sym}: {qty} shares")
    for sym, _ in aggregated:
        print(f"  TTM dividend income (last {dom.TTM_NUM_PAYMENTS} payments): {sym} = {ttm_by_ticker[sym]:.4f}")
    print(f"Total TTM dividend income (all tickers in file): {total_income:.4f}")
    print(f"Wrote TTM income to {fincol_io!r} (last row {_TOTAL_INCOME_LABEL} = {total_income:.4f})")


# ---------------------------------------------------------------------------
# User input: CLI
# ---------------------------------------------------------------------------


def load_symbols(loader_io: ISymbolLoader) -> list[str]:
    """Delegate to ``loader_io.load_symbols`` and warn (returning ``[]``) on a None/empty result."""
    result = loader_io.load_symbols()
    if not result:
        print(f"Warning: no symbols returned from {loader_io!r}", file=sys.stderr)
        return []
    return list(result)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Yahoo Finance: raw dividend series or return breakdown for a symbol."
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="raw_div",
        choices=("raw_div", "load_dividend_history", "ttm_dividend"),
        help='Mode: print dividend series (default), save dividends to cache CSV, TTM dividend income from a '
        "positions file. "
        'Default: "%(default)s".',
    )
    parser.add_argument(
        "-s",
        "--symbol",
        default="TD.TO",
        help="Ticker symbol (Yahoo format). Default: %(default)s.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="In raw_div mode, print snapshot.divs structure debug lines.",
    )
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument(
        "-j",
        "--jsonFile",
        dest="json_file",
        nargs="?",
        const="input_symbols.json",
        default=None,
        metavar="PATH",
        help="For raw_div and load_dividend_history: read symbols from a JSON array of objects with "
        "'symbol' keys (quantity ignored). For ttm_dividend: read 'symbol' and 'quantity' per object. "
        "If the flag is given without PATH, use input_symbols.json.",
    )
    input_group.add_argument(
        "-c",
        "--csvFile",
        dest="csv_file",
        nargs="?",
        const="input_symbols.csv",
        default=None,
        metavar="PATH",
        help="For raw_div and load_dividend_history: read symbols from a CSV file with a 'symbol' "
        "column (quantity ignored). For ttm_dividend: read 'symbol' and 'quantity' columns. "
        "If the flag is given without PATH, use input_symbols.csv. Mutually exclusive with -j/--jsonFile.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    input_arg = args.json_file if args.json_file is not None else args.csv_file
    if args.command == "ttm_dividend" and input_arg is None:
        raise SystemExit(
            "ttm_dividend requires -j / --jsonFile or -c / --csvFile "
            "(omit PATH to use input_symbols.json or input_symbols.csv)."
        )
    if input_arg is not None and args.command not in (
        "raw_div",
        "load_dividend_history",
        "ttm_dividend",
    ):
        raise SystemExit(
            "--jsonFile/-j and --csvFile/-c are only supported with raw_div, "
            "load_dividend_history, and ttm_dividend."
        )
    fincol_io: IFincolIo = CsvFincolIo()
    if input_arg is not None:
        # Path resolution: ``PATH`` / the default ``input_symbols.json`` /
        # ``input_symbols.csv`` are resolved with :class:`pathlib.Path` as usual—relative
        # names are relative to the process current working directory, not the directory
        # containing this script.
        path = Path(input_arg).expanduser()
        if not path.is_file():
            raise SystemExit(f"Input file not found: {path}")
        loader_io: ISymbolLoader = (
            CsvSymbolLoader(path) if args.csv_file is not None
            else JsonSymbolLoader(path)
        )
        if args.command == "ttm_dividend":
            run_ttm_dividend(loader_io, fincol_io)
            return 0
        symbols = load_symbols(loader_io)
        if not symbols:
            raise SystemExit(f"No symbols found in {path}")
        if args.command == "raw_div":
            for sym in symbols:
                run_raw_div(sym, verbose=args.verbose)
            return 0
        run_load_dividend_history(symbols, fincol_io)
        return 0
    if args.command == "raw_div":
        run_raw_div(args.symbol, verbose=args.verbose)
        return 0
    if args.command == "load_dividend_history":
        run_load_dividend_history([args.symbol], fincol_io)
        return 0
    raise SystemExit(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
