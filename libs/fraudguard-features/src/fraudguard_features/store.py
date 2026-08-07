"""Redis-backed feature store.

Two fraud signals, each stored in the primitive that fits its access
pattern -- see ADR-0007 for the reasoning:

- **Velocity**: a per-account sorted set (member = event_id, score =
  occurred_at). One structure answers any trailing window via `ZCOUNT`.
- **Merchant diversity**: a HyperLogLog per account per calendar day.
  Reading unions the last two day-buckets at read time via `PFCOUNT`.

`record_transaction` is the write side (the future stream aggregator,
Milestone 8); `get_feature_vector` and friends are the read side
(`feature-service`, Milestone 7). Both live here so they cannot drift
apart into two independent schemas.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Final

import redis.asyncio as redis

from fraudguard_features.settings import RedisSettings

#: Trailing windows `get_velocity` / `get_feature_vector` can answer.
VELOCITY_WINDOWS: Final[dict[str, timedelta]] = {
    "1m": timedelta(minutes=1),
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
}

# Entries older than the longest tracked window are trimmed on every write,
# so the sorted set never grows unbounded.
_MAX_VELOCITY_WINDOW = max(VELOCITY_WINDOWS.values())
# A grace period beyond the max window, so a key survives long enough to
# answer its own longest window right up until it expires, not a moment
# short of it.
_VELOCITY_KEY_TTL_SECONDS = int(
    (_MAX_VELOCITY_WINDOW + timedelta(minutes=5)).total_seconds()
)

# How many trailing calendar-day buckets a diversity read unions. 2 covers a
# rolling ~24h window even when "now" is shortly after midnight.
_DIVERSITY_LOOKBACK_DAYS = 2
_MERCHANT_BUCKET_TTL_SECONDS = int(
    timedelta(days=_DIVERSITY_LOOKBACK_DAYS).total_seconds()
)


def _velocity_key(account_id: str) -> str:
    return f"velocity:{account_id}"


def _merchant_bucket_key(account_id: str, day: datetime) -> str:
    return f"merchant_hll:{account_id}:{day:%Y-%m-%d}"


class FeatureStore:
    def __init__(self, settings: RedisSettings | None = None) -> None:
        self._settings = settings or RedisSettings()
        self._client: redis.Redis = redis.from_url(
            self._settings.url, decode_responses=True
        )

    async def record_transaction(
        self,
        account_id: str,
        event_id: str,
        merchant_id: str,
        occurred_at: datetime,
    ) -> None:
        """Write side: fold one transaction into velocity and diversity.

        A single pipeline, not four round trips -- these four writes belong
        to one transaction event and should reach Redis together.
        """
        score = occurred_at.timestamp()
        cutoff = (occurred_at - _MAX_VELOCITY_WINDOW).timestamp()
        velocity_key = _velocity_key(account_id)
        merchant_key = _merchant_bucket_key(account_id, occurred_at)

        async with self._client.pipeline(transaction=True) as pipe:
            pipe.zadd(velocity_key, {event_id: score})
            pipe.zremrangebyscore(velocity_key, "-inf", cutoff)
            pipe.expire(velocity_key, _VELOCITY_KEY_TTL_SECONDS)
            pipe.pfadd(merchant_key, merchant_id)
            pipe.expire(merchant_key, _MERCHANT_BUCKET_TTL_SECONDS)
            await pipe.execute()

    async def get_velocity(
        self, account_id: str, window: str, *, now: datetime | None = None
    ) -> int:
        """Read side: transaction count for `account_id` in the trailing `window`."""
        if window not in VELOCITY_WINDOWS:
            raise ValueError(
                f"unknown velocity window {window!r}; "
                f"expected one of {sorted(VELOCITY_WINDOWS)}"
            )
        now = now or datetime.now(UTC)
        floor = (now - VELOCITY_WINDOWS[window]).timestamp()
        count = await self._client.zcount(
            _velocity_key(account_id), floor, now.timestamp()
        )
        return int(count)

    async def get_distinct_merchants(
        self, account_id: str, *, now: datetime | None = None
    ) -> int:
        """Read side: approximate distinct-merchant count over the trailing
        ~24h (see ADR-0007 for the day-bucket boundary approximation).
        """
        now = now or datetime.now(UTC)
        keys = [
            _merchant_bucket_key(account_id, now - timedelta(days=offset))
            for offset in range(_DIVERSITY_LOOKBACK_DAYS)
        ]
        count = await self._client.pfcount(*keys)
        return int(count)

    async def get_feature_vector(
        self, account_id: str, *, now: datetime | None = None
    ) -> dict[str, int]:
        """Every feature for `account_id` in one pipelined round trip."""
        now = now or datetime.now(UTC)
        velocity_key = _velocity_key(account_id)
        merchant_keys = [
            _merchant_bucket_key(account_id, now - timedelta(days=offset))
            for offset in range(_DIVERSITY_LOOKBACK_DAYS)
        ]

        async with self._client.pipeline(transaction=False) as pipe:
            for delta in VELOCITY_WINDOWS.values():
                pipe.zcount(velocity_key, (now - delta).timestamp(), now.timestamp())
            pipe.pfcount(*merchant_keys)
            results = await pipe.execute()

        velocity = dict(zip(VELOCITY_WINDOWS.keys(), results[:-1], strict=True))
        return {
            **{f"velocity_{name}": int(count) for name, count in velocity.items()},
            "distinct_merchants_24h": int(results[-1]),
        }

    async def ping(self) -> None:
        await self._client.ping()

    async def close(self) -> None:
        await self._client.aclose()
