"""Hermetic tests for the driver -- a mocked HTTP transport, no real gateway.
The real round trip against a live containerized gateway is covered by
test_end_to_end_integration.py.
"""

from __future__ import annotations

import httpx2 as httpx
import pytest

from simulator.driver import RunSummary, run, send_transaction
from simulator.factory import TransactionFactory


def _client_with_transport(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url="http://gateway.invalid", transport=handler)


def _decision_response(outcome: str = "approve") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "transaction_id": "d975f45f-e13c-4934-b6bc-ed86130a8f27",
            "outcome": outcome,
            "risk_score": 0.1,
            "model_version": "fraud-lgbm-test",
            "reason_codes": ["amount"],
        },
    )


async def test_send_transaction_posts_to_v1_transactions_and_returns_the_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/transactions"
        return _decision_response("approve")

    factory = TransactionFactory(seed=0)
    payload = factory.random_transaction()
    async with _client_with_transport(httpx.MockTransport(handler)) as client:
        result = await send_transaction(client, payload)

    assert result["outcome"] == "approve"
    assert result["model_version"] == "fraud-lgbm-test"


async def test_send_transaction_raises_on_a_server_error() -> None:
    factory = TransactionFactory(seed=0)
    payload = factory.random_transaction()

    async with _client_with_transport(
        httpx.MockTransport(lambda r: httpx.Response(500))
    ) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await send_transaction(client, payload)


async def test_run_sends_the_requested_count_and_tallies_outcomes() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _decision_response("decline" if calls == 3 else "approve")

    factory = TransactionFactory(seed=0)
    async with _client_with_transport(httpx.MockTransport(handler)) as client:
        summary = await run(factory, count=5, client=client)

    assert summary.sent == 5
    assert summary.succeeded == 5
    assert summary.failed == 0
    assert summary.outcomes == {"approve": 4, "decline": 1}
    assert calls == 5


async def test_run_records_a_failure_and_continues() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 2:
            return httpx.Response(500)
        return _decision_response("approve")

    factory = TransactionFactory(seed=0)
    async with _client_with_transport(httpx.MockTransport(handler)) as client:
        summary = await run(factory, count=3, client=client)

    assert summary.sent == 3
    assert summary.succeeded == 2
    assert summary.failed == 1
    assert len(summary.errors) == 1
    assert calls == 3


async def test_run_builds_and_closes_its_own_client_when_none_is_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When `client` is omitted, `run()` must build one and close it when
    done -- verified with no real network at all: `httpx.AsyncClient` is
    monkeypatched (at the reference `simulator.driver` holds) to ignore the
    `base_url`/`timeout` kwargs `run()` passes and use a mocked transport
    instead, and `aclose` is wrapped to count calls. A real unreachable
    host is deliberately not used here to trigger this path -- on Windows,
    connecting to a closed port does not reliably fail fast, which has
    already caused a real multi-hour test hang elsewhere in this project.
    """
    close_calls = 0
    real_client_cls = httpx.AsyncClient
    real_aclose = real_client_cls.aclose

    def handler(request: httpx.Request) -> httpx.Response:
        return _decision_response("approve")

    def fake_client(**kwargs: object) -> httpx.AsyncClient:
        return real_client_cls(
            base_url="http://gateway.invalid", transport=httpx.MockTransport(handler)
        )

    async def tracking_aclose(self: httpx.AsyncClient) -> None:
        nonlocal close_calls
        close_calls += 1
        await real_aclose(self)

    monkeypatch.setattr("simulator.driver.httpx.AsyncClient", fake_client)
    monkeypatch.setattr(real_client_cls, "aclose", tracking_aclose)

    factory = TransactionFactory(seed=0)
    summary = await run(factory, base_url="http://gateway.invalid", count=2)

    assert summary.sent == 2
    assert summary.succeeded == 2
    assert close_calls == 1


def test_run_summary_record_success_and_failure() -> None:
    summary = RunSummary()
    summary.record_success("approve")
    summary.record_success("approve")
    summary.record_success("decline")
    summary.record_failure("boom")

    assert summary.sent == 4
    assert summary.succeeded == 3
    assert summary.failed == 1
    assert summary.outcomes == {"approve": 2, "decline": 1}
    assert summary.errors == ["boom"]
