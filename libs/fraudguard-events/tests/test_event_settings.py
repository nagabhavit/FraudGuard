"""Unit tests for connection settings -- no Kafka or Schema Registry required."""

from __future__ import annotations

from fraudguard_events.settings import EventSettings


def test_defaults_match_docker_compose_local_development_values() -> None:
    settings = EventSettings()
    assert settings.kafka_bootstrap_servers == "localhost:29092"
    assert settings.schema_registry_url == "http://localhost:8081"


def test_settings_are_overridable() -> None:
    settings = EventSettings(
        kafka_bootstrap_servers="kafka:9092",
        schema_registry_url="http://schema-registry:8081",
    )
    assert settings.kafka_bootstrap_servers == "kafka:9092"
    assert settings.schema_registry_url == "http://schema-registry:8081"
