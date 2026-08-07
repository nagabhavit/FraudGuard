"""Hermetic tests for the hot-path scoring orchestration (ADR-0009).

`score_transaction` against a fake `ScoringDependency` -- no HTTP, no real
feature-service or model-service. `HttpScoringClient` itself is exercised
against a mocked transport, the same technique
`fraudguard-events`' schema registry client tests use. The real round trip
against live feature-service and model-service containers is covered by
`test_transactions_integration.py`.
"""

from __future__ import annotations

import json
from decimal import Decimal
from uuid import UUID

import httpx2 as httpx
import pytest

from fraudguard_common.errors import UpstreamTimeoutError, UpstreamUnavailableError
from fraudguard_db.models import DecisionOutcome
from gateway.scoring import HttpScoringClient, score_transaction

_ACCOUNT_ID = UUID("d975f45f-e13c-4934-b6bc-ed86130a8f27")


class _FakeScoringClient:
    def __init__(
        self,
        *,
        features: dict[str, int] | None = None,
        features_error: Exception | None = None,
        score_result: dict[str, object] | None = None,
        score_error: Exception | None = None,
    ) -> None:
        self._features = features or {
            "velocity_1m": 1,
            "velocity_1h": 2,
            "velocity_24h": 5,
            "distinct_merchants_24h": 2,
        }
        self._features_error = features_error
        self._score_result = score_result or {
            "outcome": "approve",
            "risk_score": 0.1,
            "model_version": "fraud-lgbm-test",
            "reason_codes": ["amount", "velocity_1h"],
        }
        self._score_error = score_error
        self.score_call: dict[str, object] | None = None

    async def get_features(self, account_id: UUID) -> dict[str, int]:
        if self._features_error is not None:
            raise self._features_error
        return self._features

    async def score(self, **kwargs: object) -> dict[str, object]:
        self.score_call = kwargs
        if self._score_error is not None:
            raise self._score_error
        return self._score_result

    async def aclose(self) -> None:
        pass


async def test_success_maps_the_model_response_onto_a_scored_decision() -> None:
    client = _FakeScoringClient(
        score_result={
            "outcome": "decline",
            "risk_score": 0.93,
            "model_version": "fraud-lgbm-test",
            "reason_codes": ["velocity_24h"],
        }
    )
    scored = await score_transaction(
        client,
        account_id=_ACCOUNT_ID,
        amount=Decimal("42.50"),
        fallback_threshold=Decimal("500.00"),
    )
    assert scored.outcome == DecisionOutcome.DECLINE
    assert scored.risk_score == 0.93
    assert scored.model_version == "fraud-lgbm-test"
    assert scored.reason_codes == ["velocity_24h"]
    assert scored.latency_ms >= 0.0


async def test_success_forwards_the_transaction_amount_and_looked_up_features() -> None:
    client = _FakeScoringClient(
        features={
            "velocity_1m": 3,
            "velocity_1h": 7,
            "velocity_24h": 20,
            "distinct_merchants_24h": 4,
        }
    )
    await score_transaction(
        client,
        account_id=_ACCOUNT_ID,
        amount=Decimal("99.00"),
        fallback_threshold=Decimal("500.00"),
    )
    assert client.score_call == {
        "amount": Decimal("99.00"),
        "velocity_1m": 3,
        "velocity_1h": 7,
        "velocity_24h": 20,
        "distinct_merchants_24h": 4,
    }


@pytest.mark.parametrize(
    ("amount", "expected_outcome"),
    [
        (Decimal("501.00"), DecisionOutcome.REVIEW),
        (Decimal("500.00"), DecisionOutcome.APPROVE),
        (Decimal("10.00"), DecisionOutcome.APPROVE),
    ],
)
async def test_feature_service_failure_falls_back_on_amount(
    amount: Decimal, expected_outcome: DecisionOutcome
) -> None:
    client = _FakeScoringClient(
        features_error=UpstreamUnavailableError("connection refused")
    )
    scored = await score_transaction(
        client,
        account_id=_ACCOUNT_ID,
        amount=amount,
        fallback_threshold=Decimal("500.00"),
    )
    assert scored.outcome == expected_outcome
    assert scored.model_version is None
    assert scored.reason_codes is None


async def test_model_service_timeout_falls_back() -> None:
    client = _FakeScoringClient(
        score_error=UpstreamTimeoutError("model-service too slow")
    )
    scored = await score_transaction(
        client,
        account_id=_ACCOUNT_ID,
        amount=Decimal("10.00"),
        fallback_threshold=Decimal("500.00"),
    )
    assert scored.outcome == DecisionOutcome.APPROVE
    assert scored.model_version is None


async def test_model_service_error_response_falls_back() -> None:
    client = _FakeScoringClient(
        score_error=UpstreamUnavailableError("model-service returned 500")
    )
    scored = await score_transaction(
        client,
        account_id=_ACCOUNT_ID,
        amount=Decimal("501.00"),
        fallback_threshold=Decimal("500.00"),
    )
    assert scored.outcome == DecisionOutcome.REVIEW
    assert scored.model_version is None


async def test_malformed_model_response_falls_back() -> None:
    # A reachable model-service that answers with a shape score_transaction
    # did not ask for is the same "cannot trust this answer" case as
    # unreachable -- it must not raise out of the hot path.
    client = _FakeScoringClient(score_result={"outcome": "approve"})
    scored = await score_transaction(
        client,
        account_id=_ACCOUNT_ID,
        amount=Decimal("10.00"),
        fallback_threshold=Decimal("500.00"),
    )
    assert scored.outcome == DecisionOutcome.APPROVE
    assert scored.model_version is None


def _http_client_with_transports(
    *, feature_handler: httpx.MockTransport, model_handler: httpx.MockTransport
) -> HttpScoringClient:
    client = HttpScoringClient(
        feature_service_url="http://feature-service.invalid",
        model_service_url="http://model-service.invalid",
        timeout_seconds=1.0,
    )
    client._feature_client = httpx.AsyncClient(
        base_url="http://feature-service.invalid", transport=feature_handler
    )
    client._model_client = httpx.AsyncClient(
        base_url="http://model-service.invalid", transport=model_handler
    )
    return client


async def test_http_scoring_client_get_features_parses_the_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == f"/v1/features/{_ACCOUNT_ID}"
        return httpx.Response(
            200,
            json={
                "account_id": str(_ACCOUNT_ID),
                "computed_at": "2026-08-07T12:00:00Z",
                "velocity_1m": 1,
                "velocity_1h": 2,
                "velocity_24h": 3,
                "distinct_merchants_24h": 4,
            },
        )

    client = _http_client_with_transports(
        feature_handler=httpx.MockTransport(handler),
        model_handler=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
    )
    features = await client.get_features(_ACCOUNT_ID)
    assert features == {
        "velocity_1m": 1,
        "velocity_1h": 2,
        "velocity_24h": 3,
        "distinct_merchants_24h": 4,
    }


async def test_http_scoring_client_get_features_raises_on_server_error() -> None:
    client = _http_client_with_transports(
        feature_handler=httpx.MockTransport(lambda r: httpx.Response(503)),
        model_handler=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
    )
    with pytest.raises(UpstreamUnavailableError, match="503"):
        await client.get_features(_ACCOUNT_ID)


async def test_http_scoring_client_get_features_raises_timeout_on_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("feature-service too slow")

    client = _http_client_with_transports(
        feature_handler=httpx.MockTransport(handler),
        model_handler=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
    )
    with pytest.raises(UpstreamTimeoutError, match="feature-service"):
        await client.get_features(_ACCOUNT_ID)


async def test_http_scoring_client_get_features_raises_unavailable_on_connect() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = _http_client_with_transports(
        feature_handler=httpx.MockTransport(handler),
        model_handler=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
    )
    with pytest.raises(UpstreamUnavailableError, match="feature-service"):
        await client.get_features(_ACCOUNT_ID)


async def test_http_scoring_client_score_sends_the_feature_row_and_amount() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "outcome": "review",
                "risk_score": 0.5,
                "model_version": "fraud-lgbm-test",
                "reason_codes": ["amount"],
            },
        )

    client = _http_client_with_transports(
        feature_handler=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
        model_handler=httpx.MockTransport(handler),
    )
    result = await client.score(
        amount=Decimal("10.00"),
        velocity_1m=1,
        velocity_1h=2,
        velocity_24h=3,
        distinct_merchants_24h=4,
    )
    assert captured == {
        "amount": "10.00",
        "velocity_1m": 1,
        "velocity_1h": 2,
        "velocity_24h": 3,
        "distinct_merchants_24h": 4,
    }
    assert result == {
        "outcome": "review",
        "risk_score": 0.5,
        "model_version": "fraud-lgbm-test",
        "reason_codes": ["amount"],
    }


async def test_http_scoring_client_score_raises_on_server_error() -> None:
    client = _http_client_with_transports(
        feature_handler=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
        model_handler=httpx.MockTransport(lambda r: httpx.Response(500)),
    )
    with pytest.raises(UpstreamUnavailableError, match="500"):
        await client.score(
            amount=Decimal("10.00"),
            velocity_1m=1,
            velocity_1h=2,
            velocity_24h=3,
            distinct_merchants_24h=4,
        )


async def test_http_scoring_client_aclose_closes_both_clients() -> None:
    client = _http_client_with_transports(
        feature_handler=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
        model_handler=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
    )
    await client.aclose()
    assert client._feature_client.is_closed
    assert client._model_client.is_closed
