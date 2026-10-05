"""Aggregation locking tests for :class:`infrastructure.csv.azblob_io.AzBlobCsvFincolIo`.

Backed by the shared Azurite fixture in ``conftest.py``; skipped when Docker /
testcontainers are unavailable.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pytest
from azure.core.exceptions import HttpResponseError
from azure.storage.blob import BlobServiceClient, ContainerClient
from pytest_mock import MockerFixture

from application.aggregation_updater import AggregationUpdater
from constants import BCE_TO, TESTCACHE_DIVIDEND_HISTORY_CSV
from infrastructure.csv import AzBlobCsvFincolIo
from infrastructure.errors import AggregationLockError

_CONTAINER_NAME = "csvcache"
_AGGREGATION_BLOBS = [
    "aggregations/ttm_income.csv",
    "aggregations/last_dividend_decrease.csv",
    "aggregations/years_since_dividend_decrease.csv",
    "aggregations/dividends_by_year.csv",
    "aggregations/years_consecutive_dividend_increase.csv",
]


@pytest.fixture
def csvcache(
    azurite_blob_service_client: BlobServiceClient,
) -> Iterator[ContainerClient]:
    """Create an empty ``csvcache`` container for one test and delete it afterwards."""
    container_client = azurite_blob_service_client.create_container(_CONTAINER_NAME)
    try:
        yield container_client
    finally:
        container_client.delete_container()


def _lease_states(container_client: ContainerClient) -> dict[str, str]:
    return {
        name: container_client.get_blob_client(name).get_blob_properties().lease.state
        for name in _AGGREGATION_BLOBS
    }


def _local_lock_paths(cache: Path) -> list[Path]:
    return [cache / f"{name}.lock" for name in _AGGREGATION_BLOBS]


def test_begin_leases_aggregation_blobs(
    azurite_blob_service_client: BlobServiceClient,
    csvcache: ContainerClient,
    tmp_path: Path,
) -> None:
    """While locked, aggregation blobs are leased and cannot be overwritten without the lease."""
    fincol_io = AzBlobCsvFincolIo(azurite_blob_service_client, folder=tmp_path)
    fincol_io.begin_aggregation_updates()

    assert set(_lease_states(csvcache).values()) == {"leased"}
    for lock_path in _local_lock_paths(tmp_path):
        assert lock_path.is_file(), f"expected local lock {lock_path}"
    with pytest.raises(HttpResponseError):
        csvcache.upload_blob(_AGGREGATION_BLOBS[0], b"intruder", overwrite=True)

    fincol_io.finish_aggregation_updates()

    assert set(_lease_states(csvcache).values()) == {"available"}
    for lock_path in _local_lock_paths(tmp_path):
        assert not lock_path.exists(), f"local lock {lock_path} not released"


def test_writes_under_lease_upload_to_blob(
    azurite_blob_service_client: BlobServiceClient,
    csvcache: ContainerClient,
    tmp_path: Path,
) -> None:
    """Aggregation writes made while holding the lease reach Azure; lock files never do."""
    fincol_io = AzBlobCsvFincolIo(azurite_blob_service_client, folder=tmp_path)
    fincol_io.begin_aggregation_updates()
    fincol_io.write_ttm_income({"X.TO": 1.0})
    fincol_io.finish_aggregation_updates()

    content = csvcache.download_blob("aggregations/ttm_income.csv").readall()
    assert b'"X.TO",1.0000' in content
    assert not [b.name for b in csvcache.list_blobs() if b.name.endswith(".lock")]


def test_second_instance_cannot_begin_while_leased(
    azurite_blob_service_client: BlobServiceClient,
    csvcache: ContainerClient,
    tmp_path: Path,
) -> None:
    """A second writer is refused while the first holds the leases, and keeps no locks."""
    holder = AzBlobCsvFincolIo(azurite_blob_service_client, folder=tmp_path / "a")
    holder.begin_aggregation_updates()
    other_folder = tmp_path / "b"
    other = AzBlobCsvFincolIo(azurite_blob_service_client, folder=other_folder)

    with pytest.raises(AggregationLockError):
        other.begin_aggregation_updates()

    for lock_path in _local_lock_paths(other_folder):
        assert not lock_path.exists(), f"refused writer left lock {lock_path}"
    assert set(_lease_states(csvcache).values()) == {"leased"}

    holder.finish_aggregation_updates()


def test_update_aggregations_releases_leases_on_error(
    azurite_blob_service_client: BlobServiceClient,
    csvcache: ContainerClient,
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """An exception mid-batch propagates and both leases and local locks are released."""
    fincol_io = AzBlobCsvFincolIo(azurite_blob_service_client, folder=tmp_path)
    div_hist = pd.read_csv(TESTCACHE_DIVIDEND_HISTORY_CSV)
    fincol_io.write_dividend_history(
        div_hist.loc[div_hist["ticker"] == BCE_TO, ["ticker", "date", "amount"]]
    )
    mocker.patch.object(
        fincol_io, "write_dividends_by_year", side_effect=RuntimeError("boom")
    )

    with pytest.raises(RuntimeError, match="boom"):
        AggregationUpdater(fincol_io).update_aggregations([BCE_TO])

    assert set(_lease_states(csvcache).values()) == {"available"}
    for lock_path in _local_lock_paths(tmp_path):
        assert not lock_path.exists(), f"local lock {lock_path} not released"
