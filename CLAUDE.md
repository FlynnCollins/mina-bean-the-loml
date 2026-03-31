# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Lint
ruff check src

# Format
ruff format src

# Lint + format with auto-fix
ruff check --fix src && ruff format src

# Run tests
pytest

# Build package
hatch build

# Install in dev mode
pip install -e ".[dev]"
```

Python target is 3.9+. Ruff line length is 88.

## Architecture

This library provides an **adapter layer between Splunk's scripted component protocols and pure Python handler classes**. The design enforces that business logic never imports Splunk SDK directly.

### Two-Layer Pattern

**Layer 1 — Pure Python core (`core/component.py`):**
- `AbstractComponentHandler`: root ABC for all handlers; receives `TelemetryProtocol` and `ExecutionContext` at construction
- `ExecutionContext`: normalized, protocol-agnostic snapshot of runtime environment (component_name, app, component_type, user, sid, session_key, service)
- No Splunk imports — fully unit-testable

**Layer 2 — Protocol adapter (component modules):**
- `CommandHandlerBase` (`commands/streaming.py`) and `AlertActionHandlerBase` (`alert_actions/action_handler.py`) extend the core base with component-specific lifecycle methods
- Factory functions (`make_stream`, `make_process_event`) are the **only** code that touches Splunk SDK; they extract context, build `Resource` + `TelemetryService`, inject into a handler instance, and return a function wired to the UCC-generated entry point

### Factory Pattern

UCC framework generates boilerplate that calls specific methods on Splunk base classes. The factories return closures that satisfy those contracts:

```python
# In UCC-generated commands/my_command.py
from splunkapplib import make_stream
from .handler import MyHandler

stream = make_stream(MyHandler, attr="stream", version="1.0.0", destinations=[...])
```

For alert actions, `make_process_event` similarly returns a `process_event()` function bound to the handler.

Streaming command handlers are **cached per search** (keyed by `sid`) so `initialise()` is called exactly once. Alert action handlers are **fresh per invocation** (ephemeral process model).

### Telemetry System (`telemetry/`)

OTel-shaped distributed tracing + structured logging, entirely internal — no OTel SDK dependency. Four files:

| File | Contents |
|------|----------|
| `_internal.py` | Private: `_active_service` / `_active_span` ContextVars, `_fallback` logger, ID/timestamp helpers. No intra-package runtime deps. |
| `records.py` | Data types only: `Resource`, `SpanContext`, `MessageRecord`, `SpanRecord`, `TelemetryEvent` |
| `service.py` | All active machinery: `Renderer` / `SplunkLogRenderer` / `JSONRenderer`, `Destination` / `SplunkLogDestination`, `TelemetryService`, `@measure` |
| `__init__.py` | Public re-exports (same surface as before) |

**Key design points:**
- `TelemetryService` is the central object; injected into every handler by the factory. App code calls `self.tel.info(...)`, `self.tel.span(name)`, etc.
- `MessageRecord` has `severity`; `SpanRecord` does not — spans have `span_status` ("OK"/"ERROR"), not severity
- `@measure` discovers the active service via `ContextVar[_active_service]`; safe no-op if no service is active (unit tests work without setup)
- `_active_span` ContextVar enables nested spans and ensures messages emitted outside any span are caught and routed to `_fallback`

**Record flow:**
```
self.tel.info(...) or @measure
  → MessageRecord/SpanRecord buffered in TelemetryService
  → flush() on context exit
  → Destination.emit(records) for each destination
  → Renderer.render(record) → string
  → SplunkLogDestination writes to Python logger → Splunk _internal
```

**Querying in Splunk:**
- `SplunkLogRenderer` produces flat `key=value` format: `index=_internal sourcetype=splunk_python | where isnotnull(trace_id)`
- `JSONRenderer` produces hierarchical JSON for HEC ingestion

### What's Not Built Yet

- Modular input handler (`ComponentType.MODULAR_INPUT`) — follow the same two-layer pattern as `CommandHandlerBase`
- REST handler (`ComponentType.REST_HANDLER`)
- Unit tests
- Full public API surface in top-level `__init__.py`

When adding a new component type, the pattern is: abstract lifecycle base in the component module + factory function that extracts context from the Splunk protocol and injects into the handler.
