"""Shared building blocks used by every FraudGuard service.

Settings base classes, structured logging, and the error taxonomy. Anything
added here is coupled to every service, so keep it thin -- a breaking change
here costs a coordinated release across the workspace.
"""

from fraudguard_common.errors import (
    ConfigurationError,
    FraudGuardError,
    NotFoundError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
    ValidationError,
)
from fraudguard_common.logging import configure_logging, get_logger, request_id_var
from fraudguard_common.metrics import (
    observe_aggregator_processing_duration,
    observe_gateway_scoring_duration,
    observe_http_request,
    record_aggregator_message,
    record_gateway_decision,
    render_metrics,
)
from fraudguard_common.settings import (
    BaseServiceSettings,
    Environment,
    LocalDevSettings,
    LogLevel,
)

__version__ = "0.1.0"

__all__ = [
    "BaseServiceSettings",
    "ConfigurationError",
    "Environment",
    "FraudGuardError",
    "LocalDevSettings",
    "LogLevel",
    "NotFoundError",
    "UpstreamTimeoutError",
    "UpstreamUnavailableError",
    "ValidationError",
    "configure_logging",
    "get_logger",
    "observe_aggregator_processing_duration",
    "observe_gateway_scoring_duration",
    "observe_http_request",
    "record_aggregator_message",
    "record_gateway_decision",
    "render_metrics",
    "request_id_var",
]
