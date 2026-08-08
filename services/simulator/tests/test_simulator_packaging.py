"""Packaging regression tests for fraudguard-simulator.

No application logic. These prove the workspace member installs correctly.
"""

from __future__ import annotations

import importlib.metadata

import simulator


def test_package_is_importable() -> None:
    assert simulator.__version__


def test_distribution_metadata_is_installed() -> None:
    dist = importlib.metadata.distribution("fraudguard-simulator")
    assert dist.metadata["Name"] == "fraudguard-simulator"


def test_declared_and_installed_versions_agree() -> None:
    assert importlib.metadata.version("fraudguard-simulator") == simulator.__version__
