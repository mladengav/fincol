"""Azure Blob-backed :class:`~infrastructure.csv.io.CsvFincolIo` with a local cache mirror."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

import pandas as pd
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

from domain.ticker_snapshot import TickerSnapshot
from infrastructure import _PROJECT_ROOT
from infrastructure.csv.io import CsvFincolIo


class AzBlobCsvFincolIo(CsvFincolIo):
    """CsvFincolIo backed by Azure Blob Storage with a local cache folder mirror."""

    _CONTAINER_NAME = "csvcache"

    def __init__(self, folder: Path | None = None) -> None:
        super().__init__(folder=folder)
        self._folder.mkdir(parents=True, exist_ok=True)

        load_dotenv(_PROJECT_ROOT / ".env")
        storage_url = os.environ["AZURE_STORAGE_BLOB_URL"]
        credential = DefaultAzureCredential()
        self._container_client = BlobServiceClient(
            account_url=storage_url,
            credential=credential,
        ).get_container_client(self._CONTAINER_NAME)

        self._sync_from_azure()

    def _sync_from_azure(self) -> None:
        """Download blobs into the local cache, preserving subpaths (e.g. ``aggregations/ttm_income.csv``)."""
        for blob in self._container_client.list_blobs():
            target = self._folder.joinpath(*Path(blob.name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb") as f:
                download_stream = self._container_client.download_blob(blob.name)
                f.write(download_stream.readall())

    def _sync_to_azure(self) -> None:
        """Upload every file under the cache folder, including nested paths."""
        for path in self._folder.rglob("*"):
            if not path.is_file():
                continue
            blob_name = path.relative_to(self._folder).as_posix()
            with path.open("rb") as data:
                self._container_client.upload_blob(
                    name=blob_name, data=data, overwrite=True
                )

    def write_ttm_income(self, ttm_by_ticker: Mapping[str, float]) -> None:
        super().write_ttm_income(ttm_by_ticker)
        self._sync_to_azure()

    def write_dividend_history(self, body: pd.DataFrame) -> None:
        super().write_dividend_history(body)
        self._sync_to_azure()

    def write_tickers_to_cache(self, snapshots: list[TickerSnapshot]) -> None:
        super().write_tickers_to_cache(snapshots)
        self._sync_to_azure()
