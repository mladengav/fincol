"""
CLI entry: raw dividend output vs. return computation for a symbol.
Internal layout: :mod:`yfinance_client` snapshot → :mod:`domain` math → services → argparse.
"""
from __future__ import annotations

from aggregation_updater import AggregationUpdater, IAggregationUpdater
import argparse
from dividend_loader import DividendLoader, IDividendLoader

from pathlib import Path

from csv_io import CsvSymbolLoader, CsvFincolIo, AzBlobCsvFincolIo
from fincol_io import ISymbolLoader, IFincolIo
from json_io import JsonSymbolLoader

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
    parser.add_argument(
        "--azureCsvStore",
        action="store_true",
        dest="azure_csv_store",
        help="Use Azure Blob Storage container 'csvcache' as the backing store for cache CSV files.",
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
    aggregation_updater: IAggregationUpdater = AggregationUpdater()
    dividend_loader: IDividendLoader = DividendLoader()
    input_arg = args.json_file if args.json_file is not None else args.csv_file
    fincol_io: IFincolIo = AzBlobCsvFincolIo() if args.azure_csv_store else CsvFincolIo()
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
                dividend_loader.retrieve_ticker_dividends(sym, verbose=args.verbose)
            return 0
        dividend_loader.update_dividend_history(symbols, fincol_io)
        aggregation_updater.update_aggregations(fincol_io)
        return 0
    if args.command == "raw_div":
        dividend_loader.retrieve_ticker_dividends(args.symbol, verbose=args.verbose)
        return 0
    if args.command == "load_dividend_history":
        dividend_loader.update_dividend_history([args.symbol], fincol_io)
        aggregation_updater.update_aggregations(fincol_io)
        return 0
    raise SystemExit(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
