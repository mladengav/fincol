"""
CLI entry: raw dividend output vs. return computation for a symbol.
Internal layout: :mod:`yfinance_client` snapshot → :mod:`domain` math → services → argparse.
"""
from __future__ import annotations

import argparse
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

    run_update_ttm_dividend(fincol_io)


def run_update_ttm_dividend(fincol_io: IFincolIo) -> None:
    """Write TTM income via ``fincol_io``."""

    div_hist = fincol_io.read_dividend_history()
    ttm_by_ticker: dict[str, float] = {}

    unique_tickers = list(dict.fromkeys(div_hist["ticker"]))

    for sym in unique_tickers:
        ttm_by_ticker[sym] = dom.ttm_per_share_for_ticker(sym, div_hist)
    fincol_io.write_ttm_income(ttm_by_ticker)

    print(f"Loaded {len(unique_tickers)} ticker(s) from {fincol_io!r}")
    for sym in unique_tickers:
        print(f"  TTM dividend income (last {dom.TTM_NUM_PAYMENTS} payments): {sym} = {ttm_by_ticker[sym]:.4f}")

    print(f"Wrote TTM income to {fincol_io!r}")


# ---------------------------------------------------------------------------
# User input: CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Yahoo Finance: raw dividend series or return breakdown for a symbol."
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="raw_div",
        choices=("raw_div", "load_dividend_history"),
        help='Mode: print dividend series (default), or save dividends to cache CSV. '
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
        help="Read symbols from a JSON array of objects with 'symbol' keys (quantity ignored). "
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
        help="Read symbols from a CSV file with a 'symbol' column (quantity ignored). "
        "If the flag is given without PATH, use input_symbols.csv. "
        "Mutually exclusive with -j/--jsonFile.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    input_arg = args.json_file if args.json_file is not None else args.csv_file
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
        symbols = loader_io.load_symbols()
        if not symbols:
            raise SystemExit(f"No symbols found in {loader_io!r}")
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
