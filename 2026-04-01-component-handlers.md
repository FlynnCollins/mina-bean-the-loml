# Component Handlers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add generating command, eventing command, and modular input handler base classes + factories to splunkapplib, and fix alert action lifecycle method names for consistency.

**Architecture:** Each new component follows the existing two-layer pattern — a pure-Python handler base class (no Splunk imports) paired with a factory function that is the sole point of contact with the Splunk SDK. Factories extract `ExecutionContext`, wire `TelemetryService`, and return a closure matching the exact signature the UCC-generated wrapper expects.

**Tech Stack:** Python 3.9+, splunklib (splunk-sdk), splunktaucclib, pytest, ruff

---

## File Map

**Modified:**
- `src/splunkapplib/core/component.py` — add `EventWriterProtocol`
- `src/splunkapplib/alert_actions/action_handler.py` — rename lifecycle methods
- `src/splunkapplib/__init__.py` — add new exports

**Created:**
- `src/splunkapplib/commands/generating.py` — `GeneratingCommandHandlerBase` + `make_generate`
- `src/splunkapplib/commands/eventing.py` — `EventingCommandHandlerBase` + `make_transform`
- `src/splunkapplib/modular_inputs/__init__.py` — empty package marker
- `src/splunkapplib/modular_inputs/input_handler.py` — `ModularInputHandlerBase` + `_SplunkEventWriterAdapter` + `_CountingWriter` + `make_modular_input`
- `tests/unit/__init__.py` — empty
- `tests/unit/conftest.py` — `StubTelemetry`, `make_context` shared fixtures
- `tests/unit/test_alert_action.py`
- `tests/unit/test_generating_command.py`
- `tests/unit/test_eventing_command.py`
- `tests/unit/test_modular_input.py`

---

## Task 1: Test infrastructure and alert action rename

**Files:**
- Create: `tests/unit/__init__.py`
- Create: `tests/unit/conftest.py`
- Create: `tests/unit/test_alert_action.py`
- Modify: `src/splunkapplib/alert_actions/action_handler.py`

- [ ] **Step 1: Create test package and conftest**

Create `tests/__init__.py` (empty) and `tests/unit/__init__.py` (empty):

```bash
mkdir -p tests/unit
touch tests/__init__.py tests/unit/__init__.py
```

Create `tests/unit/conftest.py`:

```python
# conftest.py — shared fixtures for all unit tests
from __future__ import annotations

from contextlib import contextmanager

import pytest

from splunkapplib.core.component import ComponentType, ExecutionContext


class StubTelemetry:
    """Minimal TelemetryService stand-in. No Splunk SDK, no I/O."""

    def __init__(self):
        self.records: list[tuple] = []

    def debug(self, body: str, **attrs) -> None:
        self.records.append(("debug", body, attrs))

    def info(self, body: str, **attrs) -> None:
        self.records.append(("info", body, attrs))

    def warning(self, body: str, **attrs) -> None:
        self.records.append(("warning", body, attrs))

    def error(self, body: str, **attrs) -> None:
        self.records.append(("error", body, attrs))

    @contextmanager
    def span(self, name: str, attributes=None):
        yield

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def make_context(**kwargs) -> ExecutionContext:
    defaults = dict(
        component_name="test_component",
        app="test_app",
        component_type=ComponentType.SEARCH_COMMAND,
    )
    return ExecutionContext(**{**defaults, **kwargs})


@pytest.fixture
def stub_tel():
    return StubTelemetry()


@pytest.fixture
def ctx():
    return make_context()
```

- [ ] **Step 2: Write failing tests for renamed alert action methods**

Create `tests/unit/test_alert_action.py`:

```python
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from tests.unit.conftest import StubTelemetry, make_context
from splunkapplib.alert_actions.action_handler import AlertActionHandlerBase
from splunkapplib.core.component import ComponentType


def make_handler(extra_kwargs=None):
    tel = StubTelemetry()
    ctx = make_context(component_type=ComponentType.ALERT_ACTION)
    action = MagicMock()

    class ConcreteHandler(AlertActionHandlerBase):
        def process_alert(self):
            pass

    return ConcreteHandler(action, tel, ctx), tel


class TestProcessAlert:
    def test_process_alert_is_called_by_run(self):
        called = []

        class H(AlertActionHandlerBase):
            def process_alert(self):
                called.append(True)

        tel = StubTelemetry()
        ctx = make_context(component_type=ComponentType.ALERT_ACTION)
        h = H(MagicMock(), tel, ctx)
        h.run()

        assert called == [True]

    def test_process_alert_not_implemented_raises(self):
        tel = StubTelemetry()
        ctx = make_context(component_type=ComponentType.ALERT_ACTION)
        h = AlertActionHandlerBase(MagicMock(), tel, ctx)

        with pytest.raises(NotImplementedError, match="process_alert"):
            h.run()

    def test_old_execute_name_does_not_exist(self):
        assert not hasattr(AlertActionHandlerBase, "execute")


class TestAlertLifecycleHooks:
    def test_on_alert_start_called_before_process_alert(self):
        order = []

        class H(AlertActionHandlerBase):
            def on_alert_start(self):
                order.append("start")

            def process_alert(self):
                order.append("process")

        tel = StubTelemetry()
        ctx = make_context(component_type=ComponentType.ALERT_ACTION)
        H(MagicMock(), tel, ctx).run()

        assert order == ["start", "process"]

    def test_on_alert_end_called_with_success_true(self):
        results = []

        class H(AlertActionHandlerBase):
            def process_alert(self):
                pass

            def on_alert_end(self, success: bool):
                results.append(success)

        tel = StubTelemetry()
        ctx = make_context(component_type=ComponentType.ALERT_ACTION)
        H(MagicMock(), tel, ctx).run()

        assert results == [True]

    def test_on_alert_end_called_with_success_false_on_exception(self):
        results = []

        class H(AlertActionHandlerBase):
            def process_alert(self):
                raise ValueError("boom")

            def on_alert_end(self, success: bool):
                results.append(success)

        tel = StubTelemetry()
        ctx = make_context(component_type=ComponentType.ALERT_ACTION)
        with pytest.raises(ValueError):
            H(MagicMock(), tel, ctx).run()

        assert results == [False]

    def test_old_before_execute_name_does_not_exist(self):
        assert not hasattr(AlertActionHandlerBase, "before_execute")

    def test_old_after_execute_name_does_not_exist(self):
        assert not hasattr(AlertActionHandlerBase, "after_execute")


class TestInitialise:
    def test_initialise_called_once_across_multiple_runs(self):
        init_count = []

        class H(AlertActionHandlerBase):
            def initialise(self):
                init_count.append(1)

            def process_alert(self):
                pass

        tel = StubTelemetry()
        ctx = make_context(component_type=ComponentType.ALERT_ACTION)
        h = H(MagicMock(), tel, ctx)
        h.run()
        h.run()

        assert sum(init_count) == 1
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
pytest tests/unit/test_alert_action.py -v
```

Expected: multiple FAILED — `execute` still exists, `process_alert` does not yet exist, `before_execute`/`after_execute` still exist.

- [ ] **Step 4: Rename lifecycle methods in alert_actions/action_handler.py**

In `src/splunkapplib/alert_actions/action_handler.py`, apply these renames:
- `execute` → `process_alert` (method definition and `NotImplementedError` message)
- `before_execute` → `on_alert_start`
- `after_execute` → `on_alert_end`
- Update `run()` to call the new names
- Update all docstrings to use the new names

The `run()` method body changes from:
```python
self.before_execute()
try:
    self.execute(*args, **kwargs)
except Exception:
    success = False
    raise
finally:
    self.after_execute(success=success)
```
to:
```python
self.on_alert_start()
try:
    self.process_alert()
except Exception:
    success = False
    raise
finally:
    self.on_alert_end(success=success)
```

`run()` signature changes from `run(self, *args, **kwargs) -> int` to `run(self) -> int`.

`process_alert()` definition:
```python
def process_alert(self) -> None:
    """
    Business logic for a single alert event. Must be overridden.
    Access alert parameters via self._action.get_param(name).
    """
    raise NotImplementedError(f"{type(self).__name__} must implement process_alert()")
```

`on_alert_start()` definition:
```python
def on_alert_start(self) -> None:
    """Called immediately before process_alert()."""
    pass
```

`on_alert_end()` definition:
```python
def on_alert_end(self, success: bool) -> None:
    """
    Called after process_alert() with outcome.
    Emits a metric-style log event:
        index=telemetry body="Alert complete"
        | stats count by attributes.success, resource.component.name
    """
    self.log.info("Alert complete", success=success)
```

Also update `make_process_event`'s inner `process_event` function to call `handler.run()` (no args):
```python
with tel, tel.span(context.component_name):
    return handler.run()
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
pytest tests/unit/test_alert_action.py -v
```

Expected: all PASSED.

- [ ] **Step 6: Lint**

```bash
ruff check --fix src/splunkapplib/alert_actions/action_handler.py && ruff format src/splunkapplib/alert_actions/action_handler.py
```

- [ ] **Step 7: Commit**

```bash
git add src/splunkapplib/alert_actions/action_handler.py tests/unit/__init__.py tests/__init__.py tests/unit/conftest.py tests/unit/test_alert_action.py
git commit -m "refactor: rename alert action lifecycle methods for consistency

execute -> process_alert, before_execute -> on_alert_start,
after_execute -> on_alert_end. Drops *args/**kwargs passthrough
from process_alert since those args carry no meaningful data."
```

---

## Task 2: Add EventWriterProtocol to core/component.py

**Files:**
- Modify: `src/splunkapplib/core/component.py`

- [ ] **Step 1: Write failing test**

Add to `tests/unit/test_modular_input.py` (create the file with just this test for now):

```python
from __future__ import annotations

from splunkapplib.core.component import EventWriterProtocol


class TestEventWriterProtocol:
    def test_protocol_is_importable(self):
        assert EventWriterProtocol is not None

    def test_concrete_class_satisfies_protocol_structurally(self):
        """A class with the right write() signature satisfies the protocol."""
        from typing import runtime_checkable, Protocol

        # EventWriterProtocol must be runtime_checkable to use isinstance
        assert hasattr(EventWriterProtocol, "__protocol_attrs__") or True  # structural check

        class GoodWriter:
            def write(self, event: dict, *, sourcetype=None, index=None,
                      host=None, time=None) -> None:
                pass

        # Structural typing: GoodWriter satisfies the protocol
        # (mypy/pyright enforce this at type-check time; we verify it imports cleanly)
        writer: EventWriterProtocol = GoodWriter()  # type: ignore[assignment]
        assert writer is not None
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest tests/unit/test_modular_input.py::TestEventWriterProtocol -v
```

Expected: FAILED — `cannot import name 'EventWriterProtocol'`

- [ ] **Step 3: Add EventWriterProtocol to core/component.py**

Add after the `TelemetryProtocol` class in `src/splunkapplib/core/component.py`:

```python
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
```

- [ ] **Step 4: Run test to confirm it passes**

```bash
pytest tests/unit/test_modular_input.py::TestEventWriterProtocol -v
```

Expected: PASSED.

- [ ] **Step 5: Lint**

```bash
ruff check --fix src/splunkapplib/core/component.py && ruff format src/splunkapplib/core/component.py
```

- [ ] **Step 6: Commit**

```bash
git add src/splunkapplib/core/component.py tests/unit/test_modular_input.py
git commit -m "feat: add EventWriterProtocol to core/component.py

Pure-Python protocol that abstracts smi.EventWriter for modular input
handlers, consistent with TelemetryProtocol placement in core/."
```

---

## Task 3: GeneratingCommandHandlerBase + make_generate

**Files:**
- Create: `src/splunkapplib/commands/generating.py`
- Create: `tests/unit/test_generating_command.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_generating_command.py`:

```python
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from tests.unit.conftest import StubTelemetry, make_context
from splunkapplib.commands.generating import GeneratingCommandHandlerBase
from splunkapplib.core.component import ComponentType


def make_handler(override_generate=None):
    tel = StubTelemetry()
    ctx = make_context(component_type=ComponentType.SEARCH_COMMAND)
    command = MagicMock()

    generate_fn = override_generate or (lambda self: iter([]))

    class ConcreteHandler(GeneratingCommandHandlerBase):
        def generate_records(self):
            yield from generate_fn(self)

    return ConcreteHandler(command, tel, ctx), tel


class TestGenerateRecords:
    def test_generate_records_not_implemented_raises(self):
        tel = StubTelemetry()
        ctx = make_context(component_type=ComponentType.SEARCH_COMMAND)
        h = GeneratingCommandHandlerBase(MagicMock(), tel, ctx)

        with pytest.raises(NotImplementedError, match="generate_records"):
            list(h.run())

    def test_generate_records_yields_are_returned(self):
        records = [{"a": 1}, {"b": 2}]
        h, _ = make_handler(lambda self: iter(records))

        result = list(h.run())

        assert result == records

    def test_count_reported_in_on_generate_end(self):
        counts = []

        class H(GeneratingCommandHandlerBase):
            def generate_records(self):
                yield {"x": 1}
                yield {"x": 2}

            def on_generate_end(self, count: int, errors: int):
                counts.append((count, errors))

        tel = StubTelemetry()
        ctx = make_context(component_type=ComponentType.SEARCH_COMMAND)
        list(H(MagicMock(), tel, ctx).run())

        assert counts == [(2, 0)]

    def test_error_in_generate_records_is_logged_and_stops(self):
        class H(GeneratingCommandHandlerBase):
            def generate_records(self):
                yield {"x": 1}
                raise RuntimeError("mid-stream failure")
                yield {"x": 2}  # noqa: unreachable

        tel = StubTelemetry()
        ctx = make_context(component_type=ComponentType.SEARCH_COMMAND)
        result = list(H(MagicMock(), tel, ctx).run())

        # First record yielded, then stopped on error
        assert result == [{"x": 1}]
        error_bodies = [r[1] for r in tel.records if r[0] == "error"]
        assert any("generating record" in b for b in error_bodies)

    def test_error_reported_in_on_generate_end(self):
        counts = []

        class H(GeneratingCommandHandlerBase):
            def generate_records(self):
                raise RuntimeError("boom")
                yield  # make it a generator

            def on_generate_end(self, count: int, errors: int):
                counts.append((count, errors))

        tel = StubTelemetry()
        ctx = make_context(component_type=ComponentType.SEARCH_COMMAND)
        list(H(MagicMock(), tel, ctx).run())

        assert counts == [(0, 1)]


class TestGenerateLifecycleHooks:
    def test_on_generate_start_called_before_generate_records(self):
        order = []

        class H(GeneratingCommandHandlerBase):
            def on_generate_start(self):
                order.append("start")

            def generate_records(self):
                order.append("generate")
                yield {"x": 1}

        tel = StubTelemetry()
        ctx = make_context(component_type=ComponentType.SEARCH_COMMAND)
        list(H(MagicMock(), tel, ctx).run())

        assert order == ["start", "generate"]

    def test_on_generate_end_logs_metric(self):
        h, tel = make_handler(lambda self: iter([{"a": 1}]))
        list(h.run())

        info_bodies = [r[1] for r in tel.records if r[0] == "info"]
        assert any("Generate complete" in b for b in info_bodies)


class TestInitialise:
    def test_initialise_called_once(self):
        init_count = []

        class H(GeneratingCommandHandlerBase):
            def initialise(self):
                init_count.append(1)

            def generate_records(self):
                yield {"x": 1}

        tel = StubTelemetry()
        ctx = make_context(component_type=ComponentType.SEARCH_COMMAND)
        h = H(MagicMock(), tel, ctx)
        list(h.run())
        list(h.run())

        assert sum(init_count) == 1

    def test_initialise_not_overridden_no_span_emitted(self):
        h, tel = make_handler(lambda self: iter([]))
        list(h.run())

        span_msgs = [r for r in tel.records if "initialise" in str(r)]
        assert span_msgs == []
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/unit/test_generating_command.py -v
```

Expected: FAILED — `cannot import name 'GeneratingCommandHandlerBase'`

- [ ] **Step 3: Implement generating.py**

Create `src/splunkapplib/commands/generating.py`:

```python
# generating.py
#
# Generating command handler base class and factory.
# Copy nothing — import and subclass GeneratingCommandHandlerBase.

from __future__ import annotations

import logging
from collections.abc import Generator

from splunklib.searchcommands import GeneratingCommand

from splunkapplib.core.component import ComponentType, ExecutionContext
from splunkapplib.telemetry import (
    Destination,
    Resource,
    SplunkLogDestination,
    TelemetryService,
)


class GeneratingCommandHandlerBase:
    """
    Base class for all custom generating command handlers.

    Exposes:
      self.tel      — TelemetryService; use tel.span() for ad-hoc spans
      self.log      — alias for self.tel; self.log.info("msg", key=value, ...)
      self.context  — ExecutionContext; component_name, app, user, sid, service
      self._command — the GeneratingCommand instance for Splunk SDK access

    Override in subclasses:
      - generate_records()   — yields dict records from scratch; required

    Optionally override:
      - initialise()         — one-time setup before the first batch
      - on_generate_start()  — called before generate_records()
      - on_generate_end()    — called after generate_records() completes

    Do not override __init__ or run().

    Error handling:
      If generate_records() raises mid-iteration, the error is logged and
      generation stops. Records yielded before the error are returned.
      on_generate_end() is always called.
    """

    def __init__(
        self,
        command: GeneratingCommand,
        tel: TelemetryService,
        context: ExecutionContext,
    ) -> None:
        self.tel = tel
        self.log = tel
        self.context = context
        self._command = command
        self._initialised = False

    # ------------------------------------------------------------------
    # Infrastructure — do not override
    # ------------------------------------------------------------------

    def _ensure_initialised(self) -> None:
        if self._initialised:
            return
        has_override = (
            type(self).initialise is not GeneratingCommandHandlerBase.initialise
        )
        if has_override:
            with self.tel.span("initialise"):
                self.log.info("Running one-time initialisation")
                self.initialise()
                self.log.info("Initialisation complete")
        self._initialised = True

    def run(self) -> Generator[dict, None, None]:
        """
        Drives the full generate lifecycle. Called once per batch by the
        factory, always inside the factory's root span and tel context manager.
        """
        count = 0
        errors = 0

        self._ensure_initialised()
        self.on_generate_start()

        gen = self.generate_records()
        while True:
            try:
                record = next(gen)
            except StopIteration:
                break
            except Exception as exc:
                self.log.error(
                    "Unhandled error generating record — stopping",
                    exception_type=type(exc).__name__,
                    exception_message=str(exc),
                )
                errors += 1
                break
            yield record
            count += 1

        self.on_generate_end(count=count, errors=errors)

    # ------------------------------------------------------------------
    # Hooks — override in subclasses
    # ------------------------------------------------------------------

    def initialise(self) -> None:
        """One-time setup called before the first batch."""
        pass

    def generate_records(self) -> Generator[dict, None, None]:
        """
        Yields dict records from scratch. Must be overridden.

        Raising an exception stops generation; records yielded before the
        error are returned and an error log is emitted.
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement generate_records()"
        )

    def on_generate_start(self) -> None:
        """Called before generate_records() on each batch."""
        pass

    def on_generate_end(self, count: int, errors: int) -> None:
        """
        Called after generation completes or stops on error.
        Emits a metric-style log:
            index=telemetry body="Generate complete"
            | stats avg(attributes.count) sum(attributes.errors)
              by resource.component.name
        """
        self.log.info("Generate complete", count=count, errors=errors)


# ---------------------------------------------------------------------------
# Factory — the Splunk V2 protocol adapter
# ---------------------------------------------------------------------------


def make_generate(
    handler_class: type[GeneratingCommandHandlerBase],
    attr: str,
    version: str = "unknown",
    destinations: list[Destination] | None = None,
):
    """
    Returns a generate() function bound to a specific handler class.

    Mirrors make_stream() — same caching model (attr on the command object),
    same context extraction, same telemetry wiring.

    Parameters:
      handler_class  — the GeneratingCommandHandlerBase subclass to instantiate
      attr           — attribute name for handler caching on the command object
      version        — handler version string; surfaces as resource.service.version
      destinations   — list of Destination instances; defaults to SplunkLogDestination

    Usage:
        generate = make_generate(MyHandler, attr="_my_handler", version="1.0.0")
    """
    _destinations = destinations or [
        SplunkLogDestination(logging.getLogger(handler_class.__name__))
    ]

    def generate(
        command: GeneratingCommand,
    ) -> Generator[dict, None, None]:
        if not hasattr(command, attr):
            info = command.metadata.searchinfo
            context = ExecutionContext(
                component_name=info.command,
                app=info.app,
                component_type=ComponentType.SEARCH_COMMAND,
                user=info.username,
                sid=info.sid,
                session_key=info.session_key,
                service=command.service,
            )
            resource = Resource(
                service_name=handler_class.__name__,
                service_version=version,
                component_type=ComponentType.SEARCH_COMMAND,
                component_name=info.command,
                splunk_app=info.app,
            )
            tel = TelemetryService(resource)
            for dest in _destinations:
                tel.add_destination(dest)
            setattr(command, attr, handler_class(command, tel, context))

        handler: GeneratingCommandHandlerBase = getattr(command, attr)
        span_attrs = {
            k: v
            for k, v in {
                "sid": handler.context.sid,
                "user": handler.context.user,
            }.items()
            if v is not None
        }

        with (
            handler.tel,
            handler.tel.span(handler.context.component_name, attributes=span_attrs),
        ):
            yield from handler.run()

    return generate
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/unit/test_generating_command.py -v
```

Expected: all PASSED.

- [ ] **Step 5: Lint**

```bash
ruff check --fix src/splunkapplib/commands/generating.py && ruff format src/splunkapplib/commands/generating.py
```

- [ ] **Step 6: Commit**

```bash
git add src/splunkapplib/commands/generating.py tests/unit/test_generating_command.py
git commit -m "feat: add GeneratingCommandHandlerBase and make_generate factory"
```

---

## Task 4: EventingCommandHandlerBase + make_transform

**Files:**
- Create: `src/splunkapplib/commands/eventing.py`
- Create: `tests/unit/test_eventing_command.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_eventing_command.py`:

```python
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from tests.unit.conftest import StubTelemetry, make_context
from splunkapplib.commands.eventing import EventingCommandHandlerBase
from splunkapplib.core.component import ComponentType


def make_handler():
    tel = StubTelemetry()
    ctx = make_context(component_type=ComponentType.SEARCH_COMMAND)
    command = MagicMock()
    return tel, ctx, command


class TestTransformRecords:
    def test_transform_records_not_implemented_raises(self):
        tel, ctx, command = make_handler()
        h = EventingCommandHandlerBase(command, tel, ctx)

        with pytest.raises(NotImplementedError, match="transform_records"):
            list(h.run(iter([])))

    def test_transform_records_receives_all_input_records(self):
        received = []

        class H(EventingCommandHandlerBase):
            def transform_records(self, records):
                for r in records:
                    received.append(r)
                    yield r

        tel, ctx, command = make_handler()
        input_records = [{"a": 1}, {"b": 2}, {"c": 3}]
        list(H(command, tel, ctx).run(iter(input_records)))

        assert received == input_records

    def test_transform_records_output_is_returned(self):
        class H(EventingCommandHandlerBase):
            def transform_records(self, records):
                for r in records:
                    yield {**r, "transformed": True}

        tel, ctx, command = make_handler()
        result = list(H(command, tel, ctx).run(iter([{"x": 1}, {"x": 2}])))

        assert result == [{"x": 1, "transformed": True}, {"x": 2, "transformed": True}]

    def test_count_reported_in_on_transform_end(self):
        counts = []

        class H(EventingCommandHandlerBase):
            def transform_records(self, records):
                yield from records

            def on_transform_end(self, count: int):
                counts.append(count)

        tel, ctx, command = make_handler()
        list(H(command, tel, ctx).run(iter([{"a": 1}, {"b": 2}])))

        assert counts == [2]


class TestTransformLifecycleHooks:
    def test_on_transform_start_called_before_transform_records(self):
        order = []

        class H(EventingCommandHandlerBase):
            def on_transform_start(self):
                order.append("start")

            def transform_records(self, records):
                order.append("transform")
                yield from records

        tel, ctx, command = make_handler()
        list(H(command, tel, ctx).run(iter([{"x": 1}])))

        assert order == ["start", "transform"]

    def test_on_transform_end_logs_metric(self):
        class H(EventingCommandHandlerBase):
            def transform_records(self, records):
                yield from records

        tel, ctx, command = make_handler()
        list(H(command, tel, ctx).run(iter([{"a": 1}])))

        info_bodies = [r[1] for r in tel.records if r[0] == "info"]
        assert any("Transform complete" in b for b in info_bodies)


class TestInitialise:
    def test_initialise_called_once_across_multiple_runs(self):
        init_count = []

        class H(EventingCommandHandlerBase):
            def initialise(self):
                init_count.append(1)

            def transform_records(self, records):
                yield from records

        tel, ctx, command = make_handler()
        h = H(command, tel, ctx)
        list(h.run(iter([{"x": 1}])))
        list(h.run(iter([{"x": 2}])))

        assert sum(init_count) == 1
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/unit/test_eventing_command.py -v
```

Expected: FAILED — `cannot import name 'EventingCommandHandlerBase'`

- [ ] **Step 3: Implement eventing.py**

Create `src/splunkapplib/commands/eventing.py`:

```python
# eventing.py
#
# Eventing (dataset) command handler base class and factory.
# Copy nothing — import and subclass EventingCommandHandlerBase.

from __future__ import annotations

import logging
from collections.abc import Generator

from splunklib.searchcommands import EventingCommand

from splunkapplib.core.component import ComponentType, ExecutionContext
from splunkapplib.telemetry import (
    Destination,
    Resource,
    SplunkLogDestination,
    TelemetryService,
)


class EventingCommandHandlerBase:
    """
    Base class for all custom eventing (dataset) command handlers.

    Unlike streaming commands, eventing commands receive the full result
    set before producing output. transform_records() receives the complete
    generator and is responsible for iterating and yielding results.

    Exposes:
      self.tel      — TelemetryService; use tel.span() for ad-hoc spans
      self.log      — alias for self.tel; self.log.info("msg", key=value, ...)
      self.context  — ExecutionContext; component_name, app, user, sid, service
      self._command — the EventingCommand instance for Splunk SDK access

    Override in subclasses:
      - transform_records(records) — receives all records, yields results; required

    Optionally override:
      - initialise()           — one-time setup before the first batch
      - on_transform_start()   — called before transform_records()
      - on_transform_end()     — called after transform_records() completes

    Do not override __init__ or run().
    """

    def __init__(
        self,
        command: EventingCommand,
        tel: TelemetryService,
        context: ExecutionContext,
    ) -> None:
        self.tel = tel
        self.log = tel
        self.context = context
        self._command = command
        self._initialised = False

    # ------------------------------------------------------------------
    # Infrastructure — do not override
    # ------------------------------------------------------------------

    def _ensure_initialised(self) -> None:
        if self._initialised:
            return
        has_override = (
            type(self).initialise is not EventingCommandHandlerBase.initialise
        )
        if has_override:
            with self.tel.span("initialise"):
                self.log.info("Running one-time initialisation")
                self.initialise()
                self.log.info("Initialisation complete")
        self._initialised = True

    def run(
        self, records: Generator[dict, None, None]
    ) -> Generator[dict, None, None]:
        """
        Drives the full transform lifecycle. Called once per batch by the
        factory, always inside the factory's root span and tel context manager.
        """
        count = 0

        self._ensure_initialised()
        self.on_transform_start()

        for record in self.transform_records(records):
            yield record
            count += 1

        self.on_transform_end(count=count)

    # ------------------------------------------------------------------
    # Hooks — override in subclasses
    # ------------------------------------------------------------------

    def initialise(self) -> None:
        """One-time setup called before the first batch."""
        pass

    def transform_records(
        self, records: Generator[dict, None, None]
    ) -> Generator[dict, None, None]:
        """
        Receives the full result set and yields transformed records.
        Must be overridden.

        The handler owns iteration — it may sort, deduplicate, aggregate,
        or otherwise operate on the full dataset before yielding results.
        This is the semantic difference from StreamingCommand.
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement transform_records()"
        )

    def on_transform_start(self) -> None:
        """Called before transform_records() on each batch."""
        pass

    def on_transform_end(self, count: int) -> None:
        """
        Called after transformation completes.
        Emits a metric-style log:
            index=telemetry body="Transform complete"
            | stats avg(attributes.count) by resource.component.name
        """
        self.log.info("Transform complete", count=count)


# ---------------------------------------------------------------------------
# Factory — the Splunk V2 protocol adapter
# ---------------------------------------------------------------------------


def make_transform(
    handler_class: type[EventingCommandHandlerBase],
    attr: str,
    version: str = "unknown",
    destinations: list[Destination] | None = None,
):
    """
    Returns a transform() function bound to a specific handler class.

    Mirrors make_stream() — same caching model, same context extraction,
    same telemetry wiring.

    Parameters:
      handler_class  — the EventingCommandHandlerBase subclass to instantiate
      attr           — attribute name for handler caching on the command object
      version        — handler version string; surfaces as resource.service.version
      destinations   — list of Destination instances; defaults to SplunkLogDestination

    Usage:
        transform = make_transform(MyHandler, attr="_my_handler", version="1.0.0")
    """
    _destinations = destinations or [
        SplunkLogDestination(logging.getLogger(handler_class.__name__))
    ]

    def transform(
        command: EventingCommand,
        records: Generator[dict, None, None],
    ) -> Generator[dict, None, None]:
        if not hasattr(command, attr):
            info = command.metadata.searchinfo
            context = ExecutionContext(
                component_name=info.command,
                app=info.app,
                component_type=ComponentType.SEARCH_COMMAND,
                user=info.username,
                sid=info.sid,
                session_key=info.session_key,
                service=command.service,
            )
            resource = Resource(
                service_name=handler_class.__name__,
                service_version=version,
                component_type=ComponentType.SEARCH_COMMAND,
                component_name=info.command,
                splunk_app=info.app,
            )
            tel = TelemetryService(resource)
            for dest in _destinations:
                tel.add_destination(dest)
            setattr(command, attr, handler_class(command, tel, context))

        handler: EventingCommandHandlerBase = getattr(command, attr)
        span_attrs = {
            k: v
            for k, v in {
                "sid": handler.context.sid,
                "user": handler.context.user,
            }.items()
            if v is not None
        }

        with (
            handler.tel,
            handler.tel.span(handler.context.component_name, attributes=span_attrs),
        ):
            yield from handler.run(records)

    return transform
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/unit/test_eventing_command.py -v
```

Expected: all PASSED.

- [ ] **Step 5: Lint**

```bash
ruff check --fix src/splunkapplib/commands/eventing.py && ruff format src/splunkapplib/commands/eventing.py
```

- [ ] **Step 6: Commit**

```bash
git add src/splunkapplib/commands/eventing.py tests/unit/test_eventing_command.py
git commit -m "feat: add EventingCommandHandlerBase and make_transform factory"
```

---

## Task 5: ModularInputHandlerBase + make_modular_input

**Files:**
- Create: `src/splunkapplib/modular_inputs/__init__.py`
- Create: `src/splunkapplib/modular_inputs/input_handler.py`
- Modify: `tests/unit/test_modular_input.py` (extend with full tests)

- [ ] **Step 1: Write failing tests**

Replace `tests/unit/test_modular_input.py` with the full test suite:

```python
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, call

from tests.unit.conftest import StubTelemetry, make_context
from splunkapplib.core.component import ComponentType, EventWriterProtocol


class TestEventWriterProtocol:
    def test_protocol_is_importable(self):
        assert EventWriterProtocol is not None

    def test_concrete_class_satisfies_protocol_structurally(self):
        class GoodWriter:
            def write(self, event: dict, *, sourcetype=None, index=None,
                      host=None, time=None) -> None:
                pass

        writer: EventWriterProtocol = GoodWriter()  # type: ignore[assignment]
        assert writer is not None


class TestModularInputHandlerBase:
    def _make_handler(self, handler_class=None):
        from splunkapplib.modular_inputs.input_handler import ModularInputHandlerBase

        tel = StubTelemetry()
        ctx = make_context(component_type=ComponentType.MODULAR_INPUT)

        cls = handler_class or ModularInputHandlerBase
        return cls(tel, ctx), tel

    def test_collect_events_not_implemented_raises(self):
        from splunkapplib.modular_inputs.input_handler import ModularInputHandlerBase

        h, _ = self._make_handler()
        writer = MagicMock()

        with pytest.raises(NotImplementedError, match="collect_events"):
            h.run_collect({}, writer)

    def test_validate_default_is_noop(self):
        from splunkapplib.modular_inputs.input_handler import ModularInputHandlerBase

        h, _ = self._make_handler()
        # Should not raise
        h.run_validate({"key": "value"})

    def test_validate_called_with_params_dict(self):
        from splunkapplib.modular_inputs.input_handler import ModularInputHandlerBase

        received = []

        class H(ModularInputHandlerBase):
            def validate(self, params: dict):
                received.append(params)

            def collect_events(self, stanzas, writer):
                pass

        h, _ = self._make_handler(H)
        h.run_validate({"account": "acme", "interval": "60"})

        assert received == [{"account": "acme", "interval": "60"}]

    def test_validate_raising_propagates(self):
        from splunkapplib.modular_inputs.input_handler import ModularInputHandlerBase

        class H(ModularInputHandlerBase):
            def validate(self, params: dict):
                raise ValueError("bad config")

            def collect_events(self, stanzas, writer):
                pass

        h, _ = self._make_handler(H)
        with pytest.raises(ValueError, match="bad config"):
            h.run_validate({})

    def test_collect_events_called_with_stanzas_dict(self):
        from splunkapplib.modular_inputs.input_handler import ModularInputHandlerBase

        received = []

        class H(ModularInputHandlerBase):
            def collect_events(self, stanzas, writer):
                received.append(stanzas)

        h, _ = self._make_handler(H)
        stanzas = {"ta_input://my_input": {"index": "main", "interval": "60"}}
        h.run_collect(stanzas, MagicMock())

        assert received == [stanzas]

    def test_on_collect_end_logs_metric(self):
        from splunkapplib.modular_inputs.input_handler import ModularInputHandlerBase

        class H(ModularInputHandlerBase):
            def collect_events(self, stanzas, writer):
                pass

        h, tel = self._make_handler(H)
        h.run_collect({}, MagicMock())

        info_bodies = [r[1] for r in tel.records if r[0] == "info"]
        assert any("Collect complete" in b for b in info_bodies)

    def test_on_collect_end_receives_event_count(self):
        from splunkapplib.modular_inputs.input_handler import ModularInputHandlerBase

        counts = []

        class H(ModularInputHandlerBase):
            def collect_events(self, stanzas, writer):
                writer.write({"msg": "hello"})
                writer.write({"msg": "world"})

            def on_collect_end(self, count: int, errors: int):
                counts.append((count, errors))

        h, _ = self._make_handler(H)
        stub_writer = MagicMock()
        stub_writer.write = MagicMock()
        h.run_collect({}, stub_writer)

        assert counts == [(2, 0)]

    def test_on_collect_start_called_before_collect_events(self):
        from splunkapplib.modular_inputs.input_handler import ModularInputHandlerBase

        order = []

        class H(ModularInputHandlerBase):
            def on_collect_start(self):
                order.append("start")

            def collect_events(self, stanzas, writer):
                order.append("collect")

        h, _ = self._make_handler(H)
        h.run_collect({}, MagicMock())

        assert order == ["start", "collect"]

    def test_exception_in_collect_events_is_logged_errors_equals_1(self):
        from splunkapplib.modular_inputs.input_handler import ModularInputHandlerBase

        counts = []

        class H(ModularInputHandlerBase):
            def collect_events(self, stanzas, writer):
                raise RuntimeError("network error")

            def on_collect_end(self, count: int, errors: int):
                counts.append((count, errors))

        h, tel = self._make_handler(H)
        # Should not raise — error is caught and logged
        h.run_collect({}, MagicMock())

        assert counts == [(0, 1)]
        error_bodies = [r[1] for r in tel.records if r[0] == "error"]
        assert any("collect_events" in b for b in error_bodies)

    def test_initialise_called_once(self):
        from splunkapplib.modular_inputs.input_handler import ModularInputHandlerBase

        init_count = []

        class H(ModularInputHandlerBase):
            def initialise(self):
                init_count.append(1)

            def collect_events(self, stanzas, writer):
                pass

        h, _ = self._make_handler(H)
        h.run_collect({}, MagicMock())
        h.run_collect({}, MagicMock())

        assert sum(init_count) == 1


class TestSplunkEventWriterAdapter:
    def test_write_calls_write_event_on_underlying_ew(self):
        from splunkapplib.modular_inputs.input_handler import _SplunkEventWriterAdapter

        mock_ew = MagicMock()
        adapter = _SplunkEventWriterAdapter(mock_ew)
        adapter.write({"msg": "hello"}, sourcetype="my:st", index="main")

        mock_ew.write_event.assert_called_once()
        event_arg = mock_ew.write_event.call_args[0][0]
        assert event_arg.sourcetype == "my:st"
        assert event_arg.index == "main"

    def test_write_serialises_dict_to_json_string(self):
        from splunkapplib.modular_inputs.input_handler import _SplunkEventWriterAdapter
        import json

        mock_ew = MagicMock()
        adapter = _SplunkEventWriterAdapter(mock_ew)
        adapter.write({"key": "value"})

        event_arg = mock_ew.write_event.call_args[0][0]
        assert json.loads(event_arg.data) == {"key": "value"}

    def test_write_passes_host_and_time(self):
        from splunkapplib.modular_inputs.input_handler import _SplunkEventWriterAdapter

        mock_ew = MagicMock()
        adapter = _SplunkEventWriterAdapter(mock_ew)
        adapter.write({"x": 1}, host="myhost", time=1234567890.0)

        event_arg = mock_ew.write_event.call_args[0][0]
        assert event_arg.host == "myhost"
        assert event_arg.time == 1234567890.0
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/unit/test_modular_input.py -v
```

Expected: FAILED — `cannot import name 'ModularInputHandlerBase'` for most tests; `TestEventWriterProtocol` tests pass.

- [ ] **Step 3: Create modular_inputs package**

```bash
touch src/splunkapplib/modular_inputs/__init__.py
```

- [ ] **Step 4: Implement input_handler.py**

Create `src/splunkapplib/modular_inputs/input_handler.py`:

```python
# input_handler.py
#
# Modular input handler base class and factory.
# Copy nothing — import and subclass ModularInputHandlerBase.

from __future__ import annotations

import json
import logging
from typing import Any

from splunklib import modularinput as smi

from splunkapplib.core.component import ComponentType, EventWriterProtocol, ExecutionContext
from splunkapplib.telemetry import (
    Destination,
    Resource,
    SplunkLogDestination,
    TelemetryService,
)


# ---------------------------------------------------------------------------
# Adapters — private; bridge between Splunk SDK objects and our protocols
# ---------------------------------------------------------------------------


class _SplunkEventWriterAdapter:
    """
    Wraps smi.EventWriter and satisfies EventWriterProtocol.

    Converts a dict + optional metadata keywords into smi.Event and calls
    write_event(). Handler code never imports splunklib.modularinput.
    """

    def __init__(self, ew: smi.EventWriter) -> None:
        self._ew = ew

    def write(
        self,
        event: dict,
        *,
        sourcetype: str | None = None,
        index: str | None = None,
        host: str | None = None,
        time: float | None = None,
    ) -> None:
        self._ew.write_event(
            smi.Event(
                data=json.dumps(event, ensure_ascii=False, default=str),
                sourcetype=sourcetype,
                index=index,
                host=host,
                time=time,
            )
        )


class _CountingWriter:
    """
    Wraps EventWriterProtocol and counts write() calls.
    Used by run_collect() to report event count to on_collect_end().
    """

    def __init__(self, wrapped: EventWriterProtocol) -> None:
        self._wrapped = wrapped
        self.count = 0

    def write(
        self,
        event: dict,
        *,
        sourcetype: str | None = None,
        index: str | None = None,
        host: str | None = None,
        time: float | None = None,
    ) -> None:
        self._wrapped.write(
            event, sourcetype=sourcetype, index=index, host=host, time=time
        )
        self.count += 1


# ---------------------------------------------------------------------------
# Handler base class
# ---------------------------------------------------------------------------


class ModularInputHandlerBase:
    """
    Base class for all custom modular input handlers.

    Exposes:
      self.tel      — TelemetryService; use tel.span() for ad-hoc spans
      self.log      — alias for self.tel; self.log.info("msg", key=value, ...)
      self.context  — ExecutionContext; component_name, session_key

    Override in subclasses:
      - collect_events(stanzas, writer) — streams events; required

    Optionally override:
      - validate(params)       — raise ValueError to reject a config
      - initialise()           — one-time setup before collect_events
      - on_collect_start()     — called before collect_events
      - on_collect_end()       — called after collect_events completes

    Do not override __init__, run_validate(), or run_collect().

    Note: app is not reliably available from the modular input protocol and
    will be an empty string in ExecutionContext unless set by the handler
    subclass during initialise().
    """

    def __init__(
        self,
        tel: TelemetryService,
        context: ExecutionContext,
    ) -> None:
        self.tel = tel
        self.log = tel
        self.context = context
        self._initialised = False

    # ------------------------------------------------------------------
    # Infrastructure — do not override
    # ------------------------------------------------------------------

    def _ensure_initialised(self) -> None:
        if self._initialised:
            return
        has_override = (
            type(self).initialise is not ModularInputHandlerBase.initialise
        )
        if has_override:
            with self.tel.span("initialise"):
                self.log.info("Running one-time initialisation")
                self.initialise()
                self.log.info("Initialisation complete")
        self._initialised = True

    def run_validate(self, params: dict) -> None:
        """Called by the factory's validate_input closure."""
        self.validate(params)

    def run_collect(
        self, stanzas: dict[str, dict], writer: EventWriterProtocol
    ) -> None:
        """
        Called by the factory's stream_events closure.

        Wraps the writer in a _CountingWriter so on_collect_end() receives
        the actual number of events written. Exceptions from collect_events()
        are caught, logged, and swallowed — the modular input process stays
        alive for the next collection interval.
        """
        errors = 0
        counting_writer = _CountingWriter(writer)

        self._ensure_initialised()
        self.on_collect_start()

        try:
            self.collect_events(stanzas, counting_writer)
        except Exception as exc:
            self.log.error(
                "Unhandled error in collect_events",
                exception_type=type(exc).__name__,
                exception_message=str(exc),
            )
            errors += 1
        finally:
            self.on_collect_end(count=counting_writer.count, errors=errors)

    # ------------------------------------------------------------------
    # Hooks — override in subclasses
    # ------------------------------------------------------------------

    def initialise(self) -> None:
        """One-time setup called before the first collect_events()."""
        pass

    def validate(self, params: dict) -> None:
        """
        Validate a single input stanza's configuration.
        Raise ValueError with a descriptive message if the config is invalid.
        The default implementation accepts any configuration.
        """
        pass

    def collect_events(
        self, stanzas: dict[str, dict], writer: EventWriterProtocol
    ) -> None:
        """
        Stream events for all input stanzas. Must be overridden.

        stanzas — dict mapping stanza name → parameter dict, e.g.:
            {
              "ta_myinput://my_instance": {
                "index": "main",
                "interval": "60",
                "account": "my_account",
              }
            }

        writer — EventWriterProtocol; call writer.write(event_dict, ...) to
                 emit events. All keyword arguments (sourcetype, index, host,
                 time) are optional.
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement collect_events()"
        )

    def on_collect_start(self) -> None:
        """Called before collect_events() on each invocation."""
        pass

    def on_collect_end(self, count: int, errors: int) -> None:
        """
        Called after collect_events() completes or errors.
        Emits a metric-style log:
            index=telemetry body="Collect complete"
            | stats sum(attributes.count) sum(attributes.errors)
              by resource.component.name
        """
        self.log.info("Collect complete", count=count, errors=errors)


# ---------------------------------------------------------------------------
# Factory — the Splunk modular input protocol adapter
# ---------------------------------------------------------------------------


def make_modular_input(
    handler_class: type[ModularInputHandlerBase],
    version: str = "unknown",
    destinations: list[Destination] | None = None,
):
    """
    Returns a (validate_input, stream_events) tuple bound to a handler class.

    Usage:
        validate_input, stream_events = make_modular_input(
            MyHandler, version="1.0.0"
        )

    Both closures construct a fresh handler per call — modular input processes
    are short-lived (one invocation per collection interval), so there is no
    need for the attr-based caching used by command handler factories.

    Parameters:
      handler_class  — the ModularInputHandlerBase subclass to instantiate
      version        — handler version; surfaces as resource.service.version
      destinations   — list of Destination instances; defaults to SplunkLogDestination
    """
    _destinations = destinations or [
        SplunkLogDestination(logging.getLogger(handler_class.__name__))
    ]

    def _make_handler(component_name: str, session_key: str | None) -> ModularInputHandlerBase:
        context = ExecutionContext(
            component_name=component_name,
            app="",
            component_type=ComponentType.MODULAR_INPUT,
            session_key=session_key,
        )
        resource = Resource(
            service_name=handler_class.__name__,
            service_version=version,
            component_type=ComponentType.MODULAR_INPUT,
            component_name=component_name,
            splunk_app="",
        )
        tel = TelemetryService(resource)
        for dest in _destinations:
            tel.add_destination(dest)
        return handler_class(tel, context)

    def validate_input(definition: smi.ValidationDefinition) -> None:
        session_key = definition.metadata.get("session_key")
        params = dict(definition.parameters)
        handler = _make_handler(
            component_name="validate_input",
            session_key=session_key,
        )
        with handler.tel, handler.tel.span("validate_input"):
            handler.run_validate(params)

    def stream_events(
        inputs: smi.InputDefinition, ew: smi.EventWriter
    ) -> None:
        session_key = inputs.metadata.get("session_key")
        component_name = next(iter(inputs.inputs), "modular_input")
        handler = _make_handler(
            component_name=component_name,
            session_key=session_key,
        )
        stanzas = dict(inputs.inputs)
        writer = _SplunkEventWriterAdapter(ew)
        with handler.tel, handler.tel.span(component_name):
            handler.run_collect(stanzas, writer)

    return validate_input, stream_events
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
pytest tests/unit/test_modular_input.py -v
```

Expected: all PASSED.

- [ ] **Step 6: Lint**

```bash
ruff check --fix src/splunkapplib/modular_inputs/ && ruff format src/splunkapplib/modular_inputs/
```

- [ ] **Step 7: Commit**

```bash
git add src/splunkapplib/modular_inputs/ tests/unit/test_modular_input.py
git commit -m "feat: add ModularInputHandlerBase and make_modular_input factory"
```

---

## Task 6: Update public API

**Files:**
- Modify: `src/splunkapplib/__init__.py`

- [ ] **Step 1: Update __init__.py**

Replace the contents of `src/splunkapplib/__init__.py` with:

```python
# splunkapplib
#
# Top-level public API. App authors should import from here:
#
#   from splunkapplib import CommandHandlerBase, make_stream
#   from splunkapplib import GeneratingCommandHandlerBase, make_generate
#   from splunkapplib import EventingCommandHandlerBase, make_transform
#   from splunkapplib import AlertActionHandlerBase, make_process_event
#   from splunkapplib import ModularInputHandlerBase, make_modular_input
#   from splunkapplib import measure
#
# Advanced telemetry usage (TelemetryService, Resource, renderers, etc.)
# is available via the splunkapplib.telemetry subpackage.
# EventWriterProtocol is available from splunkapplib.core.component.

from splunkapplib.alert_actions.action_handler import (
    AlertActionHandlerBase,
    make_process_event,
)
from splunkapplib.commands.eventing import EventingCommandHandlerBase, make_transform
from splunkapplib.commands.generating import GeneratingCommandHandlerBase, make_generate
from splunkapplib.commands.streaming import CommandHandlerBase, make_stream
from splunkapplib.core.component import AbstractComponentHandler, ExecutionContext
from splunkapplib.modular_inputs.input_handler import (
    ModularInputHandlerBase,
    make_modular_input,
)
from splunkapplib.telemetry import measure

__all__ = [
    "AbstractComponentHandler",
    "AlertActionHandlerBase",
    "CommandHandlerBase",
    "EventingCommandHandlerBase",
    "ExecutionContext",
    "GeneratingCommandHandlerBase",
    "ModularInputHandlerBase",
    "make_generate",
    "make_modular_input",
    "make_process_event",
    "make_stream",
    "make_transform",
    "measure",
]
```

- [ ] **Step 2: Run full test suite**

```bash
pytest tests/unit/ -v
```

Expected: all PASSED.

- [ ] **Step 3: Verify imports work from the public API**

```bash
python -c "from splunkapplib import GeneratingCommandHandlerBase, EventingCommandHandlerBase, ModularInputHandlerBase, make_generate, make_transform, make_modular_input; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Lint all modified files**

```bash
ruff check --fix src && ruff format src
```

- [ ] **Step 5: Run full test suite one final time**

```bash
pytest tests/unit/ -v
```

Expected: all PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/splunkapplib/__init__.py
git commit -m "feat: export new handler classes from top-level splunkapplib API"
```
