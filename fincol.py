"""
CLI entry: raw dividend output vs. return computation for a symbol.
Internal layout: :mod:`yfinance_client` snapshot → period math → services → argparse.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from debug_utils import debug_print_divs_structure
from yfinance_client import TickerSnapshot, load_ticker, load_ticker_dividends, load_ticker_history

# ---------------------------------------------------------------------------
# Domain: return periods (pure given a snapshot, except empty hist guard in caller)
# ---------------------------------------------------------------------------


def _get_price_on_or_after(df: pd.DataFrame, d: date) -> pd.Series:
    df2 = df[df.index.date >= d]
    return df2.iloc[0] if not df2.empty else df.iloc[0]


def _get_price_on_or_before(df: pd.DataFrame, d: date) -> pd.Series:
    df2 = df[df.index.date <= d]
    return df2.iloc[-1] if not df2.empty else df.iloc[-1]


def compute_return_periods(snapshot: TickerSnapshot) -> dict[str, dict[str, object]]:
    """1d, 1m, YTD metrics using ``snapshot.hist`` and ``snapshot.divs``."""
    hist = snapshot.hist
    divs = snapshot.divs
    today = snapshot.end
    periods: dict[str, tuple[date, date]] = {
        "1d": (today - timedelta(days=1), today),
        "1m": (today - timedelta(days=30), today),
        "YTD": (date(today.year, 1, 1), today),
    }
    results: dict[str, dict[str, object]] = {}
    for name, (sdate, edate) in periods.items():
        start_row = _get_price_on_or_after(hist, sdate)
        end_row = _get_price_on_or_before(hist, edate)
        div_sum = divs[(divs.index.date >= sdate) & (divs.index.date <= edate)].sum()
        price_return = (end_row["Close"] - start_row["Close"]) / start_row["Close"]
        total_return = (end_row["Close"] - start_row["Close"] + div_sum) / start_row["Close"]
        adj_return = (end_row["Adj Close"] - start_row["Adj Close"]) / start_row["Adj Close"]
        results[name] = {
            "start_date": start_row.name.date(),
            "end_date": end_row.name.date(),
            "start_close": float(start_row["Close"]),
            "end_close": float(end_row["Close"]),
            "dividends": float(div_sum),
            "price_return": float(price_return),
            "total_return": float(total_return),
            "adj_return": float(adj_return),
        }
    return results


# ---------------------------------------------------------------------------
# Services: orchestration (each mode uses its own progressive load sequence)
# ---------------------------------------------------------------------------


def run_raw_div(symbol: str, *, verbose: bool = False) -> None:
    """``load_ticker`` + ``load_ticker_dividends``; print raw ex-dividend series (no price history)."""
    snapshot = load_ticker(symbol)
    load_ticker_dividends(snapshot)
    print(f"Dividends (ex-dates) for {snapshot.symbol}")
    if verbose:
        debug_print_divs_structure(snapshot.divs)
    print(snapshot.divs.to_string() if not snapshot.divs.empty else "(no dividends in series)")


_DIVIDEND_HISTORY_CSV = Path(__file__).resolve().parent / "cache" / "dividend_history.csv"


def _dividends_to_history_frame(symbol: str, divs: pd.Series) -> pd.DataFrame:
    """One row per dividend: ticker, calendar date (YYYY-MM-DD), amount (from ``Date`` / ``Dividends`` columns)."""
    if divs.empty:
        return pd.DataFrame(columns=["ticker", "date", "amount"])
    tab = divs.reset_index()
    date_col, amt_col = tab.columns[0], tab.columns[1]
    return pd.DataFrame(
        {
            "ticker": symbol,
            "date": pd.to_datetime(tab[date_col]).dt.strftime("%Y-%m-%d"),
            "amount": tab[amt_col].astype(float),
        }
    )


def run_load_dividend_history(symbol: str) -> None:
    """Like :func:`run_raw_div`, plus append deduplicated rows to ``cache/dividend_history.csv``."""
    snapshot = load_ticker(symbol)
    load_ticker_dividends(snapshot)
    print(f"Dividends (ex-dates) for {snapshot.symbol}")
    print(snapshot.divs.to_string() if not snapshot.divs.empty else "(no dividends in series)")

    new_df = _dividends_to_history_frame(snapshot.symbol, snapshot.divs)
    x_retrieved = len(new_df)

    path = _DIVIDEND_HISTORY_CSV
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        existing = pd.read_csv(path)
    else:
        existing = pd.DataFrame(columns=["ticker", "date", "amount"])

    if existing.empty:
        existing_clean = existing
    else:
        existing_clean = existing.drop_duplicates(subset=["ticker", "date", "amount"], keep="first")

    combined = pd.concat([existing_clean, new_df], ignore_index=True)
    combined = combined.drop_duplicates(subset=["ticker", "date", "amount"], keep="first")
    combined = combined.sort_values(["ticker", "date"], kind="mergesort").reset_index(drop=True)

    rows_added = len(combined) - len(existing_clean)
    z_filtered = x_retrieved - rows_added

    with path.open("w", encoding="utf-8", newline="") as f:
        f.write('"ticker","date","amount"\n')
        for _, row in combined.iterrows():
            f.write(f'"{row["ticker"]}","{row["date"]}",{row["amount"]:.4f}\n')

    print(
        f"{x_retrieved} rows retrieved ticker {snapshot.symbol}, "
        f"{rows_added} rows added, {z_filtered} duplicate rows filtered out"
    )


def run_fetch_and_compute(symbol: str) -> dict[str, dict[str, object]]:
    """``load_ticker`` + ``load_ticker_dividends`` + ``load_ticker_history``; same ``divs`` path as :func:`run_raw_div`."""
    snapshot = load_ticker(symbol)
    load_ticker_dividends(snapshot)
    load_ticker_history(snapshot)
    if snapshot.hist.empty:
        raise RuntimeError("No price data returned for " + snapshot.symbol)
    return compute_return_periods(snapshot)


def print_return_report(results: dict[str, dict[str, object]]) -> None:
    for period, vals in results.items():
        print(f"{period}: start {vals['start_date']} -> end {vals['end_date']}")
        print(f"  Start Close: {vals['start_close']:.2f}, End Close: {vals['end_close']:.2f}")
        print(f"  Dividends in period: {vals['dividends']:.4f}")
        print(f"  Price return: {vals['price_return']:.2%}")
        print(f"  Total return (price + dividends): {vals['total_return']:.2%}")
        print(f"  Adjusted-close return: {vals['adj_return']:.2%}\n")


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
        choices=("raw_div", "load_dividend_history", "fetch_and_compute"),
        help='Mode: print dividend series (default), save dividends to cache CSV, or compute period returns. '
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
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "raw_div":
        run_raw_div(args.symbol, verbose=args.verbose)
        return 0
    if args.command == "load_dividend_history":
        run_load_dividend_history(args.symbol)
        return 0
    results = run_fetch_and_compute(args.symbol)
    print_return_report(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
