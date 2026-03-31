# service.py
#
# All active telemetry machinery:
#
#   Renderer / SplunkLogRenderer / JSONRenderer  — record → string serialisation
#   Destination / SplunkLogDestination           — string delivery to a sink
#   TelemetryService                             — buffer, span lifecycle, flush
#   measure                                      — @measure decorator

from __future__ import annotations

import inspect
import json
import logging
from abc import ABC, abstractmethod
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Generator

from splunkapplib.telemetry._internal import (
    _active_service,
    _active_span,
    _fallback,
    _now_iso,
    _now_ms,
    _span_id,
    _trace_id,
)
from splunkapplib.telemetry.records import (
    MessageRecord,
    Resource,
    SpanContext,
    SpanRecord,
    TelemetryEvent,
)


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


class Renderer(ABC):
    """Abstract base for all record renderers."""

    @abstractmethod
    def render(self, record: TelemetryEvent) -> str: ...


def _severity_text(severity: int) -> str:
    return logging.getLevelName(severity)


def _kv(d: dict[str, Any]) -> str:
    """
    Serialise a flat dict to Splunk key=value format.

    Values containing spaces, equals signs, or double-quotes are quoted.
    Backslashes and embedded double-quotes inside quoted values are escaped
    so the output is unambiguous.
    """
    parts = []
    for k, v in d.items():
        sv = str(v)
        if " " in sv or "=" in sv or '"' in sv:
            escaped = sv.replace("\\", "\\\\").replace('"', '\\"')
            parts.append(f'{k}="{escaped}"')
        else:
            parts.append(f"{k}={sv}")
    return " ".join(parts)


class SplunkLogRenderer(Renderer):
    """
    Flat key=value string for Splunk _internal logging.

    All fields top-level — Splunk parses these without spath. Suitable for
    transport via a Python logger whose output goes to _internal.

    In SPL:
        index=_internal sourcetype=splunk_python
        | where isnotnull(trace_id)
    """

    def render(self, record: TelemetryEvent) -> str:
        if isinstance(record, MessageRecord):
            d: dict[str, Any] = {
                "kind": record.kind,
                "timestamp": record.timestamp,
                "severity_text": _severity_text(record.severity),
                "severity_number": record.severity,
                "body": record.body,
                **record.resource.to_dict(),
                "trace_id": record.trace_id,
                "span_id": record.span_id,
            }
            if record.parent_span_id:
                d["parent_span_id"] = record.parent_span_id
            for k, v in record.attributes.items():
                d[f"attributes.{k}"] = v
        else:
            d = {
                "kind": record.kind,
                "timestamp": record.timestamp,
                "span_name": record.span_name,
                "span_start": record.span_start,
                "span_end": record.span_end,
                "span_duration_ms": record.span_duration_ms,
                "span_status": record.span_status,
                **record.resource.to_dict(),
                "trace_id": record.trace_id,
                "span_id": record.span_id,
            }
            if record.parent_span_id:
                d["parent_span_id"] = record.parent_span_id
            for k, v in record.attributes.items():
                d[f"attributes.{k}"] = v
        return _kv(d)


class JSONRenderer(Renderer):
    """
    Hierarchical JSON for HEC ingestion.

    resource and attributes are nested objects — no spath required for
    field access when the data lands in Splunk via HEC with JSON extraction.

    MessageRecord shape:
        {
          "timestamp": "...", "kind": "message",
          "severity_text": "INFO", "severity_number": 20,
          "body": "...", "trace_id": "...", "span_id": "...",
          "resource": { "service_name": "...", ... },
          "attributes": { "count": 47 }
        }

    SpanRecord shape:
        {
          "timestamp": "...", "kind": "span",
          "span_name": "...", "span_start": "...", "span_end": "...",
          "span_duration_ms": 12.3, "span_status": "OK",
          "trace_id": "...", "span_id": "...",
          "resource": { ... }, "attributes": { ... }
        }

    parent_span_id is included in both types only when a parent exists.
    """

    def render(self, record: TelemetryEvent) -> str:
        if isinstance(record, MessageRecord):
            d: dict[str, Any] = {
                "kind": record.kind,
                "timestamp": record.timestamp,
                "severity_text": _severity_text(record.severity),
                "severity_number": record.severity,
                "body": record.body,
                "resource": record.resource.to_nested_dict(),
                "trace_id": record.trace_id,
                "span_id": record.span_id,
            }
            if record.parent_span_id:
                d["parent_span_id"] = record.parent_span_id
            d["attributes"] = dict(record.attributes)
        else:
            d = {
                "kind": record.kind,
                "timestamp": record.timestamp,
                "span_name": record.span_name,
                "span_start": record.span_start,
                "span_end": record.span_end,
                "span_duration_ms": record.span_duration_ms,
                "span_status": record.span_status,
                "resource": record.resource.to_nested_dict(),
                "trace_id": record.trace_id,
                "span_id": record.span_id,
            }
            if record.parent_span_id:
                d["parent_span_id"] = record.parent_span_id
            d["attributes"] = dict(record.attributes)
        return json.dumps(d)


# ---------------------------------------------------------------------------
# Destinations
# ---------------------------------------------------------------------------


class Destination(ABC):
    """
    Abstract base for all telemetry destinations.

    Implement emit() to deliver a batch of records to a specific sink
    (Splunk _internal, HEC, stdout, a test buffer, etc.).

    emit() receives the full flush batch. Implementations may render
    records individually (SplunkLogDestination) or batch-send them
    (e.g. a HECDestination would build a single HTTP request).
    """

    @abstractmethod
    def emit(self, records: list[TelemetryEvent]) -> None: ...


class SplunkLogDestination(Destination):
    """
    Delivers telemetry to Splunk _internal via a Python logger.

    Renders each record with the provided renderer (defaults to
    SplunkLogRenderer for flat KV output) and writes it at INFO level
    to the provided logger. Splunk routes named Python loggers to
    _internal automatically.

    Usage:
        import logging
        dest = SplunkLogDestination(logging.getLogger("MyHandler"))
        tel.add_destination(dest)

    To use a different renderer (e.g. for a custom log format):
        dest = SplunkLogDestination(logger, renderer=MyRenderer())
    """

    def __init__(
        self,
        logger: logging.Logger,
        renderer: Renderer | None = None,
    ) -> None:
        self._logger = logger
        self._renderer = renderer or SplunkLogRenderer()

    def emit(self, records: list[TelemetryEvent]) -> None:
        for record in records:
            self._logger.info(self._renderer.render(record))


# ---------------------------------------------------------------------------
# TelemetryService
# ---------------------------------------------------------------------------


class TelemetryService:
    """
    Central telemetry object — owns the record buffer, destination list,
    and span lifecycle. One instance per handler; injected at construction
    time by the factory.

    Exposes structured logging directly (debug/info/warning/error) so that
    AbstractComponentHandler can alias self.log = self.tel — one object,
    two names, no proxy class.

    Context manager usage:

        with self.tel:
            ...work...

    __enter__: registers this service in _active_service (enables @measure)
    __exit__:  flushes the buffer to all destinations and deregisters

    The context manager is a flush/registration boundary only — it does not
    open any span. The factory opens the root span around the handler's work.

    Destinations:
      Add destinations via add_destination() before entering the context
      manager. On flush, all buffered records are sent to every destination.
      Destination failures are caught individually — a broken destination
      does not block other destinations or crash the handler.
    """

    def __init__(self, resource: Resource) -> None:
        self.resource = resource
        self._destinations: list[Destination] = []
        self._buffer: list[TelemetryEvent] = []
        self._svc_token = None

    def add_destination(self, destination: Destination) -> None:
        """Register a destination that will receive records on flush."""
        self._destinations.append(destination)

    # ------------------------------------------------------------------
    # Logging methods — exposed directly (no Logger proxy)
    # ------------------------------------------------------------------

    def debug(self, body: str, **attributes: Any) -> None:
        self._buffer_message(body, logging.DEBUG, attributes)

    def info(self, body: str, **attributes: Any) -> None:
        self._buffer_message(body, logging.INFO, attributes)

    def warning(self, body: str, **attributes: Any) -> None:
        self._buffer_message(body, logging.WARNING, attributes)

    def error(self, body: str, **attributes: Any) -> None:
        self._buffer_message(body, logging.ERROR, attributes)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _buffer_message(
        self,
        body: str,
        severity: int,
        attributes: dict[str, Any],
    ) -> None:
        """
        Constructs and buffers a MessageRecord from the active span context.

        If no span is active, the message is written to the fallback logger
        rather than buffered — trace_id and span_id are required fields on
        MessageRecord and cannot be fabricated. Wrap the emitting code in a
        span via @measure or tel.span() to fix this.
        """
        ctx = _active_span.get()

        if ctx is None:
            _fallback.warning(
                "Message outside span context — not buffered "
                "(severity=%s body=%r instance_id=%s). "
                "Wrap the emitting code in a span via @measure or tel.span().",
                logging.getLevelName(severity),
                body,
                self.resource.instance_id,
            )
            return

        self._buffer.append(
            MessageRecord(
                timestamp=_now_iso(),
                severity=severity,
                body=body,
                resource=self.resource,
                attributes=attributes,
                trace_id=ctx.trace_id,
                span_id=ctx.span_id,
                parent_span_id=ctx.parent_span_id,
            )
        )

    @contextmanager
    def span(
        self,
        name: str,
        attributes: dict[str, Any] | None = None,
    ) -> Generator[None, None, None]:
        """
        Opens a span around a block of work. Prefer @measure for named methods;
        use tel.span() for ad-hoc spans where extracting a method is impractical.

        If no span is currently active, a new trace_id is generated — this span
        becomes a root span, starting a new trace. If a span is active, this
        span inherits the active trace_id and becomes a child.

        On exit, a SpanRecord is buffered with the span's timing and status.
        On exception, an error MessageRecord is buffered first (within the span's
        context so it carries the correct trace/span IDs), then the SpanRecord
        is buffered with status "ERROR", then the exception is re-raised.
        """
        parent_ctx = _active_span.get()
        trace_id = parent_ctx.trace_id if parent_ctx else _trace_id()
        span_id = _span_id()
        parent_span_id = parent_ctx.span_id if parent_ctx else None

        ctx = SpanContext(trace_id, span_id, parent_span_id, name)
        token = _active_span.set(ctx)

        start_iso = _now_iso()
        start_ms = _now_ms()
        status = "OK"

        try:
            yield
        except Exception as exc:
            status = "ERROR"
            self._buffer_message(
                body=f"{type(exc).__name__}: {exc}",
                severity=logging.ERROR,
                attributes={
                    "exception.type": type(exc).__name__,
                    "exception.message": str(exc),
                },
            )
            raise
        finally:
            _active_span.reset(token)
            end_iso = _now_iso()
            duration = round(_now_ms() - start_ms, 3)
            self._buffer.append(
                SpanRecord(
                    timestamp=end_iso,
                    resource=self.resource,
                    attributes=attributes or {},
                    trace_id=trace_id,
                    span_id=span_id,
                    parent_span_id=parent_span_id,
                    span_name=name,
                    span_start=start_iso,
                    span_end=end_iso,
                    span_duration_ms=duration,
                    span_status=status,
                )
            )

    def flush(self) -> None:
        """
        Sends all buffered records to every registered destination.
        Clears the buffer before delivery so records are not re-sent on
        a subsequent flush even if a destination raises.

        Each destination failure is caught individually. On failure, the
        records are written to the fallback Python logger so telemetry is
        never silently discarded.
        """
        if not self._buffer:
            return

        batch = list(self._buffer)
        self._buffer.clear()

        _fallback_renderer = SplunkLogRenderer()

        for destination in self._destinations:
            try:
                destination.emit(batch)
            except Exception as exc:
                _fallback.warning(
                    "Destination %s failed (%s: %s) — writing %d records to _internal",
                    type(destination).__name__,
                    type(exc).__name__,
                    exc,
                    len(batch),
                )
                for record in batch:
                    try:
                        _fallback.info(_fallback_renderer.render(record))
                    except Exception:
                        pass

    def __enter__(self) -> TelemetryService:
        self._svc_token = _active_service.set(self)
        return self

    def __exit__(self, *_: Any) -> None:
        self.flush()
        if self._svc_token is not None:
            _active_service.reset(self._svc_token)
            self._svc_token = None


# ---------------------------------------------------------------------------
# measure decorator
# ---------------------------------------------------------------------------

# Primitive types safe to capture as span attributes from function arguments.
# Non-primitives are skipped to avoid accidentally serialising large objects
# or sensitive data that wasn't intended to appear in telemetry.
_SAFE_TYPES = (str, int, float, bool)


def measure(_fn: Callable | None = None, *, span_name: str | None = None) -> Callable:
    """
    Decorator that automatically captures a method call as a span.

    Two usage forms:

        @measure
        def _fetch_transactions(self, account_id: str, lookback_days: int):
            ...
        # span_name = "ClassName._fetch_transactions" (from __qualname__)

        @measure(span_name="custom_name")
        def execute(self, ...):
            ...
        # span_name = "custom_name"

    Behaviour:
      - Applied at class definition time — no reference to self.tel needed.
      - At call time, looks up the active TelemetryService from _active_service.
      - Primitive arguments (str, int, float, bool) are captured as span
        attributes automatically. 'self' and non-primitives are skipped.
      - If no active span exists when called, a new trace_id is generated —
        this span becomes a root span, starting a new trace. This is how
        per-result tracing works: call a @measure-decorated method per result
        with no enclosing parent and each call produces its own trace.
      - Transparent no-op if no TelemetryService is active, so decorated
        methods work normally in unit tests without any telemetry setup.
    """

    def decorator(fn: Callable) -> Callable:
        name = span_name or fn.__qualname__
        sig = inspect.signature(fn)

        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            svc = _active_service.get()
            if svc is None:
                return fn(*args, **kwargs)

            try:
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                attrs = {
                    k: v
                    for k, v in bound.arguments.items()
                    if k != "self" and isinstance(v, _SAFE_TYPES)
                }
            except TypeError:
                attrs = {}

            with svc.span(name, attributes=attrs):
                return fn(*args, **kwargs)

        return wrapper

    if _fn is not None:
        return decorator(_fn)
    return decorator
