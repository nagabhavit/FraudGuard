"""Tests that the shared error taxonomy is translated into HTTP responses."""

from __future__ import annotations

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from fraudguard_common.errors import NotFoundError
from gateway.app import create_app
from gateway.errors import fraudguard_error_handler
from gateway.settings import GatewaySettings


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
    app = create_app(GatewaySettings(_env_file=None))

    @app.get("/__test__/not-found")
    async def _raise_not_found() -> None:
        raise NotFoundError("account 123 does not exist")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/__test__/not-found")

    assert response.status_code == 404
    assert response.json() == {
        "error_code": "not_found",
        "message": "account 123 does not exist",
    }
