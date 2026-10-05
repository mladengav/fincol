"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from azure.storage.blob import BlobServiceClient


@pytest.fixture(scope="session")
def azurite_blob_service_client() -> Iterator[BlobServiceClient]:
    """Start an Azurite blob emulator once per session and yield a client to it.

    Skipped when Docker / testcontainers are unavailable so local runs don't hard-fail.
    """
    try:
        from testcontainers.community.azurite import AzuriteContainer
    except ImportError:  # pragma: no cover - dev extra not installed
        pytest.skip("testcontainers[azurite] is not installed")

    try:
        container = AzuriteContainer()
        container.start()
    except Exception as exc:  # pragma: no cover - Docker unavailable / image pull
        pytest.skip(f"Azurite testcontainer unavailable: {exc}")

    try:
        # Pin api_version: the SDK default outruns what the Azurite image supports.
        yield BlobServiceClient.from_connection_string(
            container.get_connection_string(), api_version="2025-01-05"
        )
    finally:
        container.stop()
