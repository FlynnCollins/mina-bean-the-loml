# Building Splunk Add-ons with the UCC Framework

A practical reference for using `ucc-gen` to create, build, and package Splunk Technology Add-ons (TAs)
that include modular inputs, alert actions, and custom search commands.

> **Documentation sources**: This guide is derived from the
> [UCC Framework documentation](https://splunk.github.io/addonfactory-ucc-generator/),
> [Splunk's UCC blog post](https://www.splunk.com/en_us/blog/customers/managing-splunk-add-ons-with-ucc-framework.html),
> and the [Splunk UCC documentation on help.splunk.com](https://help.splunk.com/en/data-management/integrate-data-with-add-ons/universal-configuration-console-ucc/universal-configuration-console).

---

## What is UCC?

The Universal Configuration Console (UCC) is a Splunk-supported developer toolkit that simplifies
Technology Add-on development. It auto-generates UI components, REST handlers, modular input
scaffolding, `.conf` files, metadata, monitoring dashboards, and alert action boilerplate from a
single declarative configuration file — `globalConfig.json`.

UCC-based add-ons are powered by two key libraries:

- **solnlib** — utility functions and classes for add-on development
  ([GitHub](https://github.com/splunk/addonfactory-solutions-library-python))
- **splunktaucclib** — the UCC runtime library
  ([GitHub](https://github.com/splunk/addonfactory-ucc-library))

---

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install splunk-add-on-ucc-framework
```

---

## The Three Core Commands

UCC's workflow consists of three commands: **init**, **build**, and **package**.

### 1. `ucc-gen init` — Initialise a new add-on

Creates the initial project structure including a `package/` directory and a starter
`globalConfig.json`.

```bash
ucc-gen init \
  --addon-name "my_ta_example" \
  --addon-display-name "My TA Example" \
  --addon-input-name my_data_input
```

This produces:

```
my_ta_example/
├── globalConfig.json
├── app.manifest
└── package/
    ├── bin/
    ├── default/
    └── ...
```

The `globalConfig.json` file is the central declaration that drives code generation.
The `app.manifest` file contains add-on metadata (name, version, author, description)
that UCC uses to populate `app.conf`.

### 2. `ucc-gen build` — Generate the add-on

Reads `globalConfig.json` and produces the full add-on file structure in an `output/` directory.

```bash
ucc-gen build \
  --source my_ta_example/package \
  --ta-version 1.0.0
```

Alternatively, if your project uses Git tags for versioning, the `--ta-version` flag can be
omitted and UCC will derive the version from Git.

What `ucc-gen build` generates:

- UI components (stored in `appserver/`)
- Python REST handlers (stored in `bin/`)
- Modular input scripts (stored in `bin/`)
- `.conf` files (`app.conf`, `inputs.conf`, `restmap.conf`, `web.conf`, etc.)
- Metadata files (stored in `metadata/`)
- Python requirements installed into `lib/`
- OpenAPI description document (`appserver/static/openapi.json`)
- Alert action files (if alerts are defined in `globalConfig.json`)
- Monitoring dashboard (if configured)

If you have custom modular input code in `package/bin/`, `ucc-gen build` will use your
files instead of generating new ones. As the UCC quickstart documentation notes: after
you update the modular input code, running `ucc-gen` again will use the updated modular
inputs from `package/bin/` instead of generating new ones.

### 3. `ucc-gen package` — Create the distributable archive

Packages the built output into a `.tar.gz` file suitable for installation on a Splunk
instance.

```bash
ucc-gen package --path output/my_ta_example
```

The archive is created at the same level as your `globalConfig.json` file.

---

## Project File Structure Before `ucc-gen build`

When building an add-on that includes a modular input, an alert action, and a custom
search command, your source tree under `package/` needs to contain specific files that
UCC will copy through or merge during the build. The overall layout looks like this:

```
my_ta_example/
├── globalConfig.json              # Central UCC declaration (inputs, alerts, commands, config)
├── app.manifest                   # Add-on metadata
│
└── package/
    ├── bin/
    │   ├── my_input_helper.py     # Modular input helper module (validate_input + stream_events)
    │   ├── my_alert_helper.py     # Alert action custom script (process_event)
    │   └── my_command_logic.py    # Custom search command logic (generate/stream/transform function)
    │
    ├── default/                   # Optional — UCC generates commands.conf from globalConfig
    │
    ├── lib/                       # Third-party Python dependencies (populated by build or manually)
    │
    ├── appserver/
    │   └── static/
    │       └── alerticon.png      # Optional custom alert action icon
    │
    └── README/                    # Optional spec files
```

Key points about what goes where:

- **Modular inputs** are declared in `globalConfig.json` under `pages.inputs.services`.
  UCC auto-generates the input script scaffolding. You provide a helper module in
  `package/bin/` if you want to customise the `validate_input` and `stream_events` logic.
- **Alert actions** are declared in `globalConfig.json` under `alerts`. UCC auto-generates
  the alert action script and HTML. You provide a custom script in `package/bin/` via the
  `customScript` parameter if you want to supply your own `process_event()` logic.
- **Custom search commands** are declared in `globalConfig.json` under
  `customSearchCommand` (at the same indent level as `meta` and `pages`). UCC
  auto-generates the wrapper Python script and `commands.conf` stanza. You provide
  a logic file in `package/bin/` containing the appropriate function for your command
  type (`generate`, `stream`, or `transform`). The `fileName` property in
  `globalConfig.json` must reference this logic file, and the build will fail if it
  does not exist.

---

## Defining Modular Inputs in `globalConfig.json`

Modular inputs are defined under `pages.inputs.services` in `globalConfig.json`. Each
service entry becomes a modular input type that users can configure through the add-on's
Inputs page.

### Minimal modular input example

```json
{
  "pages": {
    "configuration": {
      "title": "Configuration",
      "tabs": [
        {
          "name": "logging",
          "title": "Logging",
          "entity": [
            {
              "type": "singleSelect",
              "label": "Log Level",
              "field": "loglevel",
              "defaultValue": "INFO",
              "options": {
                "disableSearch": true,
                "autoCompleteFields": [
                  { "value": "DEBUG", "label": "DEBUG" },
                  { "value": "INFO",  "label": "INFO" },
                  { "value": "WARN",  "label": "WARN" },
                  { "value": "ERROR", "label": "ERROR" }
                ]
              }
            }
          ]
        }
      ]
    },
    "inputs": {
      "title": "Inputs",
      "description": "Manage your data inputs",
      "services": [
        {
          "name": "my_data_input",
          "title": "My Data Input",
          "entity": [
            {
              "type": "text",
              "label": "Name",
              "field": "name",
              "help": "A unique name for the data input.",
              "required": true,
              "validators": [
                {
                  "type": "regex",
                  "errorMsg": "Input Name must begin with a letter and consist exclusively of alphanumeric characters and underscores.",
                  "pattern": "^[a-zA-Z]\\w*$"
                },
                {
                  "type": "string",
                  "errorMsg": "Length of input name should be between 1 and 100",
                  "minLength": 1,
                  "maxLength": 100
                }
              ]
            },
            {
              "type": "text",
              "label": "Interval",
              "field": "interval",
              "help": "Time interval of the data input, in seconds.",
              "required": true,
              "defaultValue": "300",
              "validators": [
                {
                  "type": "regex",
                  "errorMsg": "Interval must be an integer.",
                  "pattern": "^\\-[1-9]\\d*$|^\\d*$"
                }
              ]
            },
            {
              "type": "text",
              "label": "API Endpoint",
              "field": "api_endpoint",
              "help": "The URL of the API to collect data from.",
              "required": true
            },
            {
              "type": "singleSelect",
              "label": "Index",
              "field": "index",
              "defaultValue": "default",
              "options": {
                "endpointUrl": "data/indexes",
                "denyList": "^_.*$",
                "createSearchChoice": true
              },
              "required": true
            }
          ],
          "inputHelperModule": "my_input_helper"
        }
      ],
      "table": {
        "actions": ["edit", "delete", "clone"],
        "header": [
          { "label": "Name", "field": "name" },
          { "label": "Interval", "field": "interval" },
          { "label": "Index", "field": "index" },
          { "label": "Status", "field": "disabled" }
        ]
      }
    }
  },
  "meta": {
    "name": "my_ta_example",
    "restRoot": "my_ta_example",
    "version": "1.0.0",
    "displayName": "My TA Example",
    "schemaVersion": "0.0.3"
  }
}
```

### The input helper module

When `inputHelperModule` is specified for a service, UCC expects a Python file with that
name in `package/bin/`. This module must contain two functions: `validate_input` and
`stream_events`. UCC regenerates the input wrapper script on every build to keep arguments
and options synchronised with `globalConfig.json`, but it preserves your helper module.

**`package/bin/my_input_helper.py`**:

```python
from splunklib import modularinput as smi


def validate_input(definition: smi.ValidationDefinition):
    """Called when the user saves input configuration.
    Raise an exception to reject the configuration."""
    api_endpoint = definition.parameters.get("api_endpoint")
    if not api_endpoint.startswith("https://"):
        raise ValueError("API endpoint must use HTTPS")


def stream_events(inputs: smi.InputDefinition, event_writer: smi.EventWriter):
    """Called at each collection interval. Write events to Splunk."""
    for input_name, input_item in inputs.inputs.items():
        # Your data collection logic here
        event = smi.Event(
            data='{"status": "ok"}',
            sourcetype="my_ta_example:data",
            source=input_item.get("api_endpoint"),
            index=input_item.get("index", "default"),
        )
        event_writer.write_event(event)
```

If you omit the `inputHelperModule` property, UCC generates a boilerplate modular input
script directly. You can then copy the auto-generated script from the build output back
into `package/bin/` and modify it — subsequent builds will use your version.

### What UCC generates from the input definition

From the `services` entry above, `ucc-gen build` produces:

- `default/inputs.conf` — with default stanzas and `python.version = python3`
- `README/inputs.conf.spec` — with documented parameters
- `bin/<addon_name>_rh_my_data_input.py` — the REST handler for CRUD operations
- `bin/my_data_input.py` — the modular input wrapper script (or uses your helper module)

---

## Defining Alert Actions in `globalConfig.json`

Alert actions are defined under the top-level `alerts` key in `globalConfig.json`.
Each alert action appears in the "Trigger Actions" section when users create alerts
in Splunk.

### Alert action example

Add this alongside the `pages` and `meta` keys in your `globalConfig.json`:

```json
{
  "alerts": [
    {
      "name": "send_to_service",
      "label": "Send to External Service",
      "description": "Forwards alert results to an external API endpoint.",
      "iconFileName": "alerticon.png",
      "customScript": "my_alert_helper.py",
      "entity": [
        {
          "type": "text",
          "label": "Webhook URL",
          "field": "webhook_url",
          "help": "The URL to send alert data to.",
          "required": true
        },
        {
          "type": "singleSelect",
          "label": "Severity",
          "field": "severity",
          "required": true,
          "defaultValue": "medium",
          "options": {
            "items": [
              { "value": "low",      "label": "Low" },
              { "value": "medium",   "label": "Medium" },
              { "value": "high",     "label": "High" },
              { "value": "critical", "label": "Critical" }
            ]
          }
        },
        {
          "type": "checkbox",
          "label": "Include Raw Events",
          "field": "include_raw",
          "defaultValue": 0,
          "required": false,
          "help": "Check to include the full raw events in the payload."
        }
      ]
    }
  ]
}
```

### Alert action properties reference

| Property | Type | Description |
|---|---|---|
| `name`* | string | Alphanumeric name used to generate the Python file for the alert action. |
| `label`* | string | User-facing name shown in Trigger Actions. |
| `description`* | string | Description of the alert action. |
| `entity`* | array | Array of input fields available in the alert action UI. |
| `iconFileName` | string | Icon file name; must be in `appserver/static/`. Defaults to `alerticon.png`. |
| `customScript` | string | Python script with custom validation and execution logic. Must be in `package/bin/`. |
| `adaptiveResponse` | object | Configuration for Enterprise Security Adaptive Response integration. |

### The custom alert action script

If `customScript` is specified, UCC expects that file in `package/bin/`. It must define a
`process_event()` function and optionally a `validate_params()` function:

**`package/bin/my_alert_helper.py`**:

```python
import json
import urllib.request


def process_event(helper, *args, **kwargs):
    """Called when the alert fires. Return 0 on success, non-zero on failure."""
    helper.log_info("Alert action send_to_service started.")

    webhook_url = helper.get_param("webhook_url")
    severity = helper.get_param("severity")
    include_raw = helper.get_param("include_raw")

    events = helper.get_events()

    payload = json.dumps({
        "severity": severity,
        "event_count": len(events),
        "events": events if include_raw else [],
    }).encode("utf-8")

    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        urllib.request.urlopen(req)
        helper.log_info(f"Successfully sent {len(events)} events.")
        return 0
    except Exception as e:
        helper.log_error(f"Failed to send events: {e}")
        return 1
```

If `customScript` is _not_ provided, UCC generates a boilerplate Python file with
stub implementations. The `helper` object is an instance of
`splunktaucclib.alert_actions_base.ModularAlertBase` and provides methods such as
`get_param()`, `get_events()`, `log_info()`, `log_error()`, `addevent()`, and
`writeevents()`.

### What UCC generates from the alert definition

From the `alerts` entry above, `ucc-gen build` produces:

- `default/alert_actions.conf` — alert action configuration
- `default/alert_actions.conf.spec` — spec file
- `bin/send_to_service.py` — the alert action entry point (imports your custom script)
- `default/data/ui/alerts/send_to_service.html` — the alert action UI form

---

## Defining Custom Search Commands in `globalConfig.json`

Custom search commands are declared in `globalConfig.json` under the top-level
`customSearchCommand` key (at the same indent level as `meta` and `pages`). UCC
auto-generates a wrapper Python script and `commands.conf` stanza from this definition.

There are four types of custom search commands in Splunk: Generating, Streaming,
Transforming, and Dataset processing. UCC's `commandType` property accepts three
values: `generating`, `streaming`, and `dataset processing` (eventing/dataset
processing commands use a `transform` function in the logic file).

### How it works

You provide a **logic file** in `package/bin/` containing the actual command implementation.
UCC generates a **wrapper script** (named after `commandName`) that imports from your logic
file. UCC also auto-generates the `commands.conf` stanza with `chunked = true` and
`python.version = python3`.

Your logic file must export a specific function based on the command type:

- `generating` → the logic file must include a `generate` function
- `streaming` → the logic file must include a `stream` function
- `dataset processing` → the logic file must include a `transform` function

If the file specified in `fileName` does not exist in `package/bin/`, the build will fail.

### Minimal definition in `globalConfig.json`

```json
"customSearchCommand": [
    {
        "commandName": "mycommandname",
        "fileName": "mycommandlogic.py",
        "commandType": "generating",
        "arguments": [
            {
                "name": "argument_name",
                "validate": {
                    "type": "Fieldname"
                },
                "required": true
            },
            {
                "name": "argument_two"
            }
        ]
    }
]
```

This generates a wrapper script named `mycommandname.py` that imports from your
`mycommandlogic.py` file, and produces the following `commands.conf` stanza:

```ini
[mycommandname]
filename = mycommandname.py
chunked = true
python.version = python3
```

### `customSearchCommand` properties reference

| Property | Type | Description |
|---|---|---|
| `commandName`* | string | Name of the custom search command. |
| `fileName`* | string | Name of the Python file containing the command logic. Must exist in `package/bin/`. |
| `commandType`* | string | Type of command: `streaming`, `generating`, or `dataset processing`. |
| `arguments`* | array[objects] | Arguments that can be passed to the command. |
| `requiredSearchAssistant` | boolean | Whether to generate `searchbnf.conf` for search assistance. Default: `false`. |
| `usage` | string | Usage visibility: `public`, `private`, or `deprecated`. Required if `requiredSearchAssistant` is `true`. |
| `description` | string | Description of the command. Required if `requiredSearchAssistant` is `true`. |
| `syntax` | string | Syntax string for the command. Required if `requiredSearchAssistant` is `true`. |

### Argument properties

| Property | Type | Description |
|---|---|---|
| `name`* | string | Name of the argument. |
| `defaultValue` | string/number | Default value of the argument. |
| `required` | boolean | Whether the argument is required. |
| `validate` | object | Validation specification. Supported types: `Integer`, `Float`, `Boolean`, `RegularExpression`, `FieldName`. |

For `Integer` and `Float` validators, you can optionally specify `minimum` and `maximum`
properties. The other validators (`Boolean`, `RegularExpression`, `FieldName`) require
no additional properties. All validators are provided by the `splunklib` library.

### Full example with search assistant

```json
"customSearchCommand": [
    {
        "commandName": "generatetextcommand",
        "fileName": "generatetext.py",
        "commandType": "generating",
        "requiredSearchAssistant": true,
        "description": "This command generates COUNT occurrences of a TEXT string.",
        "syntax": "generatetextcommand count=<event_count> text=<string>",
        "usage": "public",
        "arguments": [
            {
                "name": "count",
                "required": true,
                "validate": {
                    "type": "Integer",
                    "minimum": 5,
                    "maximum": 10
                }
            },
            {
                "name": "text",
                "required": true
            }
        ]
    }
]
```

The logic file you provide in `package/bin/generatetext.py` would contain:

```python
def generate(command):
    """Called by the UCC-generated wrapper script."""
    count = int(command.count)
    text = command.text
    for i in range(count):
        yield {"_raw": f"{i + 1}. {text}", "_time": None}
```

From this, UCC generates a wrapper script (`generatetextcommand.py`), a `commands.conf`
stanza, and (because `requiredSearchAssistant` is `true`) a `searchbnf.conf` stanza
providing search-time syntax assistance.

---

## Complete `globalConfig.json` Example

Here is a complete `globalConfig.json` that defines a modular input, an alert action,
and a custom search command together:

```json
{
  "pages": {
    "configuration": {
      "title": "Configuration",
      "description": "Set up your add-on",
      "tabs": [
        {
          "name": "account",
          "title": "Account",
          "entity": [
            {
              "type": "text",
              "label": "API Key",
              "field": "api_key",
              "help": "Enter your API key.",
              "required": true,
              "encrypted": true
            }
          ]
        },
        {
          "name": "logging",
          "title": "Logging",
          "entity": [
            {
              "type": "singleSelect",
              "label": "Log Level",
              "field": "loglevel",
              "defaultValue": "INFO",
              "options": {
                "disableSearch": true,
                "autoCompleteFields": [
                  { "value": "DEBUG", "label": "DEBUG" },
                  { "value": "INFO",  "label": "INFO" },
                  { "value": "WARN",  "label": "WARN" },
                  { "value": "ERROR", "label": "ERROR" }
                ]
              }
            }
          ]
        }
      ]
    },
    "inputs": {
      "title": "Inputs",
      "description": "Manage your data inputs",
      "services": [
        {
          "name": "my_data_input",
          "title": "My Data Input",
          "inputHelperModule": "my_input_helper",
          "entity": [
            {
              "type": "text",
              "label": "Name",
              "field": "name",
              "required": true,
              "validators": [
                {
                  "type": "regex",
                  "pattern": "^[a-zA-Z]\\w*$",
                  "errorMsg": "Must begin with a letter; alphanumerics and underscores only."
                }
              ]
            },
            {
              "type": "text",
              "label": "Interval",
              "field": "interval",
              "required": true,
              "defaultValue": "300",
              "validators": [
                {
                  "type": "regex",
                  "pattern": "^\\d+$",
                  "errorMsg": "Interval must be a positive integer."
                }
              ]
            },
            {
              "type": "text",
              "label": "API Endpoint",
              "field": "api_endpoint",
              "required": true
            },
            {
              "type": "singleSelect",
              "label": "Index",
              "field": "index",
              "defaultValue": "default",
              "required": true,
              "options": {
                "endpointUrl": "data/indexes",
                "denyList": "^_.*$",
                "createSearchChoice": true
              }
            }
          ]
        }
      ],
      "table": {
        "actions": ["edit", "delete", "clone"],
        "header": [
          { "label": "Name",     "field": "name" },
          { "label": "Interval", "field": "interval" },
          { "label": "Index",    "field": "index" },
          { "label": "Status",   "field": "disabled" }
        ]
      }
    },
    "dashboard": {
      "panels": [
        { "name": "default" }
      ]
    }
  },
  "alerts": [
    {
      "name": "send_to_service",
      "label": "Send to External Service",
      "description": "Forwards alert results to an external API.",
      "customScript": "my_alert_helper.py",
      "entity": [
        {
          "type": "text",
          "label": "Webhook URL",
          "field": "webhook_url",
          "required": true
        },
        {
          "type": "singleSelect",
          "label": "Severity",
          "field": "severity",
          "required": true,
          "defaultValue": "medium",
          "options": {
            "items": [
              { "value": "low",      "label": "Low" },
              { "value": "medium",   "label": "Medium" },
              { "value": "high",     "label": "High" },
              { "value": "critical", "label": "Critical" }
            ]
          }
        }
      ]
    }
  ],
  "customSearchCommand": [
    {
      "commandName": "mycommand",
      "fileName": "my_command_logic.py",
      "commandType": "streaming",
      "requiredSearchAssistant": true,
      "description": "Filters events where a field exceeds a threshold.",
      "syntax": "mycommand field=<fieldname> threshold=<number>",
      "usage": "public",
      "arguments": [
        {
          "name": "field",
          "required": true,
          "validate": {
            "type": "Fieldname"
          }
        },
        {
          "name": "threshold",
          "required": true,
          "validate": {
            "type": "Float"
          }
        }
      ]
    }
  ],
  "meta": {
    "name": "my_ta_example",
    "restRoot": "my_ta_example",
    "version": "1.0.0",
    "displayName": "My TA Example",
    "schemaVersion": "0.0.3"
  }
}
```

---

## End-to-End Build Workflow

Putting it all together — from an empty directory to an installable add-on:

```bash
# 1. Set up the environment
python3 -m venv .venv
source .venv/bin/activate
pip install splunk-add-on-ucc-framework

# 2. Initialise the project
ucc-gen init \
  --addon-name "my_ta_example" \
  --addon-display-name "My TA Example" \
  --addon-input-name my_data_input

# 3. Edit globalConfig.json to add inputs, alerts, custom commands, configuration tabs
#    (See the complete example above)

# 4. Add your custom code to package/bin/
#    - my_input_helper.py     (modular input helper — validate_input + stream_events)
#    - my_alert_helper.py     (alert action script — process_event)
#    - my_command_logic.py    (custom search command logic — generate/stream/transform)

# 5. Build the add-on
ucc-gen build --source my_ta_example/package --ta-version 1.0.0

# 6. Package the add-on
ucc-gen package --path output/my_ta_example

# 7. Install the resulting .tar.gz on your Splunk instance
```

---

## References

- [UCC Framework documentation](https://splunk.github.io/addonfactory-ucc-generator/) — full reference for `globalConfig.json` schema, entity types, validators, and advanced features
- [UCC quickstart guide](https://splunk.github.io/addonfactory-ucc-generator/quickstart/) — step-by-step getting started
- [UCC inputs reference](https://splunk.github.io/addonfactory-ucc-generator/inputs/) — modular input service properties
- [UCC alert actions reference](https://splunk.github.io/addonfactory-ucc-generator/alert_actions/) — alert action configuration
- [UCC alert action scripts](https://splunk.github.io/addonfactory-ucc-generator/alert_actions/alert_scripts/) — custom script implementation
- [UCC input helper module](https://splunk.github.io/addonfactory-ucc-generator/inputs/helper/) — `validate_input` and `stream_events` pattern
- [UCC custom search commands](https://splunk.github.io/addonfactory-ucc-generator/custom_search_commands/) — including commands in UCC apps
- [UCC .conf files](https://splunk.github.io/addonfactory-ucc-generator/dot_conf_files/) — how UCC generates and merges `.conf` files
- [Example TA on GitHub](https://github.com/splunk/splunk-example-ta) — a reference add-on built with UCC
- [solnlib](https://github.com/splunk/addonfactory-solutions-library-python) — utility library for add-on development
- [splunktaucclib](https://github.com/splunk/addonfactory-ucc-library) — UCC runtime library
- [Splunk SDK for Python](https://github.com/splunk/splunk-sdk-python) — used by generated modular inputs