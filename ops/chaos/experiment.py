"""Chaos experiments for the degradation ladder and aggregator recovery.
See ADR-0015.

One parameterized script, not one per target: `docker compose stop
<target>` -> send traffic via the simulator -> assert the target's
documented signal shows the outage -> `docker compose start <target>` ->
poll until the signal recovers. Self-verifying: a failed assertion is an
uncaught `ChaosExperimentError`, which exits non-zero -- no human has to
read output and judge it.

Two signal families, per ADR-0015's explicit approval -- not
interchangeable, and never silently substituted for each other:

- model-service / feature-service: the gateway's own response to
  `POST /v1/transactions`, confirmed via `GET /v1/transactions`
  (`model_version` null during the outage -- the existing ADR-0005/
  ADR-0009 fallback signal, populated again on recovery).
- kafka: originally intended to be the aggregator's `GET /health/ready`,
  `checks.kafka_consumer`, the same shape of signal as the other two
  targets. Verified against the real stack and found not to work --
  `aiokafka` retries a lost broker connection internally, so the
  consumer's `running` flag (and therefore this check) never leaves
  `"ok"` during a live outage. See ADR-0015's "Verification findings"
  for the full account. This script still checks and prints
  `checks.kafka_consumer` on every run -- the limitation is verified and
  recorded each time, not silently dropped once it stopped being useful
  as a pass/fail signal -- but the actual outage/recovery signal is the
  gateway's own `fraudguard_gateway_kafka_publish_total{outcome}`
  (ADR-0013, a pre-existing metric), confirmed by direct measurement to
  increment `outcome="failure"` during the outage and `outcome="success"`
  again on recovery.

Runs against the local docker-compose stack from the host, the same
posture as `ops/scripts/create_kafka_topics.py` and `services/simulator`
(ADR-0011) -- not wired into CI (ADR-0015): Alertmanager's own `for:`
windows alone would consume minutes per experiment against a budget the
`integration` job does not have to spare.

Usage:
    uv run --all-packages python ops/chaos/experiment.py --target model-service
    uv run --all-packages python ops/chaos/experiment.py --target feature-service
    uv run --all-packages python ops/chaos/experiment.py --target kafka
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
import time
from collections.abc import Awaitable, Callable
from typing import Literal

import httpx2 as httpx

from simulator.driver import send_transaction
from simulator.factory import TransactionFactory

Target = Literal["model-service", "feature-service", "kafka"]

_TARGETS: tuple[Target, ...] = ("model-service", "feature-service", "kafka")

_DEFAULT_GATEWAY_URL = "http://localhost:8000"
_DEFAULT_AGGREGATOR_URL = "http://localhost:8002"
_REQUEST_TIMEOUT_SECONDS = 10.0

#: A live Kafka outage delays POST /v1/transactions by tens of seconds --
#: measured at 43.1s in the real-stack run that produced ADR-0015's
#: "Verification findings" -- the gateway's own best-effort publish
#: attempt blocking the response before it returns
#: (docs/architecture.md's Kafka topics "Known gap"). The other two
#: targets' fallback path is bounded by GatewaySettings.scoring_timeout_seconds
#: (2s, ADR-0009) and need no such allowance.
_KAFKA_REQUEST_TIMEOUT_SECONDS = 90.0

#: The script's own bail-out bound so a genuinely broken recovery doesn't
#: hang the terminal forever -- not a documented recovery-time SLA this
#: project claims (ADR-0015's Acceptance criteria).
_POLL_TIMEOUT_SECONDS = 60.0
_POLL_INTERVAL_SECONDS = 1.0


class ChaosExperimentError(AssertionError):
    """A target's documented signal did not show what it should.

    A distinct type, not a bare `AssertionError`, so a failure here reads
    as "the system did not behave the way its own ADRs say it does," not
    an ordinary test typo.
    """


def _docker_compose(*args: str) -> None:
    # S603/S607: no untrusted input reaches this -- `args` is always one of
    # this module's own hardcoded "stop"/"start" literals plus `target`,
    # which argparse already constrains to `_TARGETS` before it gets here.
    subprocess.run(["docker", "compose", *args], check=True)  # noqa: S603, S607


async def _post_transaction(
    client: httpx.AsyncClient, factory: TransactionFactory
) -> dict[str, object]:
    payload = factory.random_transaction()
    return await send_transaction(client, payload)


async def _model_version_via_feed(
    client: httpx.AsyncClient, transaction_id: str
) -> str | None:
    """The same signal `GET /v1/transactions` already exposes (ADR-0012):
    confirms the persisted `Decision`, not just the synchronous response
    -- both are written before the response returns
    (`gateway/transactions.py`'s `create_transaction`), so this is a real
    second confirmation, not a race against it.
    """
    response = await client.get("/v1/transactions", params={"limit": 200})
    response.raise_for_status()
    items = response.json()["items"]
    matching = [item for item in items if item["transaction_id"] == transaction_id]
    if not matching:
        raise ChaosExperimentError(
            f"transaction {transaction_id} not found in GET /v1/transactions"
        )
    decision = matching[0]["decision"]
    if decision is None:
        raise ChaosExperimentError(
            f"transaction {transaction_id} has no decision in GET /v1/transactions"
        )
    model_version = decision["model_version"]
    return None if model_version is None else str(model_version)


async def _assert_model_scored(
    client: httpx.AsyncClient, factory: TransactionFactory, *, label: str
) -> None:
    result = await _post_transaction(client, factory)
    if result.get("model_version") is None:
        raise ChaosExperimentError(
            f"{label}: expected the real model to score this transaction "
            "(model_version populated), got model_version=None in the "
            "synchronous response"
        )
    transaction_id = str(result["transaction_id"])
    model_version = await _model_version_via_feed(client, transaction_id)
    if model_version is None:
        raise ChaosExperimentError(
            f"{label}: GET /v1/transactions disagrees with the synchronous "
            "response -- expected model_version populated, got None"
        )
    print(f"  ok: {label} -- model_version={model_version}")


async def _assert_fallback_engaged(
    client: httpx.AsyncClient, factory: TransactionFactory, *, label: str
) -> None:
    """`send_transaction` already raises on a non-2xx (ADR-0009: the
    gateway must still return 200 under an outage), so simply not raising
    here is itself part of the "still returns 200, never hangs" signal.
    """
    result = await _post_transaction(client, factory)
    if result.get("model_version") is not None:
        raise ChaosExperimentError(
            f"{label}: expected the fallback rule (model_version=None) "
            f"while the target is stopped, got "
            f"model_version={result['model_version']!r}"
        )
    transaction_id = str(result["transaction_id"])
    model_version = await _model_version_via_feed(client, transaction_id)
    if model_version is not None:
        raise ChaosExperimentError(
            f"{label}: GET /v1/transactions disagrees with the synchronous "
            f"response -- expected model_version=None, got {model_version!r}"
        )
    print(
        f"  ok: {label} -- fallback engaged (model_version=None), "
        "confirmed via GET /v1/transactions"
    )


async def _kafka_consumer_status(client: httpx.AsyncClient) -> str:
    # /health/ready returns 503 when degraded (aggregator/health.py) --
    # still valid JSON with the exact signal this needs, so this
    # deliberately does not call raise_for_status().
    response = await client.get("/health/ready")
    body = response.json()
    return str(body["checks"]["kafka_consumer"])


async def _assert_kafka_consumer_status(
    client: httpx.AsyncClient, expected: str, *, label: str
) -> None:
    actual = await _kafka_consumer_status(client)
    if actual != expected:
        raise ChaosExperimentError(
            f"{label}: expected checks.kafka_consumer={expected!r}, got {actual!r}"
        )
    print(f"  ok: {label} -- checks.kafka_consumer={actual!r}")


async def _counter_value(
    client: httpx.AsyncClient, metric_name: str, **labels: str
) -> float:
    """One Prometheus counter's current value, by exact line-prefix match
    against `GET /metrics`'s text exposition format -- the same approach
    `test_transactions_integration.py`/`test_labels_integration.py`'s
    `_metric_value` helper already uses, not a new parsing strategy.
    """
    response = await client.get("/metrics")
    response.raise_for_status()
    label_str = ",".join(f'{key}="{value}"' for key, value in sorted(labels.items()))
    prefix = f"{metric_name}{{{label_str}}} " if labels else f"{metric_name} "
    for line in response.text.splitlines():
        if line.startswith(prefix):
            return float(line.removeprefix(prefix))
    return 0.0


async def _poll_until(
    predicate: Callable[[], Awaitable[bool]],
    *,
    label: str,
    timeout_seconds: float = _POLL_TIMEOUT_SECONDS,
    interval_seconds: float = _POLL_INTERVAL_SECONDS,
) -> None:
    """Poll `predicate` until it returns `True`, or give up after
    `timeout_seconds` -- the script's own bail-out bound, not a
    documented recovery-time SLA (ADR-0015's Acceptance criteria).
    Matches this project's existing pattern of polling until a condition
    holds rather than sleeping a fixed amount
    (`test_end_to_end_integration.py`'s hot-and-cold-path test, ADR-0011).
    """
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if await predicate():
            return
        await asyncio.sleep(interval_seconds)
    raise ChaosExperimentError(
        f"{label}: did not recover within {timeout_seconds:.0f}s"
    )


async def _run_degradation_ladder_experiment(
    target: Literal["model-service", "feature-service"],
    gateway_client: httpx.AsyncClient,
    factory: TransactionFactory,
) -> None:
    print(f"=== chaos experiment: {target} ===")
    print("baseline: confirming the real model scores a transaction before the outage")
    await _assert_model_scored(gateway_client, factory, label="baseline")

    print(f"stopping {target}...")
    _docker_compose("stop", target)
    try:
        print("outage: confirming the degradation ladder engages")
        await _assert_fallback_engaged(gateway_client, factory, label="outage")
    finally:
        print(f"starting {target}...")
        _docker_compose("start", target)

    print("recovery: polling until the real model scores again")

    async def _recovered() -> bool:
        try:
            await _assert_model_scored(gateway_client, factory, label="recovery-poll")
        except ChaosExperimentError:
            return False
        return True

    await _poll_until(_recovered, label=f"{target} recovery")
    print(f"=== {target}: degradation and recovery both verified ===")


async def _run_kafka_experiment(
    gateway_client: httpx.AsyncClient,
    aggregator_client: httpx.AsyncClient,
    factory: TransactionFactory,
) -> None:
    """See ADR-0015's "Verification findings": `checks.kafka_consumer`
    (the originally intended signal) does not detect a live broker
    outage -- `aiokafka` retries internally and the aggregator's consume
    loop never exits, so it stays `"ok"` throughout. That is checked and
    printed below anyway, every run, as the documented limitation -- not
    worked around by dropping it, just no longer what pass/fail hinges
    on. The signal outage/recovery actually hinge on is the gateway's
    own `fraudguard_gateway_kafka_publish_total{outcome}` (ADR-0013),
    confirmed by direct measurement to increment `outcome="failure"`
    during the outage and `outcome="success"` again on recovery.
    """
    print("=== chaos experiment: kafka ===")
    print("baseline: confirming checks.kafka_consumer is 'ok' before the outage")
    await _assert_kafka_consumer_status(aggregator_client, "ok", label="baseline")
    failures_before = await _counter_value(
        gateway_client, "fraudguard_gateway_kafka_publish_total", outcome="failure"
    )

    print("stopping kafka...")
    _docker_compose("stop", "kafka")
    try:
        print(
            "outage: sending a transaction -- this blocks for tens of "
            "seconds while the gateway's own publish attempt gives up "
            "(the known, documented delay) -- then confirming "
            "kafka_publish_total{outcome=failure} incremented"
        )
        started_at = time.monotonic()
        await _post_transaction(gateway_client, factory)
        elapsed = time.monotonic() - started_at
        failures_after = await _counter_value(
            gateway_client, "fraudguard_gateway_kafka_publish_total", outcome="failure"
        )
        if failures_after <= failures_before:
            raise ChaosExperimentError(
                "outage: expected fraudguard_gateway_kafka_publish_total"
                '{outcome="failure"} to increment during the Kafka outage, '
                f"got {failures_before:.0f} -> {failures_after:.0f}"
            )
        print(
            f"  ok: outage -- kafka_publish_total{{outcome=failure}} "
            f"{failures_before:.0f} -> {failures_after:.0f} (request took "
            f"{elapsed:.1f}s)"
        )

        print(
            "outage: confirming checks.kafka_consumer -- the originally "
            "intended signal -- stays 'ok' regardless (the documented "
            "limitation, verified again, not hidden)"
        )
        await _assert_kafka_consumer_status(
            aggregator_client, "ok", label="outage (known limitation)"
        )
    finally:
        print("starting kafka...")
        _docker_compose("start", "kafka")

    print(
        "recovery: polling until a transaction completes and "
        "kafka_publish_total{outcome=success} increments again"
    )
    successes_before = await _counter_value(
        gateway_client, "fraudguard_gateway_kafka_publish_total", outcome="success"
    )

    async def _recovered() -> bool:
        try:
            await _post_transaction(gateway_client, factory)
        except httpx.HTTPError:
            return False
        successes_after = await _counter_value(
            gateway_client, "fraudguard_gateway_kafka_publish_total", outcome="success"
        )
        return successes_after > successes_before

    await _poll_until(_recovered, label="kafka recovery")
    print("  ok: recovery -- kafka_publish_total{outcome=success} incremented again")
    print(
        "=== kafka: outage and recovery both verified via kafka_publish_total; "
        "checks.kafka_consumer's limitation confirmed, not hidden ==="
    )


async def _run(
    target: Target, *, gateway_url: str, aggregator_url: str, seed: int
) -> None:
    factory = TransactionFactory(seed=seed)
    if target == "kafka":
        # See _KAFKA_REQUEST_TIMEOUT_SECONDS -- this target's gateway
        # client must outlast the documented outage-induced delay, not
        # the ~10s bound the other two targets' fast-failing fallback
        # path needs.
        async with (
            httpx.AsyncClient(
                base_url=gateway_url, timeout=_KAFKA_REQUEST_TIMEOUT_SECONDS
            ) as gateway_client,
            httpx.AsyncClient(
                base_url=aggregator_url, timeout=_REQUEST_TIMEOUT_SECONDS
            ) as aggregator_client,
        ):
            await _run_kafka_experiment(gateway_client, aggregator_client, factory)
    else:
        async with httpx.AsyncClient(
            base_url=gateway_url, timeout=_REQUEST_TIMEOUT_SECONDS
        ) as gateway_client:
            await _run_degradation_ladder_experiment(target, gateway_client, factory)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=_TARGETS)
    parser.add_argument("--gateway-url", default=_DEFAULT_GATEWAY_URL)
    parser.add_argument("--aggregator-url", default=_DEFAULT_AGGREGATOR_URL)
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    try:
        asyncio.run(
            _run(
                args.target,
                gateway_url=args.gateway_url,
                aggregator_url=args.aggregator_url,
                seed=args.seed,
            )
        )
    except ChaosExperimentError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as exc:
        print(f"FAILED: docker compose command failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
