"""Azure Blob-backed :class:`~infrastructure.csv.io.CsvFincolIo` with a local cache mirror."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import date
from pathlib import Path

import pandas as pd
from azure.core.exceptions import HttpResponseError, ResourceExistsError
from azure.storage.blob import BlobLeaseClient, BlobServiceClient

from domain.ticker_snapshot import TickerSnapshot
from infrastructure.csv.io import CsvFincolIo
from infrastructure.errors import AggregationLockError

logger = logging.getLogger(__name__)


class AzBlobCsvFincolIo(CsvFincolIo):
    """CsvFincolIo backed by Azure Blob Storage with a local cache folder mirror."""

    _CONTAINER_NAME = "csvcache"
    _LEASE_DURATION_SECONDS = 60

    def __init__(
        self, blob_service_client: BlobServiceClient, folder: Path | None = None
    ) -> None:
        super().__init__(folder=folder)
        self._folder.mkdir(parents=True, exist_ok=True)
        self._aggregation_leases: dict[str, BlobLeaseClient] = {}

        self._container_client = blob_service_client.get_container_client(
            self._CONTAINER_NAME
        )

        self._sync_from_azure()

    def _sync_from_azure(self) -> None:
        """Download blobs into the local cache, preserving subpaths (e.g. ``aggregations/ttm_income.csv``)."""
        for blob in self._container_client.list_blobs():
            if blob.name.endswith(self._LOCK_SUFFIX):
                continue
            target = self._folder.joinpath(*Path(blob.name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb") as f:
                download_stream = self._container_client.download_blob(blob.name)
                f.write(download_stream.readall())

    def _sync_to_azure(self) -> None:
        """Upload every file under the cache folder, including nested paths.

        Aggregation blobs are only uploaded while this instance holds their lease.
        """
        aggregation_blob_names = {p.as_posix() for p in self._AGGREGATION_CSVS}
        for held_lease in self._aggregation_leases.values():
            held_lease.renew()
        for path in self._folder.rglob("*"):
            if not path.is_file() or path.name.endswith(self._LOCK_SUFFIX):
                continue
            blob_name = path.relative_to(self._folder).as_posix()
            lease = self._aggregation_leases.get(blob_name)
            if blob_name in aggregation_blob_names and lease is None:
                continue
            with path.open("rb") as data:
                self._container_client.upload_blob(
                    name=blob_name, data=data, overwrite=True, lease=lease
                )

    def begin_aggregation_updates(self) -> None:
        """Take the local lock files, then a lease on every aggregation blob.

        Raises :class:`AggregationLockError` if any blob is already leased; local
        locks and leases acquired before the failure are released first.
        """
        super().begin_aggregation_updates()
        try:
            for csv_path in self._AGGREGATION_CSVS:
                blob_name = csv_path.as_posix()
                blob_client = self._container_client.get_blob_client(blob_name)
                if not blob_client.exists():
                    # A lease needs an existing blob; readers treat empty as no data.
                    try:
                        blob_client.upload_blob(b"", overwrite=False)
                    except ResourceExistsError:
                        pass
                try:
                    lease = blob_client.acquire_lease(
                        lease_duration=self._LEASE_DURATION_SECONDS
                    )
                except HttpResponseError as e:
                    raise AggregationLockError(
                        f"Could not lease blob {self._CONTAINER_NAME}/{blob_name}: "
                        f"{e.message}"
                    ) from e
                self._aggregation_leases[blob_name] = lease
        except BaseException:
            self.finish_aggregation_updates()
            raise

    def finish_aggregation_updates(self) -> None:
        """Release the blob leases and local lock files held by this instance."""
        try:
            for blob_name, lease in self._aggregation_leases.items():
                try:
                    lease.release()
                except HttpResponseError:
                    logger.warning(
                        "Could not release lease on blob %s/%s",
                        self._CONTAINER_NAME,
                        blob_name,
                        exc_info=True,
                    )
            self._aggregation_leases.clear()
        finally:
            super().finish_aggregation_updates()

    def write_ttm_income(self, ttm_by_ticker: Mapping[str, float]) -> None:
        super().write_ttm_income(ttm_by_ticker)
        self._sync_to_azure()

    def write_last_dividend_decrease(
        self, last_decrease_by_ticker: Mapping[str, date]
    ) -> None:
        super().write_last_dividend_decrease(last_decrease_by_ticker)
        self._sync_to_azure()

    def write_years_since_dividend_decrease(
        self, years_since_by_ticker: Mapping[str, int]
    ) -> None:
        super().write_years_since_dividend_decrease(years_since_by_ticker)
        self._sync_to_azure()

    def write_dividends_by_year(self, dividends_by_year: pd.DataFrame) -> None:
        super().write_dividends_by_year(dividends_by_year)
        self._sync_to_azure()

    def write_years_consecutive_dividend_increase(
        self, years_consecutive_by_ticker: Mapping[str, int]
    ) -> None:
        super().write_years_consecutive_dividend_increase(years_consecutive_by_ticker)
        self._sync_to_azure()

    def write_dividend_history(self, body: pd.DataFrame) -> None:
        super().write_dividend_history(body)
        self._sync_to_azure()

    def write_tickers_to_cache(self, snapshots: list[TickerSnapshot]) -> None:
        super().write_tickers_to_cache(snapshots)
        self._sync_to_azure()
