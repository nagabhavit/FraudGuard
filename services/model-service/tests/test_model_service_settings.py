"""Tests for model-service-specific settings."""

from __future__ import annotations

import pytest

from model_service.settings import ModelServiceSettings, get_settings


def test_service_name_defaults_to_model_service() -> None:
    settings = ModelServiceSettings(_env_file=None)
    assert settings.service_name == "model-service"
    assert settings.port == 8003
    assert settings.approve_below == 0.3
    assert settings.decline_above == 0.7


def test_get_settings_reflects_current_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("port", "9003")
    settings = get_settings()
    assert settings.port == 9003
