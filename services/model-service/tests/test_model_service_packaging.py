"""Packaging regression tests for fraudguard-model-service.

No application logic. These prove the workspace member installs correctly
and that its dependency on fraudguard-ml resolves through the workspace
rather than PyPI.
"""

from __future__ import annotations

import importlib.metadata

import model_service


def test_package_is_importable() -> None:
    assert model_service.__version__


def test_distribution_metadata_is_installed() -> None:
    dist = importlib.metadata.distribution("fraudguard-model-service")
    assert dist.metadata["Name"] == "fraudguard-model-service"


def test_declared_and_installed_versions_agree() -> None:
    assert (
        importlib.metadata.version("fraudguard-model-service")
        == model_service.__version__
    )


def test_workspace_dependency_on_ml_is_resolved() -> None:
    requires = importlib.metadata.requires("fraudguard-model-service") or []
    assert any(req.startswith("fraudguard-ml") for req in requires)

    import fraudguard_ml

    assert fraudguard_ml.__version__
