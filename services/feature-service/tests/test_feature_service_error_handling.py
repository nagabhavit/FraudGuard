"""Tests that the shared error taxonomy is translated into HTTP responses."""

from __future__ import annotations

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from feature_service.app import create_app
from feature_service.errors import fraudguard_error_handler
from feature_service.settings import FeatureServiceSettings
from fraudguard_common.errors import UpstreamUnavailableError


async def test_handler_reraises_exceptions_outside_the_taxonomy() -> None:
    """Defensive branch: FastAPI only ever calls this handler for
    `FraudGuardError` (or a subclass), so this exercises the guard directly
    rather than relying on being unreachable through the app.
    """
    scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
    request = Request(scope)

    with pytest.raises(ValueError, match="not a FraudGuardError"):
        await fraudguard_error_handler(request, ValueError("not a FraudGuardError"))


def test_fraudguard_error_is_translated_to_its_http_status_and_code() -> None:
    app = create_app(FeatureServiceSettings(_env_file=None))

    @app.get("/__test__/unavailable")
    async def _raise_unavailable() -> None:
        raise UpstreamUnavailableError("redis circuit open")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/__test__/unavailable")

    assert response.status_code == 503
    assert response.json() == {
        "error_code": "upstream_unavailable",
        "message": "redis circuit open",
    }
