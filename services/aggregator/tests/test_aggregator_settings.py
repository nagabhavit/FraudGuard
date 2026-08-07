"""Tests for aggregator-specific settings."""

from __future__ import annotations

import pytest

from aggregator.settings import AggregatorSettings, get_settings


def test_service_name_defaults_to_aggregator() -> None:
    settings = AggregatorSettings(_env_file=None)
    assert settings.service_name == "aggregator"
    assert settings.port == 8002


def test_get_settings_reflects_current_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("port", "9002")
    settings = get_settings()
    assert settings.port == 9002
