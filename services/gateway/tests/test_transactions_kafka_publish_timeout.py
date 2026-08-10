"""Hermetic test for Milestone 27's Kafka publish timeout bound.

docs/architecture.md documents a real, observed gap: a publish to a
missing Kafka topic was taking 30+ seconds (aiokafka's own metadata-retry
behavior), not a bounded few milliseconds -- silently violating the
hot-path budget even though a publish failure never fails the request
(ADR-0006). Reproducing that exact 30+ second hang against a real broker
would be slow and would require deliberately breaking a topic other
tests share -- inappropriate for this specific fix, which is really
about proving *our* code bounds the wait, not about Kafka's own retry
behavior (which is not our code to test). A fake producer whose
`publish()` sleeps longer than the configured timeout gives a fast,
hermetic, and precise test of exactly that bounding logic, following
this project's own precedent of using a fake only when faking the real
thing convincingly is not the harder path (contrast test_transactions.py
and test_transactions_integration.py's docstrings on this exact
tradeoff).
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

from fastapi import Request

from fraudguard_common.metrics import render_metrics
from fraudguard_db.models import Transaction
from gateway.settings import GatewaySettings
from gateway.transactions import _publish_transaction_received


class _HangingProducer:
    """publish() never resolves on its own within any reasonable test
    timeout -- only asyncio.wait_for's own bound can end it."""

    async def publish(self, *args: object, **kwargs: object) -> None:
        await asyncio.sleep(3600)


def _metric_value(metric_name: str, **labels: str) -> float:
    text = render_metrics()[0].decode()
    label_str = ",".join(f'{key}="{value}"' for key, value in sorted(labels.items()))
    prefix = f"{metric_name}{{{label_str}}} " if labels else f"{metric_name} "
    for line in text.splitlines():
        if line.startswith(prefix):
            return float(line.removeprefix(prefix))
    return 0.0


def _fake_request(timeout_seconds: float) -> Request:
    """A duck-typed stand-in, not a real Starlette Request --
    _publish_transaction_received only ever touches .app.state.events and
    .app.state.settings, so that's all this provides. cast() tells mypy
    to trust the duck typing rather than requiring a full Request.
    """
    settings = GatewaySettings(_env_file=None)
    settings.kafka_publish_timeout_seconds = timeout_seconds
    state = SimpleNamespace(events=_HangingProducer(), settings=settings)
    app = SimpleNamespace(state=state)
    return cast(Request, SimpleNamespace(app=app))


def _transaction() -> Transaction:
    return Transaction(
        id=uuid4(),
        account_id=uuid4(),
        merchant_id="merchant-1",
        amount=Decimal("42.50"),
        currency="USD",
        occurred_at=datetime.now(UTC),
    )


async def test_publish_is_bounded_by_the_configured_timeout() -> None:
    """A hanging publish must not block anywhere close to the 30+ second
    gap this milestone documents fixing -- it must return within a small
    margin of the configured timeout."""
    request = _fake_request(timeout_seconds=0.05)
    started = time.monotonic()
    await _publish_transaction_received(request, _transaction())
    elapsed = time.monotonic() - started
    assert elapsed < 1.0


async def test_publish_timeout_is_recorded_as_a_failure() -> None:
    """A timeout must go through the same failure path as any other
    publish error -- the request still succeeds (ADR-0006), but the
    failure is observable, not silent."""
    before = _metric_value("fraudguard_gateway_kafka_publish_total", outcome="failure")
    request = _fake_request(timeout_seconds=0.05)
    await _publish_transaction_received(request, _transaction())
    after = _metric_value("fraudguard_gateway_kafka_publish_total", outcome="failure")
    assert after == before + 1.0
