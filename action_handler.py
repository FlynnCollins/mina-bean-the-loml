# alert_action_handler.py
#
# Alert action handler base class and factory.
# Copy nothing — import and subclass AlertActionHandlerBase.

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from splunktaucclib.alert_actions_base import ModularAlertBase

from splunkapplib.core.component import ComponentType, ExecutionContext
from splunkapplib.telemetry import (
    Destination,
    Resource,
    SplunkLogDestination,
    TelemetryService,
)


class AlertActionHandlerBase:
    """
    Base class for all custom alert action handlers.

    Exposes:
      self.tel      — TelemetryService; use tel.span() for ad-hoc spans
      self.log      — alias for self.tel; self.log.info("msg", key=value, ...)
      self.context  — ExecutionContext; component_name, app, session_key, service
      self._action  — ModularAlertBase instance for Splunk alert action API access

    Override in subclasses:
      - process_alert()    — business logic for one alert event

    Optionally override:
      - initialise()       — one-time setup before process_alert()
      - on_alert_start()   — called immediately before process_alert()
      - on_alert_end()     — called after process_alert() with success status

    Do not override __init__ or run().

    Trace structure:
      The factory opens one root span per invocation, named after the alert.
      All handler code runs inside this root span — self.log is always safe
      to call. @measure or tel.span() placed by the component author create
      child spans within the invocation trace.
    """

    def __init__(
        self,
        action: ModularAlertBase,
        tel: TelemetryService,
        context: ExecutionContext,
    ) -> None:
        self.tel = tel
        self.log = tel  # alias — same object
        self.context = context
        self._action = action
        self._initialised = False

    # ------------------------------------------------------------------
    # Infrastructure — do not override
    # ------------------------------------------------------------------

    def _ensure_initialised(self) -> None:
        """
        Calls initialise() exactly once per invocation, guarded by
        self._initialised.

        If initialise() has been overridden in the concrete class, it is
        wrapped in a span so its duration is observable. If it has not
        been overridden (the base no-op), the span is suppressed entirely
        — no noise for components that need no setup.
        """
        if self._initialised:
            return

        has_override = type(self).initialise is not AlertActionHandlerBase.initialise
        if has_override:
            with self.tel.span("initialise"):
                self.log.info("Running one-time initialisation")
                self.initialise()
                self.log.info("Initialisation complete")

        self._initialised = True

    def run(self) -> int:
        """
        Drives the full alert action lifecycle for a single invocation.
        Always called inside the factory's root span and tel context manager.

        Span hierarchy (when initialise() is overridden):
            [root: <alert_name>]           — opened by factory
              [span: initialise]           — opened by _ensure_initialised
              on_alert_start()
              process_alert()
              on_alert_end()

        Exceptions from process_alert() propagate into the UCC-generated
        process_event() try/except, which handles logging and status codes.
        Our error span is recorded before UCC ever sees the exception.
        """
        success = True

        self.log.info("Alert action invoked", app=self.context.app)
        self._ensure_initialised()
        self.on_alert_start()
        try:
            self.process_alert()
        except Exception:
            success = False
            raise
        finally:
            self.on_alert_end(success=success)

        return 0

    # ------------------------------------------------------------------
    # Hooks — override in subclasses
    # ------------------------------------------------------------------

    def initialise(self) -> None:
        """
        Called once per invocation before execute().
        self.log and self.context are available.
        """
        pass

    def process_alert(self) -> None:
        """
        Business logic for a single alert event. Must be overridden.
        Access alert parameters via self._action.get_param(name).
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement process_alert()"
        )

    def on_alert_start(self) -> None:
        """Called immediately before process_alert()."""
        pass

    def on_alert_end(self, success: bool) -> None:
        """
        Called after process_alert() with outcome.
        Emits a metric-style log event:
            index=telemetry body="Alert complete"
            | stats count by attributes.success, resource.component.name
        """
        self.log.info("Alert complete", success=success)


# ---------------------------------------------------------------------------
# Factory — the Splunk protocol adapter
# ---------------------------------------------------------------------------


def make_process_event(
    handler_class: type[AlertActionHandlerBase],
    version: str = "unknown",
    destinations: list[Destination] | None = None,
):
    """
    Returns a process_event() function bound to a specific handler class.

    Mirrors make_stream() — same configuration surface, same adapter role:
      1. Extracts execution context from the ModularAlertBase instance
      2. Constructs a Resource and TelemetryService
      3. Constructs the handler with both injected
      4. Opens a root span named after the alert and runs handler.run()

    No attr/caching parameter — alert actions are ephemeral processes so
    a fresh handler is correctly constructed on every call.

    Parameters:
      handler_class  — the AlertActionHandlerBase subclass to instantiate
      version        — handler version string; surfaces as resource.service.version
      destinations   — list of Destination instances; defaults to a single
                       SplunkLogDestination writing to _internal

    Usage:
        process_event = make_process_event(MyHandler, version="1.2.0")
    """
    _destinations = destinations or [
        SplunkLogDestination(logging.getLogger(handler_class.__name__))
    ]

    def process_event(action: ModularAlertBase) -> int:
        context = ExecutionContext(
            component_name=action.alert_name,
            app=action.ta_name,
            component_type=ComponentType.ALERT_ACTION,
            user=None,
            sid=None,
            session_key=getattr(action, "_session_key", None),
            service=getattr(action, "service", None),
        )
        resource = Resource(
            service_name=handler_class.__name__,
            service_version=version,
            component_type=ComponentType.ALERT_ACTION,
            component_name=action.alert_name,
            splunk_app=action.ta_name,
        )
        tel = TelemetryService(resource)
        for dest in _destinations:
            tel.add_destination(dest)
        handler = handler_class(action, tel, context)

        with tel, tel.span(context.component_name):
            return handler.run()

    return process_event
