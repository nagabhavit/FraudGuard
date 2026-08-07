"""Tests for the liveness and readiness endpoints.

Uses a fake model rather than a real trained one -- this suite must stay
hermetic and pass without ml/pipelines/train.py having been run. The real
model is exercised by test_scoring_integration.py.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from model_service.app import create_app
from model_service.settings import ModelServiceSettings


class _FakeModel:
    version = "fake-v1"

    def predict_proba(self, row: list[float]) -> float:
        return 0.1

    def explain(self, row: list[float], top_n: int = 3) -> list[str]:
        return []


def _client() -> TestClient:
    settings = ModelServiceSettings(_env_file=None)
    return TestClient(create_app(settings, model=_FakeModel()))


def test_liveness_reports_ok() -> None:
    response = _client().get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {}}


def test_readiness_reports_ok() -> None:
    response = _client().get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"model": "ok"}}
