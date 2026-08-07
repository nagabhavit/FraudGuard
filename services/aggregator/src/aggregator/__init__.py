"""FraudGuard stream aggregator.

Consumes `fraudguard.transactions.v1` and folds each event into the Redis
feature store built in `fraudguard-features` -- the write side of the cold
path. See ADR-0008.
"""

__version__ = "0.1.0"
