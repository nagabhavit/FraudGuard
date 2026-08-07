"""Unit tests for model artifact path settings -- no I/O required."""

from __future__ import annotations

from fraudguard_ml.settings import ModelArtifactSettings


def test_defaults_point_at_ml_models() -> None:
    settings = ModelArtifactSettings()
    assert settings.model_path == "ml/models/fraud_model.txt"
    assert settings.model_metadata_path == "ml/models/fraud_model.meta.json"


def test_settings_are_overridable() -> None:
    settings = ModelArtifactSettings(
        model_path="/custom/model.txt", model_metadata_path="/custom/model.meta.json"
    )
    assert settings.model_path == "/custom/model.txt"
