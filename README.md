# openadr-ven-ha

A Home Assistant custom component implementing an **OpenADR 3.0 Virtual End Node (VEN)**,
translating demand response signals from a grid operator VTN into Modbus TCP power
setpoints on a solar PV inverter.

## Architecture

```
Grid operator VTN  (OpenADR 3.0 REST API)
      │  OAuth2 client credentials · HTTPS
      ▼
OpenADR3Client  (HA background task — polls /events, submits /reports)
      │  NormalizedEvent
      ▼
DRCoordinator  (SIMPLE level → power setpoint mapping)
      │  number.set_value
      ▼
Solar PV inverter  (Modbus TCP · SunSpec WMaxLimPct)
```

The VEN runs as a supervised background task inside HA — no separate
container, broker, or native dependencies required.

## Requirements

- Home Assistant 2024.1 or later
- A Modbus TCP integration configured for your inverter, exposing a `number`
  entity for power limit (e.g. `number.inverter_power_limit`)
- OAuth2 client credentials issued by your grid operator

## Installation

### HACS (recommended)

1. Add this repository as a custom HACS repository (category: Integration).
2. Install **OpenADR VEN** from HACS.
3. Restart Home Assistant.

### Manual

Copy `custom_components/openadr_ven/` into your HA `config/custom_components/`
folder and restart Home Assistant.

## Configuration

**Settings → Integrations → Add integration → OpenADR VEN**

Step 1 — connection:

| Field | Description |
|---|---|
| VTN base URL | Base URL of the VTN REST API (no trailing slash) |
| VEN name | Unique identifier agreed with your operator |
| OAuth2 token endpoint | Full URL of the token endpoint |
| OAuth2 client ID | Issued by the operator identity provider |
| OAuth2 client secret | Issued by the operator identity provider |

Step 2 — select the `number` entity that controls your inverter power limit.

After setup, click **Configure** to adjust:

| SIMPLE level | Default setpoint |
|---|---|
| 0 — normal    | 100% |
| 1 — moderate  | 75%  |
| 2 — high      | 50%  |
| 3 — critical  | 0%   |

Poll interval (10–3600 s, default 60 s) is also configurable here.

## Entities

| Entity | Description |
|---|---|
| `sensor.dr_event_level`  | Current SIMPLE signal level (0–3) |
| `sensor.dr_setpoint`     | Mapped power setpoint (%) |
| `sensor.dr_event_id`     | VTN event identifier |

## Modbus inverter setup

```yaml
modbus:
  - name: "PV Inverter"
    type: tcp
    host: 192.168.1.50
    port: 502
    numbers:
      - name: "Inverter power limit"
        slave: 1
        address: 40232      # SunSpec WMaxLimPct
        min_value: 0
        max_value: 100
        step: 1
        data_type: uint16
        scale: 100          # register unit is 0.01%
        unit_of_measurement: "%"
```

## Licence

MIT
