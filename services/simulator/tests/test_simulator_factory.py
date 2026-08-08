"""Hermetic tests for TransactionFactory -- no network, no real stack.

Payload shape is verified against the same rules
`gateway.transactions.TransactionCreate` enforces (min_length=1 merchant_id,
positive amount, 3-char currency, timezone-aware occurred_at) without
importing gateway's code -- this package stays decoupled from the services
it drives, the same way the gateway itself never imports fraudguard-ml.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from statistics import mean
from uuid import UUID

import pytest

from simulator.factory import SimulatedAccount, TransactionFactory, TransactionPayload


def _assert_valid_payload(payload: TransactionPayload) -> None:
    # account_id: a real UUID.
    UUID(payload["account_id"])
    # merchant_id: non-empty, per TransactionCreate's Field(min_length=1).
    assert len(payload["merchant_id"]) >= 1
    # amount: a positive Decimal, per TransactionCreate's Field(gt=0).
    assert Decimal(payload["amount"]) > 0
    # currency: exactly 3 characters, per TransactionCreate's
    # Field(min_length=3, max_length=3).
    assert len(payload["currency"]) == 3
    # occurred_at: timezone-aware and not in the future -- TransactionCreate
    # rejects naive datetimes, and a future timestamp would be just as wrong
    # for a velocity window as a stale one.
    occurred_at = datetime.fromisoformat(payload["occurred_at"])
    assert occurred_at.tzinfo is not None
    assert occurred_at <= datetime.now(UTC)


def test_account_pool_has_the_requested_size() -> None:
    factory = TransactionFactory(seed=0, account_pool_size=25)
    assert len(factory.accounts) == 25


def test_account_pool_is_deterministic_given_a_seed() -> None:
    first = TransactionFactory(seed=42, account_pool_size=30)
    second = TransactionFactory(seed=42, account_pool_size=30)
    assert [a.account_id for a in first.accounts] == [
        a.account_id for a in second.accounts
    ]
    assert [a.archetype for a in first.accounts] == [
        a.archetype for a in second.accounts
    ]


def test_different_seeds_produce_different_pools() -> None:
    first = TransactionFactory(seed=1, account_pool_size=30)
    second = TransactionFactory(seed=2, account_pool_size=30)
    assert [a.account_id for a in first.accounts] != [
        a.account_id for a in second.accounts
    ]


def test_archetype_split_is_roughly_ninety_ten() -> None:
    # A large pool keeps the observed split close to the target 10% without
    # asserting an exact count, which a different (still-valid) seed could
    # violate by one or two accounts.
    factory = TransactionFactory(seed=7, account_pool_size=2000)
    bursty = sum(1 for a in factory.accounts if a.archetype == "bursty")
    assert 150 <= bursty <= 250  # ~10% of 2000, generous tolerance


def test_transaction_for_produces_a_valid_payload() -> None:
    factory = TransactionFactory(seed=0)
    account = factory.accounts[0]
    payload = factory.transaction_for(account)
    _assert_valid_payload(payload)
    assert payload["account_id"] == str(account.account_id)


def test_transaction_for_never_produces_a_non_positive_amount() -> None:
    # log-normal draws are always positive, but rounding to 2dp can floor a
    # vanishingly small draw to 0.00 -- astronomically unlikely at this
    # archetype's mu/sigma, so 500 draws exercises the invariant without
    # ever actually triggering the clamp; see the test below for that.
    factory = TransactionFactory(seed=0)
    account = SimulatedAccount(
        account_id=factory.accounts[0].account_id, archetype="normal"
    )
    for _ in range(500):
        payload = factory.transaction_for(account)
        assert Decimal(payload["amount"]) > 0


def test_transaction_for_clamps_a_vanishing_amount_to_one_cent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Deterministic regression test for the floor-clamp itself: forces
    # lognormvariate to return a draw that rounds to 0.00 at 2dp, which
    # TransactionCreate's Field(gt=0) would otherwise reject.
    factory = TransactionFactory(seed=0)
    account = factory.accounts[0]
    monkeypatch.setattr(factory._rng, "lognormvariate", lambda mu, sigma: 0.001)

    payload = factory.transaction_for(account)

    assert Decimal(payload["amount"]) == Decimal("0.01")


def test_transaction_for_occurred_at_tracks_wall_clock_not_the_seed() -> None:
    factory = TransactionFactory(seed=0)
    account = factory.accounts[0]
    # transaction_for jitters occurred_at up to 2s into the past (see
    # factory.py); the lower bound needs to allow for that plus test
    # execution slack, not just the jitter's nominal maximum.
    before = datetime.now(UTC) - timedelta(seconds=3)
    payload = factory.transaction_for(account)
    occurred_at = datetime.fromisoformat(payload["occurred_at"])
    assert before <= occurred_at <= datetime.now(UTC)


def test_random_transaction_produces_a_valid_payload_from_the_pool() -> None:
    factory = TransactionFactory(seed=0, account_pool_size=10)
    pool_ids = {str(a.account_id) for a in factory.accounts}
    payload = factory.random_transaction()
    _assert_valid_payload(payload)
    assert payload["account_id"] in pool_ids


def test_bursty_accounts_skew_toward_higher_amounts() -> None:
    factory = TransactionFactory(seed=3)
    bursty = next(a for a in factory.accounts if a.archetype == "bursty")
    normal = next(a for a in factory.accounts if a.archetype == "normal")

    bursty_amounts = [
        Decimal(factory.transaction_for(bursty)["amount"]) for _ in range(200)
    ]
    normal_amounts = [
        Decimal(factory.transaction_for(normal)["amount"]) for _ in range(200)
    ]

    assert mean(bursty_amounts) > mean(normal_amounts)
