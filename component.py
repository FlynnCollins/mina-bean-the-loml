# base_handler.py
#
# Root of the component handler inheritance hierarchy.
#
# No Splunk imports here — this module and everything below it in the
# hierarchy is pure Python. All Splunk protocol knowledge lives exclusively
# in the factory functions at the bottom of each component handler module.

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol


class ComponentType(str, Enum):
    """
    Valid Splunk component type identifiers. Inheriting from str means
    values serialise directly without .value access.
    """

    ALERT_ACTION = "alert_action"
    MODULAR_INPUT = "modular_input"
    SEARCH_COMMAND = "search_command"
    REST_HANDLER = "rest_handler"


class TelemetryProtocol(Protocol):
    """
    Structural interface for the telemetry service as seen by handler code.

    Defines the logging methods and span context manager that handlers depend
    on. TelemetryService satisfies this protocol structurally — no explicit
    registration needed. Using a Protocol here keeps core/ free of any runtime
    import from splunkapplib.telemetry.
    """

    def debug(self, body: str, **attributes: Any) -> None: ...
    def info(self, body: str, **attributes: Any) -> None: ...
    def warning(self, body: str, **attributes: Any) -> None: ...
    def error(self, body: str, **attributes: Any) -> None: ...
    def span(
        self, name: str, attributes: dict[str, Any] | None = None
    ) -> AbstractContextManager[None]: ...


class EventWriterProtocol(Protocol):
    """
    Structural interface for writing events from a modular input handler.

    The factory injects a concrete adapter (_SplunkEventWriterAdapter) that
    wraps smi.EventWriter and satisfies this protocol. Handler code calls
    self._writer.write({...}) without ever importing splunklib.modularinput.

    All keyword arguments are optional; omit those you don't need.
    """

    def write(
        self,
        event: dict,
        *,
        sourcetype: str | None = None,
        index: str | None = None,
        host: str | None = None,
        time: float | None = None,
    ) -> None: ...


@dataclass
class ExecutionContext:
    """
    Protocol-agnostic snapshot of the execution environment for one
    component invocation. Assembled by the factory from whatever Splunk
    protocol is in use (V2 chunked, modular alert, modular input) and
    injected into the handler at construction time.

    This dataclass is the seam between Splunk's protocols and our handler
    code. Handlers read from it; they never write to it and never hold a
    reference to the underlying Splunk objects it was built from.

    Fields that a given protocol cannot provide are None. Code that needs
    a specific field should document that requirement rather than assuming
    availability.

    component_name  — SPL command name, alert name, or input name
    component_type  — category of component (SEARCH_COMMAND, ALERT_ACTION, etc.)
    app             — Splunk app context for this invocation
    user            — Search owner or action owner (None for some protocols)
    sid             — Search ID (commands only; None for alert actions/inputs)
    session_key     — Splunk REST session key for authenticated API calls
    service         — Constructed splunklib.client.Service, or None
    """

    component_name: str
    app: str
    component_type: ComponentType
    user: str | None = None
    sid: str | None = None
    session_key: str | None = None
    service: Any | None = None


class AbstractComponentHandler:
    """
    Root base class for all splunkapplib component handlers.

    Defines the constructor contract for the hierarchy: every handler
    receives an assembled TelemetryService and an ExecutionContext,
    both constructed and injected by the factory before this class
    is ever instantiated.

    Exposes:
      self.tel      — the TelemetryService for span management
      self.log      — alias for self.tel; same object, ergonomic logging
      self.context  — the ExecutionContext for execution environment data

    Concrete handlers do not call this constructor directly. They call
    super().__init__(tel, context) from their component-specific base
    class (CommandHandlerBase, AlertActionHandlerBase, etc.) which adds
    its own protocol-specific initialisation after the super().__init__.
    """

    def __init__(self, tel: TelemetryProtocol, context: ExecutionContext) -> None:
        self.tel = tel
        self.log = tel  # alias — same object
        self.context = context
