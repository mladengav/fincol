from pathlib import Path
import azure.functions as func

from csv_io import AzBlobCsvFincolIo, CsvFincolIo, CsvSymbolLoader
from fincol import run_load_dividend_history
from fincol_io import IFincolIo, ISymbolLoader
from json_io import JsonSymbolLoader

app = func.FunctionApp()

@app.route("hello")
def http_trigger(req):
    user = req.params.get("user")
    return f"Hello, {user}!"


@app.route("load_dividend_history")
def http_trigger(req):
    # Path resolution: ``PATH`` / the default ``input_symbols.json`` /
    # ``input_symbols.csv`` are resolved with :class:`pathlib.Path` as usual—relative
    # names are relative to the process current working directory, not the directory
    # containing this script.
    input_arg = "input_symbols.json"
    csv_file = None
    azure_csv_store = True
    path = Path(input_arg).expanduser()
    if not path.is_file():
        raise SystemExit(f"Input file not found: {path}")
    loader_io: ISymbolLoader = (
        CsvSymbolLoader(path) if csv_file is not None
        else JsonSymbolLoader(path)
    )
    symbols = loader_io.load_symbols()
    if not symbols:
        raise SystemExit(f"No symbols found in {loader_io!r}")
    fincol_io: IFincolIo = AzBlobCsvFincolIo() if azure_csv_store is True else CsvFincolIo()
    run_load_dividend_history(symbols, fincol_io)
    return f"Dividend history loaded for {symbols}!"