# Component Handlers: Generating, Eventing, Modular Input — Design Spec

Date: 2026-04-01

## Overview

Implement the three remaining splunkapplib component handler types:
- **Generating command** (`GeneratingCommand` / `generate()` protocol)
- **Eventing/dataset command** (`EventingCommand` / `transform()` protocol)
- **Modular input** (`smi.Script` / `validate_input()` + `stream_events()` protocol)

Also fix a consistency issue in the existing **alert action handler**: rename lifecycle methods to match the `{action}_noun` / `on_{action}_start` / `on_{action}_end` pattern used by all other handlers.

## Architecture

Follows the existing two-layer pattern:

**Layer 1 — Pure Python handler base** (no Splunk imports): defines lifecycle hooks subclasses override.

**Layer 2 — Factory function** (the only code touching Splunk SDK objects): extracts `ExecutionContext`, builds `Resource` + `TelemetryService`, injects both into the handler, and returns a closure with the exact signature the UCC-generated wrapper expects.

## New Files

```
src/splunkapplib/
  commands/
    generating.py        # GeneratingCommandHandlerBase + make_generate
    eventing.py          # EventingCommandHandlerBase + make_transform
  modular_inputs/
    __init__.py
    input_handler.py     # ModularInputHandlerBase + make_modular_input
                         # also contains _SplunkEventWriterAdapter (private)
```

`EventWriterProtocol` is added to `core/component.py` alongside `TelemetryProtocol` — it is a pure-Python Protocol (no Splunk imports), so it belongs with the other seam definitions.

## Handler Interfaces

Lifecycle method naming is consistent across all handler types:

| Handler | Primary method | Start hook | End hook |
|---|---|---|---|
| Streaming | `process_record(record)` | `on_batch_start()` | `on_batch_end(processed, errors)` |
| Generating | `generate_records()` | `on_generate_start()` | `on_generate_end(count, errors)` |
| Eventing | `transform_records(records)` | `on_transform_start()` | `on_transform_end(count)` |
| Alert action | `process_alert()` | `on_alert_start()` | `on_alert_end(success)` |
| Modular input | `collect_events(stanzas, writer)` | `on_collect_start()` | `on_collect_end(count, errors)` |

### GeneratingCommandHandlerBase (`commands/generating.py`)

```python
class GeneratingCommandHandlerBase:
    # infrastructure (do not override)
    def __init__(self, command, tel, context): ...
    def _ensure_initialised(self): ...
    def run(self) -> Generator[dict, None, None]: ...

    # override in subclasses
    def generate_records(self) -> Generator[dict, None, None]: ...  # required
    def initialise(self) -> None: ...                               # optional
    def on_generate_start(self) -> None: ...                        # optional
    def on_generate_end(self, count: int, errors: int) -> None: ... # optional, logs metric
```

`run()` calls `_ensure_initialised()`, then `on_generate_start()`, then wraps `generate_records()` in a try/except per yielded record (error → log + skip, consistent with streaming), then calls `on_generate_end(count, errors)`.

Factory: `make_generate(handler_class, attr, version, destinations)` → `generate(command) -> Generator[dict]`.
Caches handler on `command` via `attr` (same V2 chunked process-reuse model as `make_stream`).

### EventingCommandHandlerBase (`commands/eventing.py`)

```python
class EventingCommandHandlerBase:
    # infrastructure (do not override)
    def __init__(self, command, tel, context): ...
    def _ensure_initialised(self): ...
    def run(self, records: Generator[dict]) -> Generator[dict]: ...

    # override in subclasses
    def transform_records(self, records: Generator[dict]) -> Generator[dict]: ...  # required
    def initialise(self) -> None: ...                                               # optional
    def on_transform_start(self) -> None: ...                                       # optional
    def on_transform_end(self, count: int) -> None: ...                             # optional, logs metric
```

`run()` calls `_ensure_initialised()`, `on_transform_start()`, delegates fully to `transform_records(records)` (the handler owns iteration — it may sort, dedup, aggregate), counts yielded records, then calls `on_transform_end(count)`.

Factory: `make_transform(handler_class, attr, version, destinations)` → `transform(command, records) -> Generator[dict]`.
Caches handler on `command` via `attr`.

### ModularInputHandlerBase (`modular_inputs/input_handler.py`)

```python
class EventWriterProtocol(Protocol):  # in core/component.py
    def write(
        self,
        event: dict,
        *,
        sourcetype: str | None = None,
        index: str | None = None,
        host: str | None = None,
        time: float | None = None,
    ) -> None: ...

class ModularInputHandlerBase:
    # infrastructure (do not override)
    def __init__(self, tel, context): ...
    def _ensure_initialised(self): ...
    def run_validate(self, params: dict) -> None: ...
    def run_collect(self, stanzas: dict[str, dict], writer: EventWriterProtocol) -> None: ...

    # override in subclasses
    def validate(self, params: dict) -> None: ...                          # optional, raise ValueError if invalid
    def collect_events(self, stanzas: dict[str, dict],
                       writer: EventWriterProtocol) -> None: ...           # required
    def initialise(self) -> None: ...                                      # optional
    def on_collect_start(self) -> None: ...                                # optional
    def on_collect_end(self, count: int, errors: int) -> None: ...        # optional, logs metric
```

`_SplunkEventWriterAdapter` (private, in `input_handler.py`) wraps `smi.EventWriter`, converts `dict` + keyword metadata fields into `smi.Event`, and satisfies `EventWriterProtocol`. Handler code never imports `splunklib.modularinput`.

Factory: `make_modular_input(handler_class, version, destinations)` → `(validate_input, stream_events)` tuple.

```python
validate_input, stream_events = make_modular_input(MyHandler, version="1.0.0")
```

- `validate_input(definition: smi.ValidationDefinition)` — extracts `definition.parameters` as a plain dict, constructs a fresh handler, calls `handler.run_validate(params)`. No caching — validation is a lightweight separate process.
- `stream_events(inputs: smi.InputDefinition, ew: smi.EventWriter)` — extracts `inputs.inputs` as `dict[str, dict]`, wraps `ew` in `_SplunkEventWriterAdapter`, constructs a fresh handler, calls `handler.run_collect(stanzas, writer)`.

No `attr`/caching: modular input processes are short-lived (one invocation per collection interval). A fresh handler per call means `initialise()` runs exactly once per process naturally, without needing the attr-based guard used by command handlers.

## Alert Action Handler Changes

Rename lifecycle methods in `alert_actions/action_handler.py` for consistency:

| Old name | New name |
|---|---|
| `execute(*args, **kwargs)` | `process_alert()` |
| `before_execute()` | `on_alert_start()` |
| `after_execute(success)` | `on_alert_end(success)` |

`process_alert()` drops `*args, **kwargs` — those were defensive passthrough from the UCC wrapper but carry no meaningful data; everything is accessed via `self._action`.

## EventWriterProtocol Placement

`EventWriterProtocol` goes in `core/component.py` alongside `TelemetryProtocol`. Rationale: protocols define the shape of seams — they belong in `core/` with the other seam definitions. The concrete adapter (`_SplunkEventWriterAdapter`) that wraps `smi.EventWriter` lives in `modular_inputs/input_handler.py` where the Splunk knowledge belongs.

## Public API (`__init__.py`)

Add to `__all__`:

```python
from splunkapplib.commands.generating import GeneratingCommandHandlerBase, make_generate
from splunkapplib.commands.eventing import EventingCommandHandlerBase, make_transform
from splunkapplib.modular_inputs.input_handler import ModularInputHandlerBase, make_modular_input
```

`EventWriterProtocol` is exported from `core/component.py` but not necessarily from the top-level `__init__` unless handlers need to type-annotate against it in their own code (they can import from `splunkapplib.core.component`).

## What Is Not In Scope

- Unit tests (noted in CLAUDE.md as not yet built)
- REST handler (`ComponentType.REST_HANDLER`)
- Full OTel export / HEC destination wiring
