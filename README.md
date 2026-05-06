# fincol

`fincol` is a small command-line tool that loads financial dividend data from Yahoo Finance via the `yfinance` Python library and persists it to a cache. Other tools and clients can then consume that cache for downstream transformations, reporting, and analysis.

## Capabilities

- Fetches raw dividend history per ticker from Yahoo Finance.
- Supports symbol input from:
  - a single CLI symbol (`--symbol`)
  - a JSON input file (`--jsonFile`) with `symbol` keys
  - a CSV input file (`--csvFile`) with a `symbol` column
- Writes cache/output data as CSV:
  - local CSV-backed cache files
  - CSV-backed cache files stored in Azure Blob Storage (via `--azureCsvStore`)
- Updates dividend history and computes/writes trailing-twelve-month (TTM) dividend income by ticker.

## Commands

- `raw_div` (default): print raw dividend series.
- `load_dividend_history`: fetch/update cached dividend history and refresh TTM income.

## Command-line switches

- `-s`, `--symbol`: ticker symbol to process (default: `TD.TO`).
- `-v`, `--verbose`: print additional dividend structure debug output in `raw_div` mode.
- `--azureCsvStore`: use Azure Blob Storage container `csvcache` as CSV cache backend.
- `-j`, `--jsonFile [PATH]`: load symbols from JSON (default file when omitted: `input_symbols.json`).
- `-c`, `--csvFile [PATH]`: load symbols from CSV (default file when omitted: `input_symbols.csv`).
  - `--jsonFile` and `--csvFile` are mutually exclusive.