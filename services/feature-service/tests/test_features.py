"""Hermetic tests for GET /v1/features/{account_id}.

Uses a fake feature store so this suite stays hermetic. The real Redis
round trip (velocity windows, HyperLogLog diversity) is covered by
fraudguard-features' own integration tests and by
test_features_integration.py in this service.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from feature_service.app import create_app
from feature_service.settings import FeatureServiceSettings


class _FakeFeatureStore:
    def __init__(self, vector: dict[str, int]) -> None:
        self._vector = vector

    async def ping(self) -> None:
        pass

    async def get_feature_vector(self, account_id: str) -> dict[str, int]:
        return self._vector

    async def close(self) -> None:
        pass


def _client(vector: dict[str, int]) -> TestClient:
    settings = FeatureServiceSettings(_env_file=None)
    return TestClient(create_app(settings, store=_FakeFeatureStore(vector)))


def test_returns_the_feature_vector_for_a_valid_account() -> None:
    account_id = uuid4()
    vector = {
        "velocity_1m": 1,
        "velocity_1h": 4,
        "velocity_24h": 9,
        "distinct_merchants_24h": 3,
    }

    response = _client(vector).get(f"/v1/features/{account_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["account_id"] == str(account_id)
    assert body["velocity_1m"] == 1
    assert body["velocity_1h"] == 4
    assert body["velocity_24h"] == 9
    assert body["distinct_merchants_24h"] == 3
    assert "computed_at" in body


def test_invalid_account_id_is_rejected() -> None:
    response = _client({}).get("/v1/features/not-a-uuid")
    assert response.status_code == 422
