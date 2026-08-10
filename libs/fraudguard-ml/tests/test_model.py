"""Unit tests for FraudModel save/load/predict/explain.

Trains a tiny booster directly in the test rather than depending on
ml/pipelines/train.py's output existing on disk -- fast and hermetic. The
real training pipeline is exercised by ml/pipelines/train.py itself
(run manually / in CI as part of this milestone) and by model-service's
own integration tests against its real output.
"""

from __future__ import annotations

import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pytest

from fraudguard_ml.features import FEATURE_NAMES, feature_schema_hash
from fraudguard_ml.model import FeatureSchemaMismatchError, FraudModel, save_model


def _train_tiny_booster() -> lgb.Booster:
    rng = np.random.default_rng(seed=0)
    x = rng.random((64, len(FEATURE_NAMES)))
    # A learnable-enough pattern (not the point of this test) so the
    # booster produces non-degenerate contributions to exercise explain().
    y = (x[:, 0] + x[:, 1] > 1.0).astype(int)
    dataset = lgb.Dataset(x, label=y)
    return lgb.train(
        {"objective": "binary", "verbosity": -1, "num_leaves": 4},
        dataset,
        num_boost_round=5,
    )


@pytest.fixture
def saved_model(tmp_path: Path) -> tuple[Path, Path]:
    booster = _train_tiny_booster()
    model_path = tmp_path / "model.txt"
    metadata_path = tmp_path / "model.meta.json"
    save_model(
        booster,
        model_path,
        metadata_path,
        version="test-v1",
        auc=0.9,
        seed=0,
        n_samples=64,
    )
    return model_path, metadata_path


def test_save_model_writes_both_files(saved_model: tuple[Path, Path]) -> None:
    model_path, metadata_path = saved_model
    assert model_path.exists()
    assert metadata_path.exists()


def test_save_model_embeds_the_current_feature_schema_hash(
    saved_model: tuple[Path, Path],
) -> None:
    _, metadata_path = saved_model
    metadata = json.loads(metadata_path.read_text())
    assert metadata["feature_schema_hash"] == feature_schema_hash()
    assert metadata["feature_names"] == list(FEATURE_NAMES)


def test_load_round_trips_version_and_metadata(saved_model: tuple[Path, Path]) -> None:
    model_path, metadata_path = saved_model
    model = FraudModel.load(model_path, metadata_path)
    assert model.version == "test-v1"
    assert model.metadata.auc == 0.9


def test_save_model_records_seed_and_sample_count_for_reproducibility(
    saved_model: tuple[Path, Path],
) -> None:
    """Milestone 26: a later reader of the metadata file can tell exactly
    what generation parameters produced this model, not just when it was
    trained."""
    _, metadata_path = saved_model
    metadata = json.loads(metadata_path.read_text())
    assert metadata["seed"] == 0
    assert metadata["n_samples"] == 64


def test_predict_proba_returns_a_probability(saved_model: tuple[Path, Path]) -> None:
    model_path, metadata_path = saved_model
    model = FraudModel.load(model_path, metadata_path)
    probability = model.predict_proba([0.5, 0.5, 0.5, 0.5, 0.5])
    assert 0.0 <= probability <= 1.0


def test_explain_returns_top_n_feature_names(saved_model: tuple[Path, Path]) -> None:
    model_path, metadata_path = saved_model
    model = FraudModel.load(model_path, metadata_path)
    reasons = model.explain([0.9, 0.9, 0.1, 0.1, 0.1], top_n=2)
    assert len(reasons) == 2
    assert all(name in FEATURE_NAMES for name in reasons)


def test_load_rejects_a_model_trained_against_a_different_feature_schema(
    saved_model: tuple[Path, Path],
) -> None:
    model_path, metadata_path = saved_model
    metadata = json.loads(metadata_path.read_text())
    metadata["feature_schema_hash"] = "not-the-real-hash"
    metadata_path.write_text(json.dumps(metadata))

    with pytest.raises(FeatureSchemaMismatchError, match="feature schema"):
        FraudModel.load(model_path, metadata_path)
