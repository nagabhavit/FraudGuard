"""CLI entry point for the transaction simulator. See ADR-0011.

Usage:
    uv run --package fraudguard-simulator python -m simulator
    uv run --package fraudguard-simulator python -m simulator --count 50 --seed 1
    uv run --package fraudguard-simulator python -m simulator --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import asyncio

from simulator.driver import RunSummary, run
from simulator.factory import TransactionFactory

_DEFAULT_BASE_URL = "http://localhost:8000"
_DEFAULT_COUNT = 20
_DEFAULT_ACCOUNT_POOL_SIZE = 40


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=_DEFAULT_BASE_URL)
    parser.add_argument("--count", type=int, default=_DEFAULT_COUNT)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--account-pool-size", type=int, default=_DEFAULT_ACCOUNT_POOL_SIZE
    )
    return parser.parse_args()


def _print_summary(summary: RunSummary) -> None:
    print(
        f"sent {summary.sent}: {summary.succeeded} succeeded, {summary.failed} failed"
    )
    for outcome, outcome_count in sorted(summary.outcomes.items()):
        print(f"  {outcome}: {outcome_count}")
    for error in summary.errors[:5]:
        print(f"  error: {error}")


def main() -> None:
    args = _parse_args()
    factory = TransactionFactory(
        seed=args.seed, account_pool_size=args.account_pool_size
    )
    summary = asyncio.run(run(factory, base_url=args.base_url, count=args.count))
    _print_summary(summary)


if __name__ == "__main__":
    main()
