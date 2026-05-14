"""CLI entry for period return computation via yfinance snapshots."""

from __future__ import annotations

import argparse
import csv
import datetime

from application import fincol_math as fm
from infrastructure.yfinance_client import YahooFinance
import yfinance as yf


def run_fetch_and_compute(symbol: str) -> dict[str, dict[str, object]]:
    """Load dividends/history and compute 1d, 1m, and YTD returns."""
    snapshot = YahooFinance().load_ticker(symbol)
    # .with_dividends().with_history()
    # if snapshot.hist.empty:
    #   raise RuntimeError("No price data returned for " + snapshot.symbol)

    # print(f"Sector:  {snapshot.ticker.info['sectorKey']}")
    # print(f"Industry:  {snapshot.ticker.info['industry']}")
    # print(f"Basic All:  {snapshot.ticker.basic_info}")
    print(f"Calendar:  {snapshot.ticker.calendar}")

    multi = YahooFinance().load_tickers(symbol)
    print(f"Tickers:  {multi}")
    print(f"Tickers hist:")
    print(
        multi.history(
            period="3mo",
            interval="1mo",
            start=None,
            end=None,
            prepost=False,
            actions=True,
            auto_adjust=True,
            repair=False,
            threads=True,
            group_by="ticker",
            progress=False,
        )
    )
    # return fm.compute_return_periods(snapshot)

    return None


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
    # results = run_fetch_and_compute(args.symbol)
    # print_return_report(results)

    # yf = YahooFinance()

    # ticker = yf.load_ticker("BNS.TO", withDividends=True)
    # ticker.divs.to_csv("bns_divs.csv")
    # ticker.divs.to_pickle("bns_divs.pkl")

    # ticker.divs

    date = datetime.datetime.fromisoformat("2026-04-24")
    tickers = yf.Tickers("BNS.TO TD.TO RY.TO")
    df = tickers.history(period="3mo", interval="3mo",
    start=date, progress=False)
    # print(df)
    # print(df.info())
    # print(df["Dividends"])
    # print(df["Dividends"]["BNS.TO"].sum())

    div = df["Dividends"]
    for ticker in div.columns:
        total = div[ticker].sum()
        print(f"{ticker}: {total}")


    # nw_dividends_symbols = []
    # div = df["Dividends"]
    # for symbol in df["Dividends"].columns:
    #     if (df["Dividends"][symbol] > 0):
    #         nw_dividends_symbols.append(symbol)
    # print("New dividends symbols:")
    # print(nw_dividends_symbols)


    # rbc = yf.Ticker("RY.TO")
    # info = rbc.info
    # # print(info)
    # keys = info.keys()
    # with open('ry_info.csv', 'w', newline='') as f:
    #     writer = csv.DictWriter(f, fieldnames=keys)
    #     writer.writeheader()
    #     writer.writerows([info])
    

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
