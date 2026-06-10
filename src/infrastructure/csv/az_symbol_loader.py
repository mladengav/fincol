"""Azure Blob-backed :class:`~infrastructure.csv.symbol_loader.CsvSymbolLoader`.

Downloads input symbols into a local temp
folder at construction time, then defers to the base CSV symbol-parsing logic. Use as
a context manager so the temp folder is removed on exit.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from types import TracebackType

from azure.storage.blob import BlobServiceClient

from infrastructure.csv.symbol_loader import CsvSymbolLoader


class AzCsvSymbolLoader(CsvSymbolLoader):
    """:class:`CsvSymbolLoader` whose CSV is fetched from Azure Blob Storage.

    On construction the input symbols blob is
    downloaded into a temporary folder; the base class then reads symbols from it.
    The temp folder is deleted by :meth:`__exit__`, so instances are meant to be used
    via ``with``.
    """

    _CONTAINER_NAME = "csvinputs"
    _BLOB_NAME = "input_symbols.csv"

    def __init__(self, blob_service_client: BlobServiceClient) -> None:
        self._temp_dir = Path(tempfile.mkdtemp(prefix="fincol_azinput_"))
        container_client = blob_service_client.get_container_client(
            self._CONTAINER_NAME
        )

        local_path = self._temp_dir / self._BLOB_NAME
        with local_path.open("wb") as f:
            download_stream = container_client.download_blob(self._BLOB_NAME)
            f.write(download_stream.readall())

        super().__init__(local_path)

    def __repr__(self) -> str:
        return f"AzCsvSymbolLoader({self._CONTAINER_NAME}/{self._BLOB_NAME})"

    def __enter__(self) -> AzCsvSymbolLoader:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        shutil.rmtree(self._temp_dir, ignore_errors=True)
