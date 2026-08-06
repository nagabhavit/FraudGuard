"""Tests for the shared error taxonomy."""

from __future__ import annotations

import pytest

from fraudguard_common.errors import (
    ConfigurationError,
    FraudGuardError,
    NotFoundError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
    ValidationError,
)


@pytest.mark.parametrize(
    ("error_type", "expected_code", "expected_status"),
    [
        (ValidationError, "validation_error", 422),
        (NotFoundError, "not_found", 404),
        (UpstreamTimeoutError, "upstream_timeout", 504),
        (UpstreamUnavailableError, "upstream_unavailable", 503),
        (ConfigurationError, "configuration_error", 500),
    ],
)
def test_error_carries_its_code_and_status(
    error_type: type[FraudGuardError], expected_code: str, expected_status: int
) -> None:
    error = error_type("boom")
    assert error.error_code == expected_code
    assert error.http_status == expected_status
    assert error.message == "boom"
    assert str(error) == "boom"


def test_all_taxonomy_errors_derive_from_the_common_base() -> None:
    for error_type in (
        ValidationError,
        NotFoundError,
        UpstreamTimeoutError,
        UpstreamUnavailableError,
        ConfigurationError,
    ):
        assert issubclass(error_type, FraudGuardError)
