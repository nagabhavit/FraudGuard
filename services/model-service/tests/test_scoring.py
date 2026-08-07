"""Hermetic tests for POST /v1/score -- a fake model, no real LightGBM
booster required. The real model (training, loading, actual predictions)
is exercised by test_scoring_integration.py.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from model_service.app import create_app
from model_service.settings import ModelServiceSettings


class _FakeModel:
    def __init__(self, risk_score: float) -> None:
        self._risk_score = risk_score
        self.version = "fake-v1"
        self.last_row: list[float] | None = None

    def predict_proba(self, row: list[float]) -> float:
        self.last_row = row
        return self._risk_score

    def explain(self, row: list[float], top_n: int = 3) -> list[str]:
        return ["amount", "velocity_1h"][:top_n]


def _client(risk_score: float) -> tuple[TestClient, _FakeModel]:
    model = _FakeModel(risk_score)
    settings = ModelServiceSettings(_env_file=None)
    return TestClient(create_app(settings, model=model)), model


def _payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "amount": "42.50",
        "velocity_1m": 1,
        "velocity_1h": 3,
        "velocity_24h": 10,
        "distinct_merchants_24h": 2,
    }
    base.update(overrides)
    return base


def test_low_risk_score_is_approved() -> None:
    client, _ = _client(risk_score=0.1)
    response = client.post("/v1/score", json=_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "approve"
    assert body["risk_score"] == 0.1
    assert body["model_version"] == "fake-v1"
    assert body["reason_codes"] == ["amount", "velocity_1h"]


def test_high_risk_score_is_declined() -> None:
    client, _ = _client(risk_score=0.9)
    response = client.post("/v1/score", json=_payload())
    assert response.json()["outcome"] == "decline"


def test_mid_risk_score_is_sent_for_review() -> None:
    client, _ = _client(risk_score=0.5)
    response = client.post("/v1/score", json=_payload())
    assert response.json()["outcome"] == "review"


def test_thresholds_are_exclusive_boundaries() -> None:
    # Exactly at approve_below (0.3) is not < 0.3, so it is "review", not
    # "approve" -- and exactly at decline_above (0.7) is not > 0.7, so it
    # is "review", not "decline". Both boundaries are inclusive of review.
    approve_boundary, _ = _client(risk_score=0.3)
    decline_boundary, _ = _client(risk_score=0.7)
    assert (
        approve_boundary.post("/v1/score", json=_payload()).json()["outcome"]
        == "review"
    )
    assert (
        decline_boundary.post("/v1/score", json=_payload()).json()["outcome"]
        == "review"
    )


def test_feature_row_is_built_in_the_canonical_order() -> None:
    client, model = _client(risk_score=0.1)
    client.post(
        "/v1/score",
        json=_payload(
            amount="10.00",
            velocity_1m=1,
            velocity_1h=2,
            velocity_24h=3,
            distinct_merchants_24h=4,
        ),
    )
    assert model.last_row == [10.0, 1.0, 2.0, 3.0, 4.0]


def test_negative_amount_is_rejected() -> None:
    client, _ = _client(risk_score=0.1)
    response = client.post("/v1/score", json=_payload(amount="-5.00"))
    assert response.status_code == 422


def test_negative_velocity_is_rejected() -> None:
    client, _ = _client(risk_score=0.1)
    response = client.post("/v1/score", json=_payload(velocity_1m=-1))
    assert response.status_code == 422
