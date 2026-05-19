"""CLI entry for period return computation via yfinance snapshots."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta

from application import fincol_math as fm
from infrastructure.yfinance_client import YahooFinance


def run_fetch_and_compute(symbol: str) -> dict[str, dict[str, object]]:
    """Load dividends/history and compute 1d, 1m, and YTD returns."""
    divs = YahooFinance().load_ticker_dividends(symbol)

    today = datetime.now().date()
    history = YahooFinance().load_ticker_history(symbol, history_start=today- timedelta(days=365), end=today)

    return fm.compute_return_periods(symbol, divs, history)


def print_return_report(results: dict[str, dict[str, object]]) -> None:
    """Print period return metrics in a human-readable block per period."""
    for period, vals in results.items():
        print(f"{period}: start {vals['start_date']} -> end {vals['end_date']}")
        print(f"  Start Close: {vals['start_close']:.2f}, End Close: {vals['end_close']:.2f}")
        print(f"  Dividends in period: {vals['dividends']:.4f}")
        print(f"  Price return: {vals['price_return']:.2%}")
        print(f"  Total return (price + dividends): {vals['total_return']:.2%}")
        print(f"  Adjusted-close return: {vals['adj_return']:.2%}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Yahoo Finance: compute 1d/1m/YTD period returns for a symbol."
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="fetch_and_compute",
        choices=("fetch_and_compute",),
        help='Mode: compute period returns. Default: "%(default)s".',
    )
    parser.add_argument(
        "-s",
        "--symbol",
        default="TD.TO",
        help="Ticker symbol (Yahoo format). Default: %(default)s.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command != "fetch_and_compute":
        raise SystemExit(f"Unsupported command: {args.command}")
    results = run_fetch_and_compute(args.symbol)
    print_return_report(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
