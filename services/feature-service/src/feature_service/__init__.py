"""FraudGuard feature service.

Serves precomputed fraud-detection features (velocity, merchant diversity)
from Redis over HTTP -- the read side of the feature store built in
`fraudguard-features`. See ADR-0007.
"""

__version__ = "0.1.0"
