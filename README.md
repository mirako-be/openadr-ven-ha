# openadr-ven-ha

A Home Assistant custom component that implements an **OpenADR 2.0b Virtual End Node (VEN)**, translating demand response signals from a grid operator VTN into Modbus TCP power setpoints on a solar PV inverter.

## Architecture

```
Grid operator VTN
      │  HTTPS / OADR XML-SOAP
      ▼
openleadr client  (HA background task)
      │
      ▼  signal mapper (SIMPLE 0–3 → %)
HA automation engine
      │  number.set_value
      ▼
Solar PV inverter  (Modbus TCP · SunSpec WMaxLimPct)
```

The VEN runs as a supervised background task inside HA's event loop — no separate Docker container or MQTT broker required.

## Requirements

- Home Assistant 2024.1 or later
- Python package: `openleadr==0.5.30` (installed automatically via `manifest.json`)
- A Modbus TCP integration configured for your inverter, exposing a `number` entity for power limit (e.g. `number.inverter_power_limit`)

## Installation

### HACS (recommended)

1. Add this repository as a custom HACS repository (category: Integration).
2. Install **OpenADR VEN** from HACS.
3. Restart Home Assistant.

### Manual

1. Copy the `custom_components/openadr_ven/` directory into your HA `config/custom_components/` folder.
2. Restart Home Assistant.

## Configuration

1. Go to **Settings → Integrations → Add integration** and search for **OpenADR VEN**.
2. Enter your VTN connection details:
   - **VTN URL** — full HTTPS endpoint provided by your grid operator
   - **VEN name** — unique identifier for this node (agree with operator)
   - **TLS verification** — disable only for local testing
   - **Certificate / key / CA paths** — required for mutual TLS (typical in production)
3. Select the `number` entity that controls inverter power limit.
4. Click **Submit**.

After setup, open **Configure** on the integration card to adjust the SIMPLE level mapping:

| SIMPLE level | Default setpoint |
|---|---|
| 0 (normal)   | 100% |
| 1 (moderate) | 75%  |
| 2 (high)     | 50%  |
| 3 (critical) | 0%   |

## Entities created

| Entity | Type | Description |
|---|---|---|
| `sensor.dr_event_level` | sensor | Current SIMPLE signal level (0–3) |
| `sensor.dr_setpoint`    | sensor | Mapped power setpoint (%) |
| `sensor.dr_event_id`    | sensor | VTN event identifier string |

## Modbus inverter setup

Configure the HA Modbus integration for your inverter in `configuration.yaml`. Example for a SunSpec-compliant inverter:

```yaml
modbus:
  - name: "PV Inverter"
    type: tcp
    host: 192.168.1.50
    port: 502
    delay: 3
    numbers:
      - name: "Inverter power limit"
        slave: 1
        address: 40232       # SunSpec WMaxLimPct
        min_value: 0
        max_value: 100
        step: 1
        data_type: uint16
        scale: 100           # register unit is 0.01%
        unit_of_measurement: "%"
```

Consult your inverter's Modbus documentation for the exact register address and scaling.

## TLS certificates

Grid operators using OpenADR in production require mutual TLS. Place your certificates somewhere HA can read them (e.g. `/config/certs/`) and enter the absolute paths during setup.

```
/config/certs/
├── ven.crt       # VEN client certificate (issued by operator PKI)
├── ven.key       # VEN private key
└── ca.crt        # Operator CA certificate
```

## Development

```bash
python -m venv venv
source venv/bin/activate
pip install openleadr homeassistant pytest-homeassistant-custom-component
pytest tests/
```

## Licence

MIT
