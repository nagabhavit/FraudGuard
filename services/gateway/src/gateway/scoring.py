"""Hot-path scoring: feature-service, then model-service, then a decision.

ADR-0009. The gateway calls `feature-service` then `model-service`, in that
order, synchronously, each under its own bounded timeout. On any failure --
timeout, connection error, non-2xx -- scoring falls back to a fixed rule on
the transaction's own amount, and the decision is recorded with
`model_version = None` (the existing signal, ADR-0005, that a fallback rule
decided, not the model).

The gateway does not import `fraudguard-ml` or the model/feature services'
own request/response models -- it only knows the JSON shape it sends and
receives over HTTP, the same boundary `fraudguard-events`' schema registry
client keeps with the registry it talks to.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, cast
from uuid import UUID

import httpx2 as httpx

from fraudguard_common.logging import get_logger
from fraudguard_db.models import DecisionOutcome

logger = get_logger(__name__)


@dataclass(frozen=True)
class ScoredDecision:
    outcome: DecisionOutcome
    risk_score: float
    model_version: str | None
    reason_codes: list[str] | None
    latency_ms: float


class ScoringDependency(Protocol):
    """What the gateway needs to score a transaction.

    Structural, like `ReadinessDependency`/`EventPublisher` in `app.py`, so
    tests can substitute a fake that never opens a real HTTP connection --
    the real round trip against feature-service and model-service is covered
    by `test_transactions_integration.py` against the real stack.
    """

    async def get_features(self, account_id: UUID) -> dict[str, int]: ...

    async def score(
        self,
        *,
        amount: Decimal,
        velocity_1m: int,
        velocity_1h: int,
        velocity_24h: int,
        distinct_merchants_24h: int,
    ) -> dict[str, object]: ...

    async def aclose(self) -> None: ...


class HttpScoringClient:
    """Real implementation: one short-lived HTTP call to each service."""

    def __init__(
        self,
        *,
        feature_service_url: str,
        model_service_url: str,
        timeout_seconds: float,
    ) -> None:
        self._feature_client = httpx.AsyncClient(
            base_url=feature_service_url, timeout=timeout_seconds
        )
        self._model_client = httpx.AsyncClient(
            base_url=model_service_url, timeout=timeout_seconds
        )

    async def get_features(self, account_id: UUID) -> dict[str, int]:
        response = await self._feature_client.get(f"/v1/features/{account_id}")
        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise ScoringUnavailableError(
                f"feature-service returned {response.status_code}"
            )
        payload = response.json()
        return {
            "velocity_1m": int(payload["velocity_1m"]),
            "velocity_1h": int(payload["velocity_1h"]),
            "velocity_24h": int(payload["velocity_24h"]),
            "distinct_merchants_24h": int(payload["distinct_merchants_24h"]),
        }

    async def score(
        self,
        *,
        amount: Decimal,
        velocity_1m: int,
        velocity_1h: int,
        velocity_24h: int,
        distinct_merchants_24h: int,
    ) -> dict[str, object]:
        response = await self._model_client.post(
            "/v1/score",
            json={
                "amount": str(amount),
                "velocity_1m": velocity_1m,
                "velocity_1h": velocity_1h,
                "velocity_24h": velocity_24h,
                "distinct_merchants_24h": distinct_merchants_24h,
            },
        )
        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise ScoringUnavailableError(
                f"model-service returned {response.status_code}"
            )
        result: dict[str, object] = response.json()
        return result

    async def aclose(self) -> None:
        await self._feature_client.aclose()
        await self._model_client.aclose()


class ScoringUnavailableError(Exception):
    """feature-service or model-service answered, but not usefully."""


def _fallback_outcome(amount: Decimal, *, threshold: Decimal) -> DecisionOutcome:
    return DecisionOutcome.REVIEW if amount > threshold else DecisionOutcome.APPROVE


def _fallback_decision(
    amount: Decimal, *, threshold: Decimal, latency_ms: float
) -> ScoredDecision:
    outcome = _fallback_outcome(amount, threshold=threshold)
    return ScoredDecision(
        outcome=outcome,
        # Not a calibrated probability -- the fallback rule only ever
        # produces one of two outcomes, so its risk_score is a flag, not a
        # model's confidence.
        risk_score=1.0 if outcome is DecisionOutcome.REVIEW else 0.0,
        model_version=None,
        reason_codes=None,
        latency_ms=latency_ms,
    )


async def score_transaction(
    client: ScoringDependency,
    *,
    account_id: UUID,
    amount: Decimal,
    fallback_threshold: Decimal,
) -> ScoredDecision:
    start = time.monotonic()
    try:
        features = await client.get_features(account_id)
        result = await client.score(
            amount=amount,
            velocity_1m=features["velocity_1m"],
            velocity_1h=features["velocity_1h"],
            velocity_24h=features["velocity_24h"],
            distinct_merchants_24h=features["distinct_merchants_24h"],
        )
        scored = ScoredDecision(
            outcome=DecisionOutcome(cast(str, result["outcome"])),
            risk_score=cast(float, result["risk_score"]),
            model_version=str(result["model_version"]),
            reason_codes=cast("list[str]", result["reason_codes"]),
            latency_ms=(time.monotonic() - start) * 1000,
        )
    except (httpx.HTTPError, ScoringUnavailableError, KeyError, ValueError):
        # KeyError/ValueError: a reachable but malformed response -- e.g. a
        # missing field or an outcome string DecisionOutcome does not
        # recognise -- is the same "cannot trust this answer" case as
        # unreachable, and must fall back rather than propagate a shape the
        # gateway did not ask for.
        logger.exception(
            "scoring pipeline unavailable, applying fallback rule",
            extra={"account_id": str(account_id)},
        )
        latency_ms = (time.monotonic() - start) * 1000
        return _fallback_decision(
            amount, threshold=fallback_threshold, latency_ms=latency_ms
        )

    return scored
