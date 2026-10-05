"""Exceptions raised by infrastructure adapters."""

from __future__ import annotations


class AggregationLockError(RuntimeError):
    """Aggregation artifacts could not be locked, or were written without a lock."""
