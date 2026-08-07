"""Minimal async Confluent Schema Registry client.

Only the two operations FraudGuard needs: register a schema under a
subject, and fetch a schema by its registry-assigned ID. Not a general
Schema Registry SDK -- see ADR-0006 for why this is hand-written instead of
using confluent-kafka's client.
"""

from __future__ import annotations

import asyncio
from types import TracebackType

import httpx2 as httpx

_SCHEMA_REGISTRY_CONTENT_TYPE = "application/vnd.schemaregistry.v1+json"

# The registry's healthcheck (GET /subjects, used in docker-compose.yml) can
# pass before it has finished becoming the write leader for its internal
# _schemas topic -- observed taking over 30s on a cold compose stack. A
# short client timeout combined with no retry turns that into a gateway
# startup crash for a condition that resolves itself within a minute, so
# writes get a generous read timeout and a bounded retry with backoff.
_WRITE_TIMEOUT = httpx.Timeout(connect=5.0, read=20.0, write=5.0, pool=5.0)
_MAX_WRITE_ATTEMPTS = 4
_INITIAL_BACKOFF_SECONDS = 2.0


class SchemaRegistryError(RuntimeError):
    """The registry rejected a request -- e.g. a BACKWARD-incompatible schema."""


class SchemaRegistryClient:
    def __init__(self, base_url: str) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=5.0)

    async def register(self, subject: str, schema_json: str) -> int:
        """Register a schema under `subject`, returning its registry ID.

        Idempotent: the registry returns the existing ID for byte-identical
        schema content instead of creating a new version.
        """
        backoff = _INITIAL_BACKOFF_SECONDS
        last_error: Exception = RuntimeError("unreachable")  # replaced on first attempt

        for attempt in range(1, _MAX_WRITE_ATTEMPTS + 1):
            try:
                response = await self._client.post(
                    f"/subjects/{subject}/versions",
                    headers={"Content-Type": _SCHEMA_REGISTRY_CONTENT_TYPE},
                    json={"schema": schema_json},
                    timeout=_WRITE_TIMEOUT,
                )
                if response.status_code < httpx.codes.BAD_REQUEST:
                    schema_id: int = response.json()["id"]
                    return schema_id
                error = SchemaRegistryError(
                    f"failed to register schema for subject {subject!r}: "
                    f"{response.status_code} {response.text}"
                )
                if response.status_code < httpx.codes.INTERNAL_SERVER_ERROR:
                    # 4xx: the registry answered definitively -- e.g. a
                    # BACKWARD-incompatible schema (409). Retrying would
                    # only reproduce the same rejection.
                    raise error
                last_error = error
            except httpx.TimeoutException as exc:
                last_error = exc

            if attempt < _MAX_WRITE_ATTEMPTS:
                await asyncio.sleep(backoff)
                backoff *= 2

        raise SchemaRegistryError(
            f"failed to register schema for subject {subject!r} after "
            f"{_MAX_WRITE_ATTEMPTS} attempts"
        ) from last_error

    async def get_schema(self, schema_id: int) -> str:
        """Fetch the raw Avro schema JSON registered under `schema_id`."""
        response = await self._client.get(f"/schemas/ids/{schema_id}")
        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise SchemaRegistryError(
                f"failed to fetch schema {schema_id}: "
                f"{response.status_code} {response.text}"
            )
        schema: str = response.json()["schema"]
        return schema

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> SchemaRegistryClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()
