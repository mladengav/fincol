"""Shared pytest fixtures and hooks.

Container start-up lives in ``testcontainers_<name>.py``; this module orders the tests
that need containers last and starts those containers in the background.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

import pytest
from azure.storage.blob import BlobServiceClient

from testcontainers_azurite import start_azurite
from testcontainers_mssql import start_mssql

if TYPE_CHECKING:
    from testcontainers.core.container import DockerContainer

_TESTCONTAINERS_FIXTURE_TAG = "testcontainers"


def _uses_testcontainers(item: pytest.Item) -> bool:
    """True if ``item`` depends (even transitively) on a ``testcontainers*`` fixture."""
    fixturenames = getattr(item, "fixturenames", ())
    return any(_TESTCONTAINERS_FIXTURE_TAG in name for name in fixturenames)


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark testcontainer-backed tests ``docker`` and run them after all others.

    Fast tests then report failures before any container starts. ``tryfirst`` adds the
    marker ahead of ``-m`` deselection, so ``pytest -m "not docker"`` works.
    """
    for item in items:
        if _uses_testcontainers(item):
            item.add_marker(pytest.mark.docker)
    items.sort(key=_uses_testcontainers)  # stable: keeps file order within each group


type _Started = tuple[DockerContainer, Any]  # lazily evaluated: import is type-only

_STARTERS: dict[str, Callable[[], _Started]] = {
    "testcontainers_blob_service_client": start_azurite,
    "testcontainers_mssql_url": start_mssql,
}
_executor: ThreadPoolExecutor | None = None
_pending: dict[str, Future[_Started]] = {}


def _start_reaper() -> None:
    """Create testcontainers' Ryuk reaper once, as ``DockerContainer.start`` would.

    ``Reaper.get_instance()`` isn't thread-safe, so it must exist before containers
    start in parallel, or a second, orphaned reaper could remove them mid-run.
    """
    try:
        from testcontainers.core.config import testcontainers_config
        from testcontainers.core.container import Reaper

        if not testcontainers_config.ryuk_disabled:
            Reaper.get_instance()
    except Exception:  # pragma: no cover - surfaces again from the container starters
        pass


def _after(
    first: Future[None], starter: Callable[[], _Started]
) -> Callable[[], _Started]:
    def run() -> _Started:
        first.result()
        return starter()

    return run


def pytest_collection_finish(session: pytest.Session) -> None:
    """Start the containers the selected tests need while the fast tests run."""
    global _executor
    if session.config.option.collectonly:
        return
    needed = [
        name
        for name in _STARTERS
        if any(name in getattr(item, "fixturenames", ()) for item in session.items)
    ]
    if not needed:
        return
    _executor = ThreadPoolExecutor(
        max_workers=len(needed), thread_name_prefix="testcontainers"
    )
    reaper = _executor.submit(_start_reaper)
    for name in needed:
        _pending[name] = _executor.submit(_after(reaper, _STARTERS[name]))


def pytest_sessionfinish() -> None:
    """Stop containers started in the background whose fixture never ran (e.g. ``-x``)."""
    for future in _pending.values():
        if not future.cancel() and future.exception() is None:
            future.result()[0].stop()
    _pending.clear()
    if _executor is not None:
        _executor.shutdown()


def _started(name: str) -> _Started:
    """Take the background startup of fixture ``name``, or start it now if there's none.

    A starter's ``pytest.skip`` (Docker unavailable) re-raises here via the future.
    """
    future = _pending.pop(name, None)
    return future.result() if future is not None else _STARTERS[name]()


@pytest.fixture(scope="session")
def testcontainers_blob_service_client() -> Iterator[BlobServiceClient]:
    """Azurite blob emulator, started once per session; yields a client to it."""
    container, client = _started("testcontainers_blob_service_client")
    try:
        yield client
    finally:
        container.stop()


@pytest.fixture(scope="session")
def testcontainers_mssql_url() -> Iterator[str]:
    """SQL Server, started once per session with ``fincol_test`` from ``Initial.sql``.

    Yields the SQLAlchemy URL of that database.
    """
    container, url = _started("testcontainers_mssql_url")
    try:
        yield url
    finally:
        container.stop()
