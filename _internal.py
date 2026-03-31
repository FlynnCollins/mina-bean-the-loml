# _internal.py
#
# Private shared state and pure utilities. No intra-package runtime dependencies.
#
# _active_service  written by TelemetryService.__enter__, read by @measure
# _active_span     written by TelemetryService.span(), read by _buffer_message
# _fallback        Python logger for messages that can't reach normal destinations

from __future__ import annotations

import logging
import secrets
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from splunkapplib.telemetry.records import SpanContext
    from splunkapplib.telemetry.service import TelemetryService

_active_service: ContextVar[TelemetryService | None] = ContextVar(
    "_active_service", default=None
)
_active_span: ContextVar[SpanContext | None] = ContextVar(
    "_active_span", default=None
)
_fallback: logging.Logger = logging.getLogger("splunkapplib.telemetry.fallback")


def _trace_id() -> str:
    """32-char hex — OTel-compatible trace_id width."""
    return secrets.token_hex(16)


def _span_id() -> str:
    """16-char hex — OTel-compatible span_id width."""
    return secrets.token_hex(8)


def _instance_id() -> str:
    """8-char hex — stable identity for one handler instance."""
    return secrets.token_hex(4)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _now_ms() -> float:
    return time.monotonic() * 1000
