"""Tests for the application factory's startup behaviour.

No lifespan tests here (unlike the gateway, feature-service, and
aggregator): there is no async resource to start or stop -- see the note
in app.py. What is worth testing is the fail-fast behaviour itself.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from model_service.app import create_app
from model_service.settings import ModelServiceSettings


def test_create_app_fails_fast_when_no_model_file_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """See ADR-0009: this service refuses to start rather than come up
    into a permanently-degraded state, the same choice `aggregator` makes
    for a missing Kafka topic.
    """
    monkeypatch.setenv("model_path", str(tmp_path / "does-not-exist.txt"))
    monkeypatch.setenv(
        "model_metadata_path", str(tmp_path / "does-not-exist.meta.json")
    )

    with pytest.raises(FileNotFoundError):
        create_app(ModelServiceSettings(_env_file=None))
