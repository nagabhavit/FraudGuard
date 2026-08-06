"""Shared SQLAlchemy models and async session factory for FraudGuard services.

Every service that reads or writes Postgres depends on this package rather
than defining its own models, so the schema has exactly one definition. See
ADR-0005.
"""

from fraudguard_db.models import (
    Base,
    Decision,
    DecisionOutcome,
    Label,
    LabelSource,
    Transaction,
)
from fraudguard_db.session import Database, DatabaseSettings, LocalDatabaseSettings

__version__ = "0.1.0"

__all__ = [
    "Base",
    "Database",
    "DatabaseSettings",
    "Decision",
    "DecisionOutcome",
    "Label",
    "LabelSource",
    "LocalDatabaseSettings",
    "Transaction",
]
