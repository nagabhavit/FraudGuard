"""Shared feature schema and model artifact for FraudGuard's fraud model.

`ml/pipelines/train.py` (producer) and `model-service` (consumer) both
import from here, so they cannot silently disagree about feature order or
where the artifact lives. See ADR-0009. Never a dependency of the gateway,
which calls `model-service` over HTTP and must never carry LightGBM.
"""

from fraudguard_ml.features import FEATURE_NAMES, build_feature_row, feature_schema_hash
from fraudguard_ml.model import (
    FeatureSchemaMismatchError,
    FraudModel,
    ModelMetadata,
    save_model,
)
from fraudguard_ml.settings import LocalModelArtifactSettings, ModelArtifactSettings

__version__ = "0.1.0"

__all__ = [
    "FEATURE_NAMES",
    "FeatureSchemaMismatchError",
    "FraudModel",
    "LocalModelArtifactSettings",
    "ModelArtifactSettings",
    "ModelMetadata",
    "build_feature_row",
    "feature_schema_hash",
    "save_model",
]
