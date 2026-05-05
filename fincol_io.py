from typing import Protocol, runtime_checkable
import pandas as pd

@runtime_checkable
class ISymbolLoader(Protocol):
    """Source of symbol / position records consumed by :mod:`fincol`."""

    def load_symbols(self) -> list[str]: ...

    def load_symbols_with_quantities(self) -> list[tuple[str, float]]: ...


@runtime_checkable
class IFincolIo(Protocol):

    def read_ttm_income(self) -> pd.DataFrame: ...

    def write_ttm_income(self, body: pd.DataFrame) -> None: ...

    def read_dividend_history(self) -> pd.DataFrame: ...

    def write_dividend_history(self, body: pd.DataFrame) -> None: ...
        
