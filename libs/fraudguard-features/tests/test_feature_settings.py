"""Unit tests for Redis connection settings -- no Redis required."""

from __future__ import annotations

from fraudguard_features.settings import RedisSettings


def test_defaults_match_docker_compose_local_development_values() -> None:
    settings = RedisSettings()
    assert settings.redis_host == "localhost"
    assert settings.redis_port == 6379
    assert settings.url == "redis://localhost:6379"


def test_url_reflects_overrides() -> None:
    settings = RedisSettings(redis_host="redis", redis_port=6380)
    assert settings.url == "redis://redis:6380"
