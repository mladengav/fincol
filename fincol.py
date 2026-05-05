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
from json_io import ISymbolLoader, JsonSymbolLoader
from yfinance_client import load_ticker, load_ticker_dividends, load_ticker_history

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
_TTM_INCOME_CSV = Path(__file__).resolve().parent / "cache" / "ttm_income.csv"
_TOTAL_INCOME_LABEL = "total_income"


def run_load_dividend_history(symbol: str) -> None:
    """Like :func:`run_raw_div`, plus append deduplicated rows to ``cache/dividend_history.csv``."""
    snapshot = load_ticker(symbol)
    load_ticker_dividends(snapshot)
    print(f"Dividends (ex-dates) for {snapshot.symbol}")
    print(snapshot.divs.to_string() if not snapshot.divs.empty else "(no dividends in series)")

    new_df = dom.dividends_to_history_frame(snapshot.symbol, snapshot.divs)
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


def _write_ttm_income_csv(path: Path, body: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write('"ticker","ttm_dividend"\n')
        for _, row in body.iterrows():
            f.write(f'"{row["ticker"]}",{row["ttm_dividend"]:.4f}\n')


def _merge_and_write_ttm_income(
    processed: list[tuple[str, float]],
    ttm_by_ticker: dict[str, float],
) -> float:
    """Update ``_TTM_INCOME_CSV``; rows for this run replace any prior rows for the same tickers; append ``total_income`` last.

    Returns the portfolio total (same value as the ``total_income`` row).
    """
    path = _TTM_INCOME_CSV
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

    if path.exists() and path.stat().st_size > 0:
        try:
            existing = pd.read_csv(path)
        except (pd.errors.EmptyDataError, pd.errors.ParserError):
            existing = pd.DataFrame(columns=["ticker", "ttm_dividend"])
    else:
        existing = pd.DataFrame(columns=["ticker", "ttm_dividend"])

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
    _write_ttm_income_csv(path, out)
    return ticker_total


def load_symbols_with_quantities(io: ISymbolLoader) -> list[tuple[str, float]]:
    """Delegate to ``io.load_symbols_with_quantities`` and tolerate None/empty/malformed entries.

    Each result item must be a 2-element ``tuple``/``list`` whose first element is
    coercible to a non-empty ``str`` and whose second is coercible to ``float``;
    anything else is skipped with a stderr warning.
    """
    result = io.load_symbols_with_quantities()
    if not result:
        print(f"Warning: no symbol/quantity entries returned from {io!r}", file=sys.stderr)
        return []
    rows: list[tuple[str, float]] = []
    for i, item in enumerate(result):
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            print(
                f"Warning: skipping malformed entry #{i} from {io!r}: {item!r}",
                file=sys.stderr,
            )
            continue
        sym, qty = item
        try:
            sym_str = str(sym)
            qty_val = float(qty)
        except (TypeError, ValueError):
            print(
                f"Warning: skipping entry #{i} with bad types from {io!r}: {item!r}",
                file=sys.stderr,
            )
            continue
        if not sym_str:
            print(
                f"Warning: skipping entry #{i} with empty symbol from {io!r}: {item!r}",
                file=sys.stderr,
            )
            continue
        rows.append((sym_str, qty_val))
    return rows


def run_ttm_dividend(io: ISymbolLoader) -> None:
    """Load positions via ``io``; TTM from ``cache/dividend_history.csv``; write ``cache/ttm_income.csv``."""
    positions = load_symbols_with_quantities(io)
    if not positions:
        raise SystemExit(f"No symbol/quantity entries found in {io!r}")
    aggregated = dom.aggregate_positions_by_ticker(positions)
    if _DIVIDEND_HISTORY_CSV.is_file():
        div_hist = pd.read_csv(_DIVIDEND_HISTORY_CSV)
    else:
        div_hist = pd.DataFrame(columns=["ticker", "date", "amount"])
    ttm_by_ticker: dict[str, float] = {}
    for sym, qty in aggregated:
        ttm_by_ticker[sym] = dom.ttm_per_share_for_ticker(sym, div_hist) * qty
    total_income = _merge_and_write_ttm_income(aggregated, ttm_by_ticker)

    print(f"Loaded {len(positions)} position(s) from {io!r} ({len(aggregated)} ticker(s) after aggregating quantities)")
    for sym, qty in positions:
        print(f"  {sym}: {qty} shares")
    for sym, _ in aggregated:
        print(f"  TTM dividend income (last {dom.TTM_NUM_PAYMENTS} payments): {sym} = {ttm_by_ticker[sym]:.4f}")
    print(f"Total TTM dividend income (all tickers in file): {total_income:.4f}")
    print(f"Wrote {_TTM_INCOME_CSV} (last row {_TOTAL_INCOME_LABEL} = {total_income:.4f})")


def run_fetch_and_compute(symbol: str) -> dict[str, dict[str, object]]:
    """``load_ticker`` + ``load_ticker_dividends`` + ``load_ticker_history``; same ``divs`` path as :func:`run_raw_div`."""
    snapshot = load_ticker(symbol)
    load_ticker_dividends(snapshot)
    load_ticker_history(snapshot)
    if snapshot.hist.empty:
        raise RuntimeError("No price data returned for " + snapshot.symbol)
    return dom.compute_return_periods(snapshot)


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


def load_symbols(io: ISymbolLoader) -> list[str]:
    """Delegate to ``io.load_symbols`` and warn (returning ``[]``) on a None/empty result."""
    result = io.load_symbols()
    if not result:
        print(f"Warning: no symbols returned from {io!r}", file=sys.stderr)
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
        choices=("raw_div", "load_dividend_history", "ttm_dividend", "fetch_and_compute"),
        help='Mode: print dividend series (default), save dividends to cache CSV, TTM dividend income from a '
        "positions file, or compute period returns. "
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
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "ttm_dividend" and args.json_file is None:
        raise SystemExit("ttm_dividend requires -j / --jsonFile (omit PATH to use input_symbols.json).")
    if args.json_file is not None and args.command not in (
        "raw_div",
        "load_dividend_history",
        "ttm_dividend",
    ):
        raise SystemExit("--jsonFile/-j is only supported with raw_div, load_dividend_history, and ttm_dividend.")
    if args.json_file is not None:
        # Path resolution: ``PATH`` / the default ``input_symbols.json`` are resolved with
        # :class:`pathlib.Path` as usual—relative names are relative to the process current
        # working directory, not the directory containing this script.
        path = Path(args.json_file).expanduser()
        if not path.is_file():
            raise SystemExit(f"JSON file not found: {path}")
        io: ISymbolLoader = JsonSymbolLoader(path)
        if args.command == "ttm_dividend":
            run_ttm_dividend(io)
            return 0
        symbols = load_symbols(io)
        if not symbols:
            raise SystemExit(f"No symbols found in {path}")
        if args.command == "raw_div":
            for sym in symbols:
                run_raw_div(sym, verbose=args.verbose)
            return 0
        for sym in symbols:
            run_load_dividend_history(sym)
        return 0
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
