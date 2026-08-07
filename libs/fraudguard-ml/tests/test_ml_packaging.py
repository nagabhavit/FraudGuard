"""Packaging regression tests for fraudguard-ml.

No application logic. These prove the workspace member installs correctly.
"""

from __future__ import annotations

import importlib.metadata

import fraudguard_ml


def test_package_is_importable() -> None:
    assert fraudguard_ml.__version__


def test_distribution_metadata_is_installed() -> None:
    dist = importlib.metadata.distribution("fraudguard-ml")
    assert dist.metadata["Name"] == "fraudguard-ml"


def test_declared_and_installed_versions_agree() -> None:
    assert importlib.metadata.version("fraudguard-ml") == fraudguard_ml.__version__
