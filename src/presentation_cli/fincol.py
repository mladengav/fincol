"""
CLI entry: Yahoo dividend display and cache updates for one or many tickers.

Wiring: :mod:`infrastructure.yfinance_client` (live data) → :mod:`application.dividend_loader` /
:mod:`application.aggregation_updater` → :mod:`infrastructure.csv` (cache I/O);
:mod:`infrastructure.csv` / :mod:`infrastructure.json_symbol_loader` when loading positions; argparse.
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

from application.aggregation_updater import AggregationUpdater, IAggregationUpdater
from application.dividend_loader import DividendLoader, IDividendLoader
from domain.fincol_io import IFincolIo, ISymbolLoader
from infrastructure import _PROJECT_ROOT
from infrastructure.csv import (
    AzBlobCsvFincolIo,
    AzCsvSymbolLoader,
    CsvFincolIo,
    CsvSymbolLoader,
)
from infrastructure.json_symbol_loader import JsonSymbolLoader
from infrastructure.yfinance_client import YahooFinance

logging.basicConfig(
    format="%(asctime)s %(levelname)s: %(message)s", level=logging.INFO
)  # TODO use logging.conf to set format, timestamps, etc

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
        help="Mode: print dividend series (default), or save dividends to cache CSV. "
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
    input_group.add_argument(
        "--azureCsvInput",
        action="store_true",
        dest="azure_csv_input",
        help="Read symbols from 'input_symbols.csv' in the Azure Blob container "
        "'csvinputs'. Mutually exclusive with -c/--csvFile and -j/--jsonFile.",
    )
    return parser


def _build_blob_service_client() -> BlobServiceClient:
    """Build a :class:`BlobServiceClient` from ``.env`` / environment credentials."""
    load_dotenv(_PROJECT_ROOT / ".env")
    storage_url = os.environ["AZURE_STORAGE_BLOB_URL"]
    credential = DefaultAzureCredential()
    return BlobServiceClient(account_url=storage_url, credential=credential)


def _run_command(
    args: argparse.Namespace,
    symbols: list[str],
    dividend_loader: IDividendLoader,
    aggregation_updater: IAggregationUpdater,
) -> int:
    """Dispatch the parsed command over a resolved list of symbols."""
    if args.command == "raw_div":
        for sym in symbols:
            dividend_loader.retrieve_ticker_dividends(sym, verbose=args.verbose)
        return 0
    if args.command == "load_dividend_history":
        dividend_loader.update_dividend_history(symbols)
        aggregation_updater.update_aggregations(symbols)
        return 0
    raise SystemExit(f"Unsupported command: {args.command}")


def main() -> int:
    args = build_parser().parse_args()
    input_arg = args.json_file if args.json_file is not None else args.csv_file
    fincol_io: IFincolIo = (
        AzBlobCsvFincolIo(_build_blob_service_client())
        if args.azure_csv_store
        else CsvFincolIo()
    )
    aggregation_updater: IAggregationUpdater = AggregationUpdater(fincol_io)
    dividend_loader: IDividendLoader = DividendLoader(YahooFinance(), fincol_io)
    if args.azure_csv_input:
        with AzCsvSymbolLoader(_build_blob_service_client()) as loader_io:
            symbols = loader_io.load_symbols()
        if not symbols:
            raise SystemExit(f"No symbols found in {loader_io!r}")
        return _run_command(args, symbols, dividend_loader, aggregation_updater)
    if input_arg is not None:
        # Path resolution: ``PATH`` / the default ``input_symbols.json`` /
        # ``input_symbols.csv`` are resolved with :class:`pathlib.Path` as usual—relative
        # names are relative to the process current working directory, not the directory
        # containing this script.
        path = Path(input_arg).expanduser()
        if not path.is_file():
            raise SystemExit(f"Input file not found: {path}")
        loader: ISymbolLoader = (
            CsvSymbolLoader(path)
            if args.csv_file is not None
            else JsonSymbolLoader(path)
        )
        symbols = loader.load_symbols()
        if not symbols:
            raise SystemExit(f"No symbols found in {loader!r}")
        return _run_command(args, symbols, dividend_loader, aggregation_updater)
    return _run_command(args, [args.symbol], dividend_loader, aggregation_updater)


if __name__ == "__main__":
    raise SystemExit(main())
