"""Packaging regression tests for fraudguard-db.

No application logic. These prove the workspace member installs correctly.
"""

from __future__ import annotations

import importlib.metadata

import fraudguard_db


def test_package_is_importable() -> None:
    assert fraudguard_db.__version__


def test_distribution_metadata_is_installed() -> None:
    dist = importlib.metadata.distribution("fraudguard-db")
    assert dist.metadata["Name"] == "fraudguard-db"


def test_declared_and_installed_versions_agree() -> None:
    assert importlib.metadata.version("fraudguard-db") == fraudguard_db.__version__
