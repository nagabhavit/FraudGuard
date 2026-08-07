"""The feature schema every score is computed against.

One ordered list, imported by both `ml/pipelines/train.py` (which produces
a model trained on rows in this order) and `model-service` (which builds
rows in this order from a scoring request). Without a shared definition,
training and serving could silently disagree about which column is which
-- a wrong-but-not-crashing bug, since the model still returns a number for
misordered input, just not the number it would have for the intended one.
See ADR-0009.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Final

#: Order matters -- this is the exact column order the model is trained on
#: and the exact order `build_feature_row` produces.
FEATURE_NAMES: Final[tuple[str, ...]] = (
    "amount",
    "velocity_1m",
    "velocity_1h",
    "velocity_24h",
    "distinct_merchants_24h",
)


def feature_schema_hash() -> str:
    """A short, stable fingerprint of `FEATURE_NAMES`.

    Embedded in a saved model's metadata at training time
    (`fraudguard_ml.model.save_model`) and recomputed at load time
    (`fraudguard_ml.model.FraudModel.load`) so a model trained against a
    different feature schema fails to load instead of silently scoring
    against the wrong columns.
    """
    joined = ",".join(FEATURE_NAMES)
    return hashlib.sha256(joined.encode()).hexdigest()[:16]


def build_feature_row(
    *,
    amount: Decimal | float,
    velocity_1m: int,
    velocity_1h: int,
    velocity_24h: int,
    distinct_merchants_24h: int,
) -> list[float]:
    """Build one row in `FEATURE_NAMES` order.

    Keyword-only and named per feature, rather than accepting a dict, so a
    typo in a caller's key is a `TypeError` at the call site instead of a
    silently-missing feature at predict time.
    """
    values = {
        "amount": float(amount),
        "velocity_1m": float(velocity_1m),
        "velocity_1h": float(velocity_1h),
        "velocity_24h": float(velocity_24h),
        "distinct_merchants_24h": float(distinct_merchants_24h),
    }
    return [values[name] for name in FEATURE_NAMES]
