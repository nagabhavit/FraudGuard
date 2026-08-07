"""Packaging regression tests for fraudguard-events.

No application logic. These prove the workspace member installs correctly
and, critically, that the bundled .avsc schema ships inside the wheel --
that is data, not code, and hatchling does not include it by accident.
"""

from __future__ import annotations

import importlib.metadata

import fraudguard_events


def test_package_is_importable() -> None:
    assert fraudguard_events.__version__


def test_distribution_metadata_is_installed() -> None:
    dist = importlib.metadata.distribution("fraudguard-events")
    assert dist.metadata["Name"] == "fraudguard-events"


def test_declared_and_installed_versions_agree() -> None:
    assert (
        importlib.metadata.version("fraudguard-events") == fraudguard_events.__version__
    )


def test_bundled_avro_schema_is_reachable_from_the_installed_package() -> None:
    schema = fraudguard_events.load_schema("transaction_received")
    assert schema["name"] == "TransactionReceived"
