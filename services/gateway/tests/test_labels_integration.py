"""Integration tests for POST /v1/transactions/{id}/labels against the real stack.

Requires the docker compose stack (postgres) -- marked `integration` for the
same reason as `test_transactions_integration.py`. Covers what
`test_labels.py` cannot without faking a SQLAlchemy session convincingly
enough to trust (ADR-0005): the 201 success path, the 404 path against a
transaction that genuinely does not exist, and the embedded-label shape
`GET /v1/transactions` now returns (ADR-0014).
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from fraudguard_common.metrics import render_metrics
from fraudguard_db.models import Label
from fraudguard_db.session import Database, DatabaseSettings
from gateway.app import create_app
from gateway.settings import GatewaySettings

pytestmark = pytest.mark.integration


def _metric_value(metric_name: str, **labels: str) -> float:
    text = render_metrics()[0].decode()
    label_str = ",".join(f'{key}="{value}"' for key, value in sorted(labels.items()))
    prefix = f"{metric_name}{{{label_str}}} " if labels else f"{metric_name} "
    for line in text.splitlines():
        if line.startswith(prefix):
            return float(line.removeprefix(prefix))
    return 0.0


def _post_transaction(client: TestClient) -> UUID:
    payload = {
        "account_id": str(uuid4()),
        "merchant_id": "integration-test-merchant",
        "amount": "55.00",
        "currency": "USD",
        "occurred_at": "2026-08-09T09:00:00Z",
    }
    response = client.post("/v1/transactions", json=payload)
    assert response.status_code == 200
    return UUID(response.json()["transaction_id"])


async def test_create_label_persists_for_real() -> None:
    app = create_app(GatewaySettings(_env_file=None))

    labels_before = _metric_value(
        "fraudguard_gateway_labels_total", source="chargeback", is_fraud="true"
    )

    with TestClient(app) as client:
        transaction_id = _post_transaction(client)
        response = client.post(
            f"/v1/transactions/{transaction_id}/labels",
            json={
                "is_fraud": True,
                "source": "chargeback",
                "notes": "cardholder disputed the charge",
            },
        )
    assert response.status_code == 201
    body = response.json()
    assert body["transaction_id"] == str(transaction_id)
    assert body["is_fraud"] is True
    assert body["source"] == "chargeback"
    assert body["notes"] == "cardholder disputed the charge"

    labels_after = _metric_value(
        "fraudguard_gateway_labels_total", source="chargeback", is_fraud="true"
    )
    assert labels_after == labels_before + 1.0

    db = Database(DatabaseSettings())
    try:
        async with db.session() as session:
            stored = await session.scalar(
                select(Label).where(Label.transaction_id == transaction_id)
            )
        assert stored is not None
        assert stored.is_fraud is True
        assert stored.source.value == "chargeback"
    finally:
        await db.dispose()


async def test_create_label_without_notes_defaults_to_null() -> None:
    app = create_app(GatewaySettings(_env_file=None))
    with TestClient(app) as client:
        transaction_id = _post_transaction(client)
        response = client.post(
            f"/v1/transactions/{transaction_id}/labels",
            json={"is_fraud": False, "source": "manual_review"},
        )
    assert response.status_code == 201
    assert response.json()["notes"] is None


async def test_create_label_for_missing_transaction_is_404() -> None:
    app = create_app(GatewaySettings(_env_file=None))
    with TestClient(app) as client:
        response = client.post(
            f"/v1/transactions/{uuid4()}/labels",
            json={"is_fraud": True, "source": "customer_report"},
        )
    assert response.status_code == 404
    assert response.json()["error_code"] == "not_found"


async def test_multiple_labels_on_one_transaction_are_all_kept() -> None:
    """ADR-0005/ADR-0014: a chargeback and a manual review can disagree."""
    app = create_app(GatewaySettings(_env_file=None))
    with TestClient(app) as client:
        transaction_id = _post_transaction(client)
        first = client.post(
            f"/v1/transactions/{transaction_id}/labels",
            json={"is_fraud": True, "source": "chargeback"},
        )
        second = client.post(
            f"/v1/transactions/{transaction_id}/labels",
            json={"is_fraud": False, "source": "manual_review"},
        )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


async def test_list_transactions_embeds_its_labels() -> None:
    app = create_app(GatewaySettings(_env_file=None))
    with TestClient(app) as client:
        transaction_id = _post_transaction(client)
        no_labels_yet = client.get("/v1/transactions", params={"limit": 200})
        matching = [
            item
            for item in no_labels_yet.json()["items"]
            if item["transaction_id"] == str(transaction_id)
        ]
        assert len(matching) == 1
        assert matching[0]["labels"] == []

        create_response = client.post(
            f"/v1/transactions/{transaction_id}/labels",
            json={"is_fraud": True, "source": "customer_report", "notes": "hmm"},
        )
        assert create_response.status_code == 201
        created_label = create_response.json()

        after = client.get("/v1/transactions", params={"limit": 200})
    matching = [
        item
        for item in after.json()["items"]
        if item["transaction_id"] == str(transaction_id)
    ]
    assert len(matching) == 1
    labels = matching[0]["labels"]
    assert len(labels) == 1
    assert labels[0]["id"] == created_label["id"]
    assert labels[0]["is_fraud"] is True
    assert labels[0]["source"] == "customer_report"
    assert labels[0]["notes"] == "hmm"
