"""Packaging regression tests for fraudguard-feature-service.

No application logic. These prove the workspace member installs correctly
and that its dependency on fraudguard-features resolves through the
workspace rather than PyPI.
"""

from __future__ import annotations

import importlib.metadata

import feature_service


def test_package_is_importable() -> None:
    assert feature_service.__version__


def test_distribution_metadata_is_installed() -> None:
    dist = importlib.metadata.distribution("fraudguard-feature-service")
    assert dist.metadata["Name"] == "fraudguard-feature-service"


def test_declared_and_installed_versions_agree() -> None:
    assert (
        importlib.metadata.version("fraudguard-feature-service")
        == feature_service.__version__
    )


def test_workspace_dependency_on_features_is_resolved() -> None:
    requires = importlib.metadata.requires("fraudguard-feature-service") or []
    assert any(req.startswith("fraudguard-features") for req in requires)

    import fraudguard_features

    assert fraudguard_features.__version__
