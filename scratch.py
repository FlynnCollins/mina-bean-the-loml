from contextvars import ContextVar
from contextlib import contextmanager
from dataclasses import dataclass, field
import uuid
import time

# ── Declared once at module level ──────────────────────────────────────────
_current_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)
_current_span_id: ContextVar[str | None] = ContextVar("span_id", default=None)


@dataclass
class SpanContext:
    trace_id: str
    span_id: str
    parent_span_id: str | None


def get_current_span_context() -> SpanContext | None:
    trace_id = _current_trace_id.get()
    span_id = _current_span_id.get()
    if trace_id and span_id:
        return SpanContext(trace_id=trace_id, span_id=span_id, parent_span_id=None)
    return None


def _emit_span(*args):
    print(args)


@contextmanager
def start_span(name: str, trace_id: str | None = None):
    """Enter a span, propagating or creating the trace_id."""
    parent_span_id = _current_span_id.get()

    # If no trace_id in context and none provided, start a new trace
    resolved_trace_id = trace_id or _current_trace_id.get() or str(uuid.uuid4())
    span_id = str(uuid.uuid4())

    # .set() returns a token so we can restore on exit
    tok_trace = _current_trace_id.set(resolved_trace_id)
    tok_span = _current_span_id.set(span_id)

    start = time.monotonic()
    try:
        yield SpanContext(
            trace_id=resolved_trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
        )
    finally:
        duration_ms = (time.monotonic() - start) * 1000
        # Emit your span record here (HEC, _internal, etc.)
        _emit_span(name, resolved_trace_id, span_id, parent_span_id, duration_ms)
        # Restore — not just clear, because we might be nested
        _current_span_id.reset(tok_span)
        _current_trace_id.reset(tok_trace)


def main():
    with start_span("command.execute") as root:
        context = get_current_span_context()
        print("Root Context:")
        print(context)
        print("\n")
        with start_span("db.query") as child:
            context = get_current_span_context()
            print("Child Context:")
            print(context)


if __name__ == "__main__":
    main()
