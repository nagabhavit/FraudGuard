"""Unit tests for the Schema Registry client's retry behaviour -- a mocked
transport, not a real registry. The real round trip (including a cold-start
registry that is briefly slow to accept writes) is exercised by
`test_transactions_integration.py` against the live stack.
"""

from __future__ import annotations

import json

import httpx2 as httpx
import pytest

from fraudguard_events.schema_registry import SchemaRegistryClient, SchemaRegistryError


@pytest.fixture(autouse=True)
def _no_real_sleeping(monkeypatch: pytest.MonkeyPatch) -> None:
    # The retry loop's backoff is real time by design (production); a unit
    # test asserting the retry logic itself should not also spend 14+
    # wall-clock seconds proving it.
    async def _instant_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(
        "fraudguard_events.schema_registry.asyncio.sleep", _instant_sleep
    )


def _client_with_transport(handler: httpx.MockTransport) -> SchemaRegistryClient:
    client = SchemaRegistryClient(base_url="http://schema-registry.invalid")
    client._client = httpx.AsyncClient(
        base_url="http://schema-registry.invalid", transport=handler
    )
    return client


async def test_register_succeeds_on_the_first_attempt() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"id": 7})

    client = _client_with_transport(httpx.MockTransport(handler))
    schema_id = await client.register("subject-1", json.dumps({"type": "string"}))

    assert schema_id == 7
    assert calls == 1


async def test_register_retries_after_a_timeout_then_succeeds() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise httpx.ReadTimeout("registry not yet leader for _schemas")
        return httpx.Response(200, json={"id": 9})

    client = _client_with_transport(httpx.MockTransport(handler))
    schema_id = await client.register("subject-1", json.dumps({"type": "string"}))

    assert schema_id == 9
    assert calls == 3


async def test_register_gives_up_after_the_maximum_attempts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("registry never becomes ready")

    client = _client_with_transport(httpx.MockTransport(handler))

    with pytest.raises(SchemaRegistryError, match="after 4 attempts"):
        await client.register("subject-1", json.dumps({"type": "string"}))


async def test_register_does_not_retry_on_a_rejected_schema() -> None:
    # A 409 (incompatible schema) is a real answer, not a transient
    # failure -- retrying it would just reproduce the same rejection.
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(409, json={"error_code": 409, "message": "incompatible"})

    client = _client_with_transport(httpx.MockTransport(handler))

    with pytest.raises(SchemaRegistryError, match="409"):
        await client.register("subject-1", json.dumps({"type": "string"}))

    assert calls == 1


async def test_register_retries_on_a_server_error() -> None:
    # A 5xx (e.g. "leader not known" while the registry is still becoming
    # writer for its internal _schemas topic) is worth retrying, unlike a
    # 4xx application-level rejection.
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls < 2:
            return httpx.Response(
                500, json={"error_code": 50003, "message": "not ready"}
            )
        return httpx.Response(200, json={"id": 3})

    client = _client_with_transport(httpx.MockTransport(handler))
    schema_id = await client.register("subject-1", json.dumps({"type": "string"}))

    assert schema_id == 3
    assert calls == 2
