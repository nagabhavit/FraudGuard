"""Tests for feature-service-specific settings."""

from __future__ import annotations

import pytest

from feature_service.settings import FeatureServiceSettings, get_settings


def test_service_name_defaults_to_feature_service() -> None:
    settings = FeatureServiceSettings(_env_file=None)
    assert settings.service_name == "feature-service"
    assert settings.port == 8001


def test_get_settings_reflects_current_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("port", "9001")
    settings = get_settings()
    assert settings.port == 9001
