"""Shared Redis feature store for FraudGuard services.

The stream aggregator (write side, Milestone 8) and feature-service (read
side, Milestone 7) both go through `FeatureStore`, so they cannot silently
disagree about key naming or windowing. See ADR-0007.
"""

from fraudguard_features.settings import LocalRedisSettings, RedisSettings
from fraudguard_features.store import VELOCITY_WINDOWS, FeatureStore

__version__ = "0.1.0"

__all__ = [
    "VELOCITY_WINDOWS",
    "FeatureStore",
    "LocalRedisSettings",
    "RedisSettings",
]
