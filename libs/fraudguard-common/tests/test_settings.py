"""Tests for the shared settings base classes."""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from fraudguard_common.settings import (
    BaseServiceSettings,
    Environment,
    LocalDevSettings,
    LogLevel,
)


def test_service_name_is_required() -> None:
    with pytest.raises(PydanticValidationError):
        BaseServiceSettings()  # type: ignore[call-arg,unused-ignore]


def test_defaults_are_local_and_info(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    settings = BaseServiceSettings(service_name="gateway")
    assert settings.environment is Environment.LOCAL
    assert settings.log_level is LogLevel.INFO
    assert settings.is_production is False


def test_reads_from_environment_case_insensitively(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("environment", "production")
    monkeypatch.setenv("log_level", "ERROR")
    settings = BaseServiceSettings(service_name="gateway")
    assert settings.environment is Environment.PRODUCTION
    assert settings.log_level is LogLevel.ERROR
    assert settings.is_production is True


def test_unknown_environment_variable_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("some_unrelated_variable", "x")
    settings = BaseServiceSettings(service_name="gateway")
    assert settings.service_name == "gateway"


def test_local_dev_settings_falls_back_to_defaults_without_a_dot_env_file() -> None:
    settings = LocalDevSettings(service_name="gateway", _env_file=None)
    assert settings.environment is Environment.LOCAL
