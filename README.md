# UCC-Generated Entry Points — Reference Examples

These files are exact copies of the boilerplate Python scripts that
`ucc-gen build` produces from `globalConfig.json`. They are here as static
reference material showing the calling conventions that splunkapplib must
satisfy — not as code to run or modify.

## What Each File Shows

| File | UCC component | Key call into helper |
|---|---|---|
| `modular_input_wrapper.py` | Modular input (`smi.Script` subclass) | `validate_input(definition)`, `stream_events(inputs, ew)` |
| `alert_action_entry_point.py` | Alert action (`ModularAlertBase` subclass) | `ta_template_alert_helper.process_event(self, ...)` |
| `streaming_command_wrapper.py` | Streaming command (`StreamingCommand` subclass) | `stream(self, events)` from logic file |
| `generating_command_wrapper.py` | Generating command (`GeneratingCommand` subclass) | `generate(self)` from logic file |
| `dataset_command_wrapper.py` | Dataset processing command (`EventingCommand` subclass) | `transform(self, events)` from logic file |

## What splunkapplib Replaces

In a real add-on using splunkapplib, the helper functions imported by these
wrappers are produced by the factory functions rather than written by hand:

```python
# In a UCC-generated streaming command, instead of a hand-written stream():
from splunkapplib import make_stream
from .handler import MyHandler

stream = make_stream(MyHandler, attr="_handler", version="1.0.0")
```

The factory returns a closure with the same signature the wrapper expects,
extracting `ExecutionContext` and wiring up `TelemetryService` before
delegating to the handler.

## Regenerating

These files were produced from the template app package at
`tests/fixtures/ta_sad_ucc_package_template/`. To regenerate after a UCC
version upgrade or `globalConfig.json` change:

```bash
cd tests/fixtures/ta_sad_ucc_package_template
hatch run ucc-gen build --source package --ta-version 0.0.1
```

Then copy the updated entry points from `output/ta_sad_ucc_package_template/bin/`
back into this directory.
