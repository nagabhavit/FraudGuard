"""Unit tests for FeatureStore's pure-Python validation -- no Redis required.

Behaviour that actually touches Redis (writes, windowed reads, HLL
diversity) is covered by test_store_integration.py against the real
service, not mocked here -- see ADR-0007.
"""

from __future__ import annotations

import pytest

from fraudguard_features.store import FeatureStore


async def test_get_velocity_rejects_an_unknown_window() -> None:
    store = FeatureStore()
    with pytest.raises(ValueError, match="unknown velocity window"):
        await store.get_velocity("some-account", "1w")
