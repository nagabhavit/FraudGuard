"""Packaging regression tests for fraudguard-features.

No application logic. These prove the workspace member installs correctly.
"""

from __future__ import annotations

import importlib.metadata

import fraudguard_features


def test_package_is_importable() -> None:
    assert fraudguard_features.__version__


def test_distribution_metadata_is_installed() -> None:
    dist = importlib.metadata.distribution("fraudguard-features")
    assert dist.metadata["Name"] == "fraudguard-features"


def test_declared_and_installed_versions_agree() -> None:
    assert (
        importlib.metadata.version("fraudguard-features")
        == fraudguard_features.__version__
    )
