"""Tests for gateway-specific settings."""

from __future__ import annotations

import pytest

from gateway.settings import GatewaySettings, get_settings


def test_service_name_defaults_to_gateway() -> None:
    settings = GatewaySettings(_env_file=None)
    assert settings.service_name == "gateway"
    assert settings.port == 8000


def test_get_settings_reflects_current_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("port", "9000")
    settings = get_settings()
    assert settings.port == 9000
