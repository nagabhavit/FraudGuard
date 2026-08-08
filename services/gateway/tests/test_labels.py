"""Hermetic tests for POST /v1/transactions/{id}/labels -- request validation only.

Same reasoning as `test_transactions.py`: FastAPI validates path and body
against `LabelCreate` before the handler runs, so an invalid request never
touches `request.app.state.db`. The success (201) and not-found (404) paths
require a real transaction to reference, so they live in
`test_labels_integration.py` against the real stack instead of faked here --
see ADR-0005/ADR-0006 for why this project prefers the real thing over a
convincingly faked session for cases like these.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from gateway.app import create_app
from gateway.settings import GatewaySettings


def _client() -> TestClient:
    return TestClient(create_app(GatewaySettings(_env_file=None)))


def _valid_payload() -> dict[str, object]:
    return {"is_fraud": True, "source": "chargeback", "notes": "disputed by cardholder"}


def test_missing_source_is_rejected() -> None:
    payload = _valid_payload()
    del payload["source"]
    response = _client().post(f"/v1/transactions/{uuid4()}/labels", json=payload)
    assert response.status_code == 422


def test_missing_is_fraud_is_rejected() -> None:
    payload = _valid_payload()
    del payload["is_fraud"]
    response = _client().post(f"/v1/transactions/{uuid4()}/labels", json=payload)
    assert response.status_code == 422


def test_unknown_source_is_rejected() -> None:
    payload = _valid_payload()
    payload["source"] = "not_a_real_source"
    response = _client().post(f"/v1/transactions/{uuid4()}/labels", json=payload)
    assert response.status_code == 422


def test_invalid_transaction_id_is_rejected() -> None:
    response = _client().post(
        "/v1/transactions/not-a-uuid/labels", json=_valid_payload()
    )
    assert response.status_code == 422
