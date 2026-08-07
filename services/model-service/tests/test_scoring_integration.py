"""Integration test against the real trained model.

Requires `ml/pipelines/train.py` to have been run (`ml/models/fraud_model.txt`
and its metadata must exist) -- marked `integration` for the same reason as
the other services' integration suites depending on external, out-of-band
setup, even though this one needs a trained artifact rather than a live
docker compose service.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fraudguard_ml import FEATURE_NAMES
from model_service.app import create_app
from model_service.settings import ModelServiceSettings

pytestmark = pytest.mark.integration


def _client() -> TestClient:
    return TestClient(create_app(ModelServiceSettings(_env_file=None)))


def test_scores_a_low_activity_transaction() -> None:
    response = _client().post(
        "/v1/score",
        json={
            "amount": "20.00",
            "velocity_1m": 0,
            "velocity_1h": 0,
            "velocity_24h": 1,
            "distinct_merchants_24h": 1,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] in ("approve", "decline", "review")
    assert 0.0 <= body["risk_score"] <= 1.0
    assert body["model_version"].startswith("fraud-lgbm-")
    assert 1 <= len(body["reason_codes"]) <= 3
    assert all(name in FEATURE_NAMES for name in body["reason_codes"])


def test_a_bursty_high_velocity_transaction_scores_higher_than_a_quiet_one() -> None:
    client = _client()

    quiet = client.post(
        "/v1/score",
        json={
            "amount": "15.00",
            "velocity_1m": 0,
            "velocity_1h": 0,
            "velocity_24h": 0,
            "distinct_merchants_24h": 0,
        },
    ).json()
    bursty = client.post(
        "/v1/score",
        json={
            "amount": "900.00",
            "velocity_1m": 5,
            "velocity_1h": 15,
            "velocity_24h": 30,
            "distinct_merchants_24h": 8,
        },
    ).json()

    # Not a hardcoded expectation of the exact score -- a real property the
    # trained model should have, given how the synthetic labels were
    # generated (ml/pipelines/train.py): elevated velocity, diversity, and
    # amount all push risk up.
    assert bursty["risk_score"] > quiet["risk_score"]


def test_readiness_reports_the_real_model_is_loaded() -> None:
    response = _client().get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"model": "ok"}}
