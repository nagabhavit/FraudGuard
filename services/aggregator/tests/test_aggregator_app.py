"""Tests for the application factory's lifecycle management."""

from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi.testclient import TestClient

from aggregator.app import create_app
from aggregator.settings import AggregatorSettings


class _FakeStore:
    def __init__(self) -> None:
        self.closed = False

    async def ping(self) -> None:
        pass

    async def record_transaction(
        self, account_id: str, event_id: str, merchant_id: str, occurred_at: datetime
    ) -> None:
        pass

    async def close(self) -> None:
        self.closed = True


class _FakeAggregator:
    def __init__(self) -> None:
        self.running = False
        self.started = False
        self.stopped = False
        self.run_forever_cancelled = False

    async def start(self) -> None:
        self.started = True
        self.running = True

    async def run_forever(self) -> None:
        # Mirrors the real Aggregator: runs until the lifespan cancels it,
        # not until it returns on its own.
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.run_forever_cancelled = True
            raise

    async def stop(self) -> None:
        self.stopped = True
        self.running = False


def test_lifespan_starts_the_consume_loop_and_cleans_up_on_shutdown() -> None:
    fake_store = _FakeStore()
    fake_aggregator = _FakeAggregator()
    app = create_app(
        AggregatorSettings(_env_file=None), store=fake_store, aggregator=fake_aggregator
    )

    with TestClient(app) as client:
        assert fake_aggregator.started is True
        assert fake_store.closed is False
        client.get("/health/live")

    assert fake_aggregator.run_forever_cancelled is True
    assert fake_aggregator.stopped is True
    assert fake_store.closed is True
