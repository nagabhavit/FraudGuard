"""Tests that the shared error taxonomy is translated into HTTP responses."""

from __future__ import annotations

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from fraudguard_common.errors import ValidationError
from model_service.app import create_app
from model_service.errors import fraudguard_error_handler
from model_service.settings import ModelServiceSettings


class _FakeModel:
    version = "fake-v1"

    def predict_proba(self, row: list[float]) -> float:
        return 0.1

    def explain(self, row: list[float], top_n: int = 3) -> list[str]:
        return []


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
    app = create_app(ModelServiceSettings(_env_file=None), model=_FakeModel())

    @app.get("/__test__/invalid")
    async def _raise_invalid() -> None:
        raise ValidationError("row has an unexpected shape")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/__test__/invalid")

    assert response.status_code == 422
    assert response.json() == {
        "error_code": "validation_error",
        "message": "row has an unexpected shape",
    }
