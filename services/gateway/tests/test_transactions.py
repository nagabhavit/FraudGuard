"""Hermetic tests for POST /v1/transactions -- request validation only.

FastAPI validates the request body against `TransactionCreate` before the
handler runs, so a malformed request never reaches the database or the
event publisher. That means these tests need no fakes at all: an invalid
payload never touches `request.app.state.db` or `request.app.state.events`.

The success path -- persisting to Postgres and publishing to Kafka -- is
covered by `test_transactions_integration.py` against the real stack, not
faked here. See ADR-0005 and ADR-0006 for why: faking a SQLAlchemy session's
server-generated columns (id, created_at) convincingly enough to trust is
harder than just running the real thing.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from gateway.app import create_app
from gateway.settings import GatewaySettings


def _client() -> TestClient:
    return TestClient(create_app(GatewaySettings(_env_file=None)))


def _valid_payload() -> dict[str, object]:
    return {
        "account_id": "d975f45f-e13c-4934-b6bc-ed86130a8f27",
        "merchant_id": "merchant-1",
        "amount": "42.50",
        "currency": "USD",
        "occurred_at": "2026-08-07T12:00:00Z",
    }


def test_missing_field_is_rejected() -> None:
    payload = _valid_payload()
    del payload["merchant_id"]
    response = _client().post("/v1/transactions", json=payload)
    assert response.status_code == 422


def test_non_positive_amount_is_rejected() -> None:
    payload = _valid_payload()
    payload["amount"] = "0"
    response = _client().post("/v1/transactions", json=payload)
    assert response.status_code == 422


def test_currency_must_be_three_characters() -> None:
    payload = _valid_payload()
    payload["currency"] = "US"
    response = _client().post("/v1/transactions", json=payload)
    assert response.status_code == 422


def test_invalid_account_id_is_rejected() -> None:
    payload = _valid_payload()
    payload["account_id"] = "not-a-uuid"
    response = _client().post("/v1/transactions", json=payload)
    assert response.status_code == 422


def test_naive_occurred_at_is_rejected() -> None:
    payload = _valid_payload()
    payload["occurred_at"] = "2026-08-07T12:00:00"  # no timezone offset
    response = _client().post("/v1/transactions", json=payload)
    assert response.status_code == 422
    assert "timezone" in response.text


# GET /v1/transactions (ADR-0012): query-param bounds are validated by
# FastAPI before the handler runs, the same reason the POST tests above need
# no database fake -- an out-of-range limit/offset never reaches
# `request.app.state.db`.


def test_limit_must_be_positive() -> None:
    response = _client().get("/v1/transactions", params={"limit": 0})
    assert response.status_code == 422


def test_limit_cannot_exceed_two_hundred() -> None:
    response = _client().get("/v1/transactions", params={"limit": 201})
    assert response.status_code == 422


def test_offset_cannot_be_negative() -> None:
    response = _client().get("/v1/transactions", params={"offset": -1})
    assert response.status_code == 422
