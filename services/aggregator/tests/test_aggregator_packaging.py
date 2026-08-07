"""Packaging regression tests for fraudguard-aggregator.

No application logic. These prove the workspace member installs correctly
and that its dependencies on fraudguard-events and fraudguard-features
resolve through the workspace rather than PyPI.
"""

from __future__ import annotations

import importlib.metadata

import aggregator


def test_package_is_importable() -> None:
    assert aggregator.__version__


def test_distribution_metadata_is_installed() -> None:
    dist = importlib.metadata.distribution("fraudguard-aggregator")
    assert dist.metadata["Name"] == "fraudguard-aggregator"


def test_declared_and_installed_versions_agree() -> None:
    assert importlib.metadata.version("fraudguard-aggregator") == aggregator.__version__


def test_workspace_dependencies_are_resolved() -> None:
    requires = importlib.metadata.requires("fraudguard-aggregator") or []
    assert any(req.startswith("fraudguard-events") for req in requires)
    assert any(req.startswith("fraudguard-features") for req in requires)

    import fraudguard_events
    import fraudguard_features

    assert fraudguard_events.__version__
    assert fraudguard_features.__version__
