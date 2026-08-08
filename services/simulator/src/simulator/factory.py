"""Realistic synthetic transaction generation. See ADR-0011.

Two account archetypes, the same idea `ml/pipelines/train.py` uses for
training data, applied one layer up: "normal" accounts (90%) transact
infrequently at modest amounts; "bursty" accounts (10%) transact more often
and at higher amounts -- the kind of pattern that pushes the real model
toward `decline`/`review` once enough of them land inside a short window.
This module generates raw `TransactionCreate`-shaped payloads, not feature
vectors -- the archetype only becomes a real risk signal after the actual
gateway, feature-service, and model-service process it, the same way it
would for a real account.

Deliberately no `numpy`/`fraudguard-ml` dependency: this tool does no
modeling, and stdlib `random` is enough for believable-shaped traffic. The
non-cryptographic PRNG is exactly what reproducibility with `--seed` wants
here -- this is synthetic test traffic, not a security context (see the
`noqa: S311` below).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal, TypedDict
from uuid import UUID

Archetype = Literal["normal", "bursty"]

#: Matches ml/pipelines/train.py's is_bursty split -- the minority of
#: accounts that transact more often and at higher amounts.
_BURSTY_FRACTION = 0.10
_MERCHANTS = [f"merchant-{i}" for i in range(1, 21)]
_CURRENCY = "USD"

#: log-normal parameters for amount, by archetype -- bursty accounts skew
#: toward higher amounts, mirroring train.py's rng.lognormal(4.5 vs 3.5, 1.0).
_AMOUNT_LOGNORMAL_MU: dict[Archetype, float] = {"normal": 3.5, "bursty": 4.5}
_AMOUNT_LOGNORMAL_SIGMA = 1.0

#: A bursty account is weighted to appear more often in random traffic than
#: its share of the account pool alone would produce -- it is not just a
#: higher-risk account, it is a more *active* one.
_BURSTY_TRAFFIC_WEIGHT = 3.0
_NORMAL_TRAFFIC_WEIGHT = 1.0


class TransactionPayload(TypedDict):
    """The exact JSON shape `POST /v1/transactions` (`TransactionCreate`,
    `services/gateway/src/gateway/transactions.py`) expects. All string
    fields -- `Decimal`/`datetime` are not JSON-serializable by default, and
    every existing example in this repo (curl, hermetic gateway tests)
    already sends amount/occurred_at as strings.
    """

    account_id: str
    merchant_id: str
    amount: str
    currency: str
    occurred_at: str


@dataclass(frozen=True)
class SimulatedAccount:
    account_id: UUID
    archetype: Archetype


class TransactionFactory:
    """Produces `TransactionPayload`s for a pool of seeded, archetyped
    accounts.

    The account pool (who exists, and whether they're "normal" or "bursty")
    is decided once, at construction, from `seed` -- a given seed always
    produces the same pool. `occurred_at` is deliberately never fixed to a
    seed-derived value: it always tracks wall-clock "now" (see
    `transaction_for`), since feature-service's velocity windows are
    relative to real time (the same requirement the README's own curl
    example and `test_full_pipeline_integration.py` already document).
    """

    def __init__(self, *, seed: int = 0, account_pool_size: int = 40) -> None:
        self._rng = random.Random(seed)  # noqa: S311 -- synthetic test traffic, not security
        self.accounts: list[SimulatedAccount] = [
            self._new_account() for _ in range(account_pool_size)
        ]

    def _new_account(self) -> SimulatedAccount:
        archetype: Archetype = (
            "bursty" if self._rng.random() < _BURSTY_FRACTION else "normal"
        )
        # UUID(int=...) from the seeded RNG, not uuid4() -- uuid4() draws
        # from os.urandom and would make the pool different every run even
        # with the same seed, breaking the reproducibility this class exists
        # to provide.
        account_id = UUID(int=self._rng.getrandbits(128))
        return SimulatedAccount(account_id=account_id, archetype=archetype)

    def transaction_for(self, account: SimulatedAccount) -> TransactionPayload:
        """One realistic transaction for a specific account.

        Public (not just used internally by `random_transaction`) so a
        caller -- an end-to-end test wanting real velocity for one known
        account, in particular -- can send several transactions for the
        same account without relying on random collision across draws from
        the pool.
        """
        mu = _AMOUNT_LOGNORMAL_MU[account.archetype]
        amount = Decimal(
            str(round(self._rng.lognormvariate(mu, _AMOUNT_LOGNORMAL_SIGMA), 2))
        )
        if amount <= 0:
            # log-normal is always positive, but rounding a vanishingly
            # small draw to 2dp can floor to 0.00, which TransactionCreate's
            # Field(gt=0) rejects.
            amount = Decimal("0.01")

        merchant_id = self._rng.choice(_MERCHANTS)
        # A small jitter into the past, never the future -- occurred_at
        # must land inside the 1-minute velocity window feature-service
        # reads, and a future timestamp is just as wrong as a stale one.
        occurred_at = datetime.now(UTC) - timedelta(seconds=self._rng.uniform(0, 2))

        return TransactionPayload(
            account_id=str(account.account_id),
            merchant_id=merchant_id,
            amount=str(amount),
            currency=_CURRENCY,
            occurred_at=occurred_at.isoformat(),
        )

    def random_transaction(self) -> TransactionPayload:
        """One realistic transaction for a random account, weighted so
        bursty accounts -- more active in practice, not just higher-risk --
        are over-represented in the traffic this produces relative to their
        share of the account pool.
        """
        weights = [
            _BURSTY_TRAFFIC_WEIGHT
            if a.archetype == "bursty"
            else _NORMAL_TRAFFIC_WEIGHT
            for a in self.accounts
        ]
        account = self._rng.choices(self.accounts, weights=weights, k=1)[0]
        return self.transaction_for(account)
