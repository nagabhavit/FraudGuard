"""Typed error taxonomy shared by every FraudGuard service.

CONTRIBUTING.md requires a specific exception from this taxonomy rather than
a bare `Exception`, so a service boundary (a FastAPI exception handler, a
Kafka consumer's retry policy) can dispatch on `error_code` without string-
matching a message. Each error also carries the HTTP status it maps to, so a
gateway-style service has one place -- not one `except` clause per error --
that translates domain errors into responses.
"""

from __future__ import annotations


class FraudGuardError(Exception):
    """Base of every domain error raised by FraudGuard code.

    Never raised directly -- always one of the subclasses below, so a bare
    `except FraudGuardError` still tells you which failure mode occurred via
    `error_code`.
    """

    error_code: str = "internal_error"
    http_status: int = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ValidationError(FraudGuardError):
    """The caller supplied input that fails a domain rule (not schema shape).

    Pydantic already rejects malformed request bodies before this is ever
    raised; this is for rules Pydantic cannot express, such as a foreign key
    that must exist or an amount that must be positive in this context.
    """

    error_code = "validation_error"
    http_status = 422


class NotFoundError(FraudGuardError):
    """A referenced entity (account, transaction, model version) does not exist."""

    error_code = "not_found"
    http_status = 404


class UpstreamTimeoutError(FraudGuardError):
    """A downstream dependency (Redis, the model service, Postgres) did not
    respond inside its budget.

    Distinct from `UpstreamUnavailableError` because a caller in the hot path
    treats them differently: a timeout may mean the request is still being
    processed downstream, an unavailable dependency means it was never
    accepted at all. Collapsing them would erase information the degradation
    ladder (Milestone 10+) needs.
    """

    error_code = "upstream_timeout"
    http_status = 504


class UpstreamUnavailableError(FraudGuardError):
    """A downstream dependency refused the connection or is circuit-broken."""

    error_code = "upstream_unavailable"
    http_status = 503


class ConfigurationError(FraudGuardError):
    """The service is misconfigured (missing/invalid environment variable).

    Deliberately raised at startup, never caught -- a service that starts
    with broken configuration and fails on the first request is harder to
    diagnose than one that refuses to start at all.
    """

    error_code = "configuration_error"
    http_status = 500
