"""Packaging regression tests for fraudguard-gateway.

No application logic. These prove the workspace member installs correctly and
that its dependency on fraudguard-common resolves through the workspace rather
than PyPI.
"""

from __future__ import annotations

import importlib.metadata

import gateway


def test_package_is_importable() -> None:
    assert gateway.__version__


def test_distribution_metadata_is_installed() -> None:
    dist = importlib.metadata.distribution("fraudguard-gateway")
    assert dist.metadata["Name"] == "fraudguard-gateway"


def test_declared_and_installed_versions_agree() -> None:
    assert importlib.metadata.version("fraudguard-gateway") == gateway.__version__


def test_workspace_dependency_on_common_is_resolved() -> None:
    """The gateway must get fraudguard-common from the workspace.

    If [tool.uv.sources] were dropped, uv would try PyPI, where this package
    does not exist. A green build here means the workspace wiring is intact.
    """
    requires = importlib.metadata.requires("fraudguard-gateway") or []
    assert any(req.startswith("fraudguard-common") for req in requires)

    import fraudguard_common

    assert fraudguard_common.__version__
