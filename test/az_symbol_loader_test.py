"""Tests for :class:`infrastructure.csv.az_symbol_loader.AzCsvSymbolLoader`.

Backed by an Azurite blob-storage emulator running in a testcontainer; the test is
skipped when Docker / testcontainers are unavailable so local runs don't hard-fail.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from azure.storage.blob import BlobServiceClient

from infrastructure.csv import AzCsvSymbolLoader

_INPUT_SYMBOLS_CSV = Path(__file__).resolve().parent.parent / "input_symbols.csv"
_CONTAINER_NAME = "csvinputs"
_BLOB_NAME = "input_symbols.csv"


@pytest.fixture
def blob_service_client() -> Iterator[BlobServiceClient]:
    """Start Azurite, seed ``csvinputs/input_symbols.csv``, and yield a client to it."""
    try:
        from testcontainers.azurite import AzuriteContainer
    except ImportError:  # pragma: no cover - dev extra not installed
        pytest.skip("testcontainers[azurite] is not installed")

    try:
        container = AzuriteContainer()
        container.start()
    except Exception as exc:  # pragma: no cover - Docker unavailable / image pull
        pytest.skip(f"Azurite testcontainer unavailable: {exc}")

    try:
        # Pin api_version: the SDK default outruns what the Azurite image supports.
        client = BlobServiceClient.from_connection_string(
            container.get_connection_string(), api_version="2025-01-05"
        )
        container_client = client.create_container(_CONTAINER_NAME)
        container_client.upload_blob(
            _BLOB_NAME, _INPUT_SYMBOLS_CSV.read_bytes(), overwrite=True
        )
        yield client
    finally:
        container.stop()


def test_loads_symbols_from_azurite_blob(
    blob_service_client: BlobServiceClient,
) -> None:
    with AzCsvSymbolLoader(blob_service_client=blob_service_client) as loader:
        temp_dir = loader._temp_dir
        assert temp_dir.is_dir()
        assert loader.load_symbols() == ["TD.TO", "BNS.TO", "BCE.TO"]

    # __exit__ removes the temp folder it downloaded the blob into.
    assert not temp_dir.exists()
