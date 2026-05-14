"""
Dev/presentation CLI: display TTM dividend income for a positions file.

This utility is a thin presentation layer over data already cached by
:mod:`fincol`. It does not fetch new market data; it only reads the cache,
aggregates positions, and displays TTM dividend income.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from application import fincol_math as fm
from domain.fincol_io import IFincolIo, ISymbolLoader
from infrastructure.csv_io import CsvFincolIo
from infrastructure.csv_symbol_loader import CsvSymbolLoader
from infrastructure.json_io import JsonSymbolLoader


def load_symbols_with_quantities(loader_io: ISymbolLoader) -> list[tuple[str, float]]:
    """Delegate to ``loader_io.load_symbols_with_quantities`` and tolerate None/empty/malformed entries.

    Each result item must be a 2-element ``tuple``/``list`` whose first element is
    coercible to a non-empty ``str`` and whose second is coercible to ``float``;
    anything else is skipped with a stderr warning.
    """
    result = loader_io.load_symbols_with_quantities()
    if not result:
        print(
            f"Warning: no symbol/quantity entries returned from {loader_io!r}",
            file=sys.stderr,
        )
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
        except TypeError, ValueError:
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


def run_display_positions_dividend(
    loader_io: ISymbolLoader, fincol_io: IFincolIo
) -> None:
    """Load positions via ``loader_io``; read TTM dividends via ``fincol_io`` and display TTM income for positions"""
    positions = load_symbols_with_quantities(loader_io)
    if not positions:
        raise SystemExit(f"No symbol/quantity entries found in {loader_io!r}")
    aggregated = fm.aggregate_positions_by_ticker(positions)
    per_share = fincol_io.read_ttm_income()
    ttm_by_ticker: dict[str, float] = {}

    for sym, qty in aggregated:
        ttm_by_ticker[sym] = per_share.get(sym, 0.0) * qty

    print(
        f"Loaded {len(positions)} position(s) from {loader_io!r} ({len(aggregated)} ticker(s) after aggregating quantities)"
    )
    for sym, qty in aggregated:
        print(f"  {sym}: {qty} shares")
    for sym, _ in aggregated:
        print(
            f"  TTM dividend income (last {fm.TTM_NUM_PAYMENTS} payments): {sym} = {ttm_by_ticker[sym]:.4f}"
        )

    total_income = sum(ttm_by_ticker.values())
    print(f"Total TTM dividend income (all tickers in file): {total_income:.4f}")


# ---------------------------------------------------------------------------
# User input: CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Display TTM dividend income per ticker (and the portfolio total) "
            "for a positions file, using the cache populated by "
            "`fincol load_dividend_history`."
        ),
    )
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "-j",
        "--jsonFile",
        dest="json_file",
        nargs="?",
        const="input_symbols.json",
        default=None,
        metavar="PATH",
        help="Read 'symbol' and 'quantity' from a JSON array of objects. "
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
        help="Read 'symbol' and 'quantity' columns from a CSV file. "
        "If the flag is given without PATH, use input_symbols.csv. "
        "Mutually exclusive with -j/--jsonFile.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    input_arg = args.json_file if args.json_file is not None else args.csv_file
    # Path resolution: ``PATH`` / the default ``input_symbols.json`` /
    # ``input_symbols.csv`` are resolved with :class:`pathlib.Path` as usual—relative
    # names are relative to the process current working directory, not the directory
    # containing this script.
    path = Path(input_arg).expanduser()
    if not path.is_file():
        raise SystemExit(f"Input file not found: {path}")
    loader_io: ISymbolLoader = (
        CsvSymbolLoader(path) if args.csv_file is not None else JsonSymbolLoader(path)
    )
    fincol_io: IFincolIo = CsvFincolIo()
    run_display_positions_dividend(loader_io, fincol_io)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
