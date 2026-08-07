"""Save and load the fraud model artifact.

LightGBM's native `Booster` format (text, human-diffable, no pickle
version-compatibility risk), not a pickled sklearn wrapper -- see ADR-0009
for why, including why the native API is what makes SHAP-style reason
codes (`pred_contrib`) straightforward.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np

from fraudguard_ml.features import FEATURE_NAMES, feature_schema_hash

#: How many top-contributing features `FraudModel.explain` returns.
_DEFAULT_REASON_CODE_COUNT = 3


class FeatureSchemaMismatchError(RuntimeError):
    """The saved model was trained against a different feature schema than
    this process's `fraudguard_ml.features.FEATURE_NAMES`.

    Raised at load time, not predict time -- a service that fails to start
    is a clearer signal than one that starts and silently scores every
    request against misaligned columns.
    """


@dataclass(frozen=True)
class ModelMetadata:
    version: str
    feature_schema_hash: str
    feature_names: tuple[str, ...]
    trained_at: str
    auc: float


class FraudModel:
    """A loaded booster plus the metadata describing what it expects."""

    def __init__(self, booster: lgb.Booster, metadata: ModelMetadata) -> None:
        self._booster = booster
        self.metadata = metadata

    @property
    def version(self) -> str:
        return self.metadata.version

    def predict_proba(self, row: list[float]) -> float:
        """Probability the transaction described by `row` is fraudulent."""
        prediction = self._booster.predict(np.array([row]))
        return float(np.asarray(prediction)[0])

    def explain(
        self, row: list[float], top_n: int = _DEFAULT_REASON_CODE_COUNT
    ) -> list[str]:
        """The `top_n` feature names with the largest absolute SHAP
        contribution to this row's prediction.

        `pred_contrib=True` returns one contribution per feature plus a
        trailing bias/expected-value term -- the bias term is dropped since
        it is not a feature and has no name to report.
        """
        contributions = np.asarray(
            self._booster.predict(np.array([row]), pred_contrib=True)
        )[0]
        feature_contributions = contributions[: len(FEATURE_NAMES)]
        ranked = sorted(
            zip(FEATURE_NAMES, feature_contributions, strict=True),
            key=lambda pair: abs(pair[1]),
            reverse=True,
        )
        return [name for name, _ in ranked[:top_n]]

    @classmethod
    def load(cls, model_path: Path, metadata_path: Path) -> FraudModel:
        raw: dict[str, Any] = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata = ModelMetadata(
            version=raw["version"],
            feature_schema_hash=raw["feature_schema_hash"],
            feature_names=tuple(raw["feature_names"]),
            trained_at=raw["trained_at"],
            auc=raw["auc"],
        )
        current_hash = feature_schema_hash()
        if metadata.feature_schema_hash != current_hash:
            raise FeatureSchemaMismatchError(
                f"model {metadata.version!r} was trained against feature schema "
                f"{metadata.feature_schema_hash!r}, but this process's "
                f"fraudguard_ml.features.FEATURE_NAMES hashes to {current_hash!r}. "
                "Retrain the model or roll back the feature schema change."
            )
        booster = lgb.Booster(model_file=str(model_path))
        return cls(booster, metadata)


def save_model(
    booster: lgb.Booster,
    model_path: Path,
    metadata_path: Path,
    *,
    version: str,
    auc: float,
) -> ModelMetadata:
    """Save `booster` and its metadata as a matched pair.

    Called only by `ml/pipelines/train.py` -- `model-service` only ever
    reads what this writes.
    """
    metadata = ModelMetadata(
        version=version,
        feature_schema_hash=feature_schema_hash(),
        feature_names=FEATURE_NAMES,
        trained_at=datetime.now(UTC).isoformat(),
        auc=auc,
    )
    model_path.parent.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(model_path))
    metadata_path.write_text(json.dumps(asdict(metadata), indent=2), encoding="utf-8")
    return metadata
