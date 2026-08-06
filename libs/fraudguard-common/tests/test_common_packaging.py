"""Packaging regression tests for fraudguard-common.

These contain no application logic. They assert that the workspace member is
correctly declared, built, and installed -- a class of breakage that otherwise
surfaces only when a container image fails to start in CI.
"""

from __future__ import annotations

import importlib.metadata

import fraudguard_common


def test_package_is_importable() -> None:
    assert fraudguard_common.__version__


def test_distribution_metadata_is_installed() -> None:
    """The hyphenated distribution name must resolve to the underscored module.

    If `[tool.hatch.build.targets.wheel] packages` is wrong, the import above
    can still succeed from the source tree while the distribution is missing.
    """
    dist = importlib.metadata.distribution("fraudguard-common")
    assert dist.metadata["Name"] == "fraudguard-common"


def test_declared_and_installed_versions_agree() -> None:
    """Catches a bumped __version__ that was never released, and vice versa."""
    assert (
        importlib.metadata.version("fraudguard-common") == fraudguard_common.__version__
    )
