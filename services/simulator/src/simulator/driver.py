"""Sends `TransactionFactory`-generated transactions to a running gateway.
See ADR-0011.

Separate from `factory.py` deliberately: the factory knows how to generate
one realistic transaction; this module knows how to send things and how
many. Milestone 12+'s load-testing work can import `send_transaction`
directly and drive it with a different, throughput-oriented driver without
touching the factory at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx2 as httpx

from simulator.factory import TransactionFactory, TransactionPayload


@dataclass
class RunSummary:
    """A running tally of one `run()` call -- not a statistics engine, just
    enough to report what happened and let a caller (a human at a terminal,
    or an end-to-end test's assertions) decide if it looks right.
    """

    sent: int = 0
    succeeded: int = 0
    failed: int = 0
    outcomes: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def record_success(self, outcome: str) -> None:
        self.sent += 1
        self.succeeded += 1
        self.outcomes[outcome] = self.outcomes.get(outcome, 0) + 1

    def record_failure(self, error: str) -> None:
        self.sent += 1
        self.failed += 1
        self.errors.append(error)


async def send_transaction(
    client: httpx.AsyncClient, payload: TransactionPayload
) -> dict[str, Any]:
    """POST one transaction, raising on a non-2xx response.

    Deliberately does not decide what to do with a failure -- `run()` below
    logs and continues (a generator producing traffic should not stop
    because one request failed), while an end-to-end test calling this
    directly can let the exception fail the test instead.
    """
    response = await client.post("/v1/transactions", json=payload)
    response.raise_for_status()
    result: dict[str, Any] = response.json()
    return result


async def run(
    factory: TransactionFactory,
    *,
    base_url: str = "",
    count: int,
    timeout_seconds: float = 5.0,
    client: httpx.AsyncClient | None = None,
) -> RunSummary:
    """Send `count` realistic transactions, one at a time.

    Sequential, not concurrent: a simulator proving the hot path behaves
    correctly has no reason to race it, and sequential sends keep this run's
    own timing simple to reason about. Concurrency is exactly the dimension
    Milestone 12+'s load-testing work would add on top of `send_transaction`
    -- not this function's job.

    `client` is injectable -- structural dependency injection, the same
    pattern `gateway.scoring.HttpScoringClient` uses -- so tests can pass a
    client wired to a mocked transport instead of `run()` always building
    its own. When omitted, a real client is built from `base_url` and owned
    (opened and closed) by this call; when provided, the caller owns its
    lifecycle and `base_url`/`timeout_seconds` are ignored.
    """
    summary = RunSummary()
    owns_client = client is None
    active_client = client or httpx.AsyncClient(
        base_url=base_url, timeout=timeout_seconds
    )
    try:
        for _ in range(count):
            payload = factory.random_transaction()
            try:
                result = await send_transaction(active_client, payload)
            except httpx.HTTPError as exc:
                summary.record_failure(str(exc))
            else:
                summary.record_success(str(result["outcome"]))
    finally:
        if owns_client:
            await active_client.aclose()
    return summary
