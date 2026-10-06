"""Azurite blob-storage emulator testcontainer, served by ``conftest.py``."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from azure.storage.blob import BlobServiceClient

if TYPE_CHECKING:
    from testcontainers.community.azurite import AzuriteContainer


def start_azurite() -> tuple[AzuriteContainer, BlobServiceClient]:
    """Start Azurite and return ``(container, BlobServiceClient)``.

    Skips when Docker / testcontainers are unavailable so local runs don't hard-fail.
    """
    try:
        from testcontainers.community.azurite import AzuriteContainer
        from testcontainers.core.wait_strategies import LogMessageWaitStrategy

        container = AzuriteContainer()
        container.start()
    except Exception as exc:  # pragma: no cover - dev extra / Docker / image pull
        pytest.skip(f"Azurite testcontainer unavailable: {exc}")

    try:
        # The built-in port wait passes once Docker's port proxy accepts, before Azurite
        # listens; the first SDK call then fails and backs off ~15s before retrying.
        LogMessageWaitStrategy(
            "Blob service is successfully listening"
        ).with_poll_interval(0.1).wait_until_ready(container)
        # Pin api_version: the SDK default outruns what the Azurite image supports.
        client = BlobServiceClient.from_connection_string(
            container.get_connection_string(), api_version="2025-01-05"
        )
    except BaseException:
        container.stop()
        raise
    return container, client
