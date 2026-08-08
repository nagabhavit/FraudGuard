"""Sustained, concurrent load generation against a running gateway.
See ADR-0015.

Separate from `driver.py`'s sequential `run()` by design -- that
function's own docstring says concurrency is a different tool's job, not
its own. This module is that different tool: `concurrency` many
`asyncio.Semaphore`-gated workers send `TransactionFactory`-generated
transactions (reusing `driver.send_transaction`) for a fixed wall-clock
duration, and the latency of every request -- success or failure -- is
recorded to report p50/p95/p99 at the end.

These percentiles are client-observed HTTP latency: factory-to-response,
including network and JSON serialization -- not
`fraudguard_gateway_scoring_duration_seconds` (ADR-0010's histogram of
the gateway's own feature-service+model-service scoring time alone). The
two measure different things and are not expected to match.

Usage:
    uv run --package fraudguard-simulator python -m simulator.load
    uv run --package fraudguard-simulator python -m simulator.load \\
        --duration-seconds 30 --concurrency 10
"""

from __future__ import annotations

import argparse
import asyncio
import time
from dataclasses import dataclass, field

import httpx2 as httpx

from simulator.driver import send_transaction
from simulator.factory import TransactionFactory

_DEFAULT_BASE_URL = "http://localhost:8000"
_DEFAULT_DURATION_SECONDS = 30.0
_DEFAULT_CONCURRENCY = 10
_DEFAULT_ACCOUNT_POOL_SIZE = 40

#: Not a target, not a claim of "the" official load level -- only a
#: convenience default so the tool is runnable with no flags, the same
#: role `simulator/__main__.py`'s `_DEFAULT_COUNT` plays there (ADR-0015's
#: Acceptance criteria: no traffic rate or concurrency level is asserted
#: as authoritative by this milestone).


@dataclass
class LoadRunSummary:
    """A running tally of one load run, plus the latency distribution
    needed to report p50/p95/p99.

    `driver.RunSummary` has no notion of per-request timing -- the
    sequential tool it belongs to has no concurrency to characterize the
    latency of *under*. This is a sibling type, not a subclass, because
    the two tools answer different questions (structural correctness vs.
    latency under load) and gain nothing from sharing a hierarchy.
    """

    sent: int = 0
    succeeded: int = 0
    failed: int = 0
    latencies_seconds: list[float] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def record_success(self, latency_seconds: float) -> None:
        self.sent += 1
        self.succeeded += 1
        self.latencies_seconds.append(latency_seconds)

    def record_failure(self, latency_seconds: float, error: str) -> None:
        self.sent += 1
        self.failed += 1
        self.latencies_seconds.append(latency_seconds)
        self.errors.append(error)

    def percentiles(self) -> dict[str, float]:
        """p50/p95/p99 over every request's latency, successes and
        failures alike -- a slow failure is still a latency observation.
        Zeros if nothing was sent.
        """
        if not self.latencies_seconds:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0}
        ordered = sorted(self.latencies_seconds)
        return {
            "p50": _nearest_rank_percentile(ordered, 0.50),
            "p95": _nearest_rank_percentile(ordered, 0.95),
            "p99": _nearest_rank_percentile(ordered, 0.99),
        }


def _nearest_rank_percentile(ordered: list[float], fraction: float) -> float:
    """Nearest-rank percentile over an already-sorted, non-empty list.

    Deliberately simple (no interpolation): this is a diagnostic tool
    reporting real observed latencies, not a statistics library -- the
    nearest actually-observed value is easier to reason about than an
    interpolated one no request actually took.
    """
    index = min(len(ordered) - 1, round(fraction * (len(ordered) - 1)))
    return ordered[index]


async def _worker(
    client: httpx.AsyncClient,
    factory: TransactionFactory,
    summary: LoadRunSummary,
    semaphore: asyncio.Semaphore,
    deadline: float,
) -> None:
    while time.monotonic() < deadline:
        async with semaphore:
            payload = factory.random_transaction()
            started_at = time.monotonic()
            try:
                await send_transaction(client, payload)
            except httpx.HTTPError as exc:
                summary.record_failure(time.monotonic() - started_at, str(exc))
            else:
                summary.record_success(time.monotonic() - started_at)


async def run(
    factory: TransactionFactory,
    *,
    base_url: str = "",
    duration_seconds: float,
    concurrency: int,
    timeout_seconds: float = 5.0,
    client: httpx.AsyncClient | None = None,
) -> LoadRunSummary:
    """Send transactions from `concurrency` concurrent workers for
    `duration_seconds`, gated by an `asyncio.Semaphore` sized to
    `concurrency` (ADR-0015) -- bounding how many requests are ever
    in flight at once, independent of how many workers are looping.

    `client` is injectable, the same structural-dependency-injection
    pattern `driver.run()` already uses, so tests can pass a client wired
    to a mocked transport instead of this always building its own.
    """
    summary = LoadRunSummary()
    owns_client = client is None
    active_client = client or httpx.AsyncClient(
        base_url=base_url, timeout=timeout_seconds
    )
    semaphore = asyncio.Semaphore(concurrency)
    deadline = time.monotonic() + duration_seconds
    try:
        workers = [
            asyncio.create_task(
                _worker(active_client, factory, summary, semaphore, deadline)
            )
            for _ in range(concurrency)
        ]
        await asyncio.gather(*workers)
    finally:
        if owns_client:
            await active_client.aclose()
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=_DEFAULT_BASE_URL)
    parser.add_argument(
        "--duration-seconds", type=float, default=_DEFAULT_DURATION_SECONDS
    )
    parser.add_argument("--concurrency", type=int, default=_DEFAULT_CONCURRENCY)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--account-pool-size", type=int, default=_DEFAULT_ACCOUNT_POOL_SIZE
    )
    return parser.parse_args()


def _print_summary(summary: LoadRunSummary) -> None:
    percentiles = summary.percentiles()
    print(
        f"sent {summary.sent}: {summary.succeeded} succeeded, {summary.failed} failed"
    )
    print(
        "  latency (client-observed, seconds): "
        f"p50={percentiles['p50']:.3f} p95={percentiles['p95']:.3f} "
        f"p99={percentiles['p99']:.3f}"
    )
    for error in summary.errors[:5]:
        print(f"  error: {error}")


def main() -> None:
    args = _parse_args()
    factory = TransactionFactory(
        seed=args.seed, account_pool_size=args.account_pool_size
    )
    summary = asyncio.run(
        run(
            factory,
            base_url=args.base_url,
            duration_seconds=args.duration_seconds,
            concurrency=args.concurrency,
        )
    )
    _print_summary(summary)


if __name__ == "__main__":
    main()
