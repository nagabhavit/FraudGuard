"""Hermetic tests for the load driver -- a mocked HTTP transport, no real
gateway, and no real timing dependency for the percentile math (ADR-0015's
Acceptance criteria: percentile correctness is unit-testable with a
synthetic latency list, requiring no live stack). The real round trip
against a live containerized gateway is a manual, documented procedure,
not an automated test -- see ADR-0015.
"""

from __future__ import annotations

import httpx2 as httpx
import pytest

from simulator.driver import send_transaction
from simulator.factory import TransactionFactory
from simulator.load import LoadRunSummary, run


def _client_with_transport(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url="http://gateway.invalid", transport=handler)


def _decision_response(model_version: str | None = "fraud-lgbm-test") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "transaction_id": "d975f45f-e13c-4934-b6bc-ed86130a8f27",
            "outcome": "approve",
            "risk_score": 0.1,
            "model_version": model_version,
            "reason_codes": ["amount"] if model_version else None,
        },
    )


def test_load_run_summary_record_success_and_failure() -> None:
    summary = LoadRunSummary()
    summary.record_success(0.01)
    summary.record_success(0.02)
    summary.record_failure(0.03, "boom")

    assert summary.sent == 3
    assert summary.succeeded == 2
    assert summary.failed == 1
    assert summary.latencies_seconds == [0.01, 0.02, 0.03]
    assert summary.errors == ["boom"]


def test_percentiles_are_zero_when_nothing_was_sent() -> None:
    summary = LoadRunSummary()
    assert summary.percentiles() == {"p50": 0.0, "p95": 0.0, "p99": 0.0}


def test_percentiles_match_a_hand_computed_nearest_rank_reference() -> None:
    """21 latencies (1.0 through 21.0 seconds), inserted out of order to
    prove `percentiles()` sorts before computing. Nearest-rank nearest
    integer indices land on whole numbers with no rounding ambiguity:
    p50 -> index 10 (value 11.0), p95 -> index 19 (value 20.0),
    p99 -> index 20, the max (value 21.0).
    """
    summary = LoadRunSummary()
    shuffled = [13.0, 1.0, 21.0, 7.0, 19.0, 4.0, 11.0, 2.0, 20.0]
    remaining = sorted(set(range(1, 22)) - {int(v) for v in shuffled})
    for value in shuffled + [float(v) for v in remaining]:
        summary.record_success(value)

    assert summary.sent == 21
    assert summary.percentiles() == {"p50": 11.0, "p95": 20.0, "p99": 21.0}


async def test_run_sends_multiple_requests_within_the_duration() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.path == "/v1/transactions"
        return _decision_response()

    factory = TransactionFactory(seed=0)
    async with _client_with_transport(httpx.MockTransport(handler)) as client:
        summary = await run(factory, duration_seconds=0.2, concurrency=3, client=client)

    assert summary.sent > 1
    assert summary.sent == summary.succeeded + summary.failed
    assert summary.succeeded == calls
    assert all(latency >= 0.0 for latency in summary.latencies_seconds)


async def test_run_records_failures_without_stopping_the_run() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    factory = TransactionFactory(seed=0)
    async with _client_with_transport(httpx.MockTransport(handler)) as client:
        summary = await run(factory, duration_seconds=0.1, concurrency=2, client=client)

    assert summary.sent > 0
    assert summary.failed == summary.sent
    assert summary.succeeded == 0
    assert len(summary.errors) == summary.sent


async def test_run_builds_and_closes_its_own_client_when_none_is_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same reasoning as `driver.run()`'s equivalent test: a real
    unreachable host is deliberately not used to trigger this path, since
    connecting to a closed port does not reliably fail fast on Windows.
    """
    close_calls = 0
    real_client_cls = httpx.AsyncClient
    real_aclose = real_client_cls.aclose

    def handler(request: httpx.Request) -> httpx.Response:
        return _decision_response()

    def fake_client(**kwargs: object) -> httpx.AsyncClient:
        return real_client_cls(
            base_url="http://gateway.invalid", transport=httpx.MockTransport(handler)
        )

    async def tracking_aclose(self: httpx.AsyncClient) -> None:
        nonlocal close_calls
        close_calls += 1
        await real_aclose(self)

    monkeypatch.setattr("simulator.load.httpx.AsyncClient", fake_client)
    monkeypatch.setattr(real_client_cls, "aclose", tracking_aclose)

    factory = TransactionFactory(seed=0)
    summary = await run(
        factory, base_url="http://gateway.invalid", duration_seconds=0.1, concurrency=2
    )

    assert summary.sent > 0
    assert close_calls == 1


async def test_send_transaction_is_reused_unchanged_from_driver() -> None:
    """ADR-0015: the load driver reuses `driver.send_transaction`, not a
    second implementation of posting one transaction.
    """
    factory = TransactionFactory(seed=0)
    payload = factory.random_transaction()

    async def handler(request: httpx.Request) -> httpx.Response:
        return _decision_response()

    async with _client_with_transport(httpx.MockTransport(handler)) as client:
        result = await send_transaction(client, payload)

    assert result["model_version"] == "fraud-lgbm-test"
