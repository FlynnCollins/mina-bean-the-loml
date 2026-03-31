# records.py
#
# All telemetry data types: Resource, SpanContext, MessageRecord, SpanRecord.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Union

from splunkapplib.core.component import ComponentType
from splunkapplib.telemetry._internal import _instance_id


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESOURCE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass(frozen=True)
class Resource:
    """
    Immutable descriptor of the entity producing telemetry. Present on
    every record regardless of span context.

    instance_id is generated at construction time and is stable for the
    full lifetime of the handler. It is the reliable handle for finding
    all telemetry from one specific handler run:

        index=telemetry resource.instance.id=a3f7c2b1

    This is orthogonal to trace context — a handler emits many traces
    across its lifetime but always has exactly one instance_id.
    """

    service_name: str
    service_version: str
    component_type: ComponentType
    component_name: str
    splunk_app: str
    instance_id: str = field(default_factory=_instance_id)

    # TODO: these two methods seem like they belong in the renderer objects.
    def to_dict(self) -> dict[str, str]:
        """Flat dict with resource.* prefixed keys for KV/flat rendering."""
        return {
            "resource.service.name": self.service_name,
            "resource.service.version": self.service_version,
            "resource.component.type": self.component_type.value,
            "resource.component.name": self.component_name,
            "resource.splunk.app": self.splunk_app,
            "resource.instance.id": self.instance_id,
        }

    def to_nested_dict(self) -> dict[str, str]:
        """Nested dict for hierarchical JSON rendering."""
        return {
            "service_name": self.service_name,
            "service_version": self.service_version,
            "component_type": self.component_type.value,
            "component_name": self.component_name,
            "splunk_app": self.splunk_app,
            "instance_id": self.instance_id,
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SPAN CONTEXT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class SpanContext:
    """
    Live context for the currently active span, held in a ContextVar.
    Accessible anywhere within the span's scope without being passed
    explicitly. The token/reset pattern correctly restores outer span
    context when nested spans exit, even under exceptions.
    """

    name: str
    trace_id: str
    span_id: str
    parent_span_id: str | None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RECORD TYPES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class MessageRecord:
    """
    An annotation emitted during a unit of work via self.log.info() etc.
    Describes something observed while work was happening.

    trace_id and span_id are non-optional — a MessageRecord cannot exist
    without span context. This is enforced by TelemetryService: messages
    emitted outside an active span are redirected to the fallback logger
    rather than buffered, keeping the main telemetry stream clean.

    In SPL: kind=message gives you the narrative stream.
        index=telemetry kind=message severity_text=ERROR
        | table timestamp body attributes.*
    """

    timestamp: str
    severity: int
    body: str
    resource: Resource
    attributes: dict[str, Any]
    trace_id: str
    span_id: str
    parent_span_id: str | None
    kind: str = "message"


@dataclass
class SpanRecord:
    """
    A summary emitted when a unit of work completes. Describes what was
    done, how long it took, and whether it succeeded.

    No body — spans don't narrate; they measure. The narrative is provided
    by MessageRecords emitted during the span's execution.

    span_status is "OK" or "ERROR". Spans have no severity — use span_status
    to filter for failures.

    In SPL: kind=span gives you the timing and structure stream.
        index=telemetry kind=span span_status=ERROR
        | table timestamp span_name span_duration_ms attributes.*

    Correlate with messages using trace_id:
        index=telemetry trace_id=<id>
        | sort timestamp
        | table kind span_name body severity_text span_duration_ms
    """

    timestamp: str
    resource: Resource
    attributes: dict[str, Any]
    trace_id: str
    span_id: str
    parent_span_id: str | None
    span_name: str
    span_start: str
    span_end: str
    span_duration_ms: float
    span_status: str
    kind: str = "span"


# Union type for the buffer
TelemetryEvent = Union[MessageRecord, SpanRecord]
