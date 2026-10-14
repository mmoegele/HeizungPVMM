# EVCC Custom Charger - Heizstab HTTP Plugin Setup

This configuration adds the heating system's 3x 2kW heating elements as a
custom EVCC charger/loadpoint using the HTTP plugin.

**How it works:** EVCC controls the heating elements directly via HTTP calls to
the heating system's REST API. EVCC decides when to enable heating and how much
power to use based on solar surplus. EVCC sends `enable` (on/off) and
`setmaxpower` (desired Watts) — our API maps the Watts to 0–3 heating elements.

## Heating System Config (heating_config.yaml)

The old EVCC controller (`evcc.enable`) must be **disabled** since EVCC is now
the controller. Enable the charger API instead:

```yaml
evcc:
  enable: false          # Old controller OFF
  heating_element_power: 2000.0
  charger_api:
    enable: true
    temp_sensor: "puffer_k_mitte"  # Buffer temperature sensor for EVCC display
```

## EVCC Configuration (evcc.yaml)

Add the following sections to your EVCC configuration file.
Replace `HEATING_SYSTEM_IP` with your Raspberry Pi's IP address.

### Charger (Custom HTTP)

```yaml
chargers:
  - name: heizstab
    type: custom
    features:
      - heating
      - integrateddevice
    icon: heater
    # --- Read attributes (EVCC reads these) ---
    status:
      source: http
      uri: http://HEATING_SYSTEM_IP:8080/api/evcc/charger/status
      jq: .status
    enabled:
      source: http
      uri: http://HEATING_SYSTEM_IP:8080/api/evcc/charger/enabled
      jq: .enabled
    power:
      source: http
      uri: http://HEATING_SYSTEM_IP:8080/api/evcc/charger/power
      jq: .power
    temp:
      source: http
      uri: http://HEATING_SYSTEM_IP:8080/api/evcc/charger/temp
      jq: .temp
    templimit:
      source: http
      uri: http://HEATING_SYSTEM_IP:8080/api/evcc/charger/templimit
      jq: .templimit
    getmaxpower:
      source: http
      uri: http://HEATING_SYSTEM_IP:8080/api/evcc/charger/maxpower
      jq: .maxpower
    # --- Write attributes (EVCC sends commands via POST) ---
    enable:
      source: http
      uri: http://HEATING_SYSTEM_IP:8080/api/evcc/charger/enable
      method: POST
      body: "${enable}"
    maxcurrent:
      source: http
      uri: http://HEATING_SYSTEM_IP:8080/api/evcc/charger/maxcurrent
      method: POST
      body: "${maxcurrent}"
    setmaxpower:
      source: http
      uri: http://HEATING_SYSTEM_IP:8080/api/evcc/charger/setmaxpower
      method: POST
      body: "${setmaxpower}"
```

### Meter (Power Measurement)

```yaml
meters:
  - name: heizstab_meter
    type: custom
    power:
      source: http
      uri: http://HEATING_SYSTEM_IP:8080/api/evcc/charger/power
      jq: .power
```

### Loadpoint

```yaml
loadpoints:
  - title: Heizstab
    charger: heizstab
    meter: heizstab_meter
    mincurrent: 9    # ~2kW = 1 element (9A × 230V × 1 phase)
    maxcurrent: 9    # ~6kW = 3 elements (9A × 230V × 3 phases)
    phases: 3         # each heating element on a separate phase
    enable:
      threshold: -1700   # Enable at 1.7kW surplus
      delay: 2m
    disable:
      threshold: 150     # Disable at 150W grid import
      delay: 5m
```

## API Endpoints Reference

### Read endpoints (EVCC polls these via GET)

| Endpoint | Purpose | Response |
|---|---|---|
| `GET /api/evcc/charger/status` | Charger status (B=idle, C=heating) | `{"status": "B"}` |
| `GET /api/evcc/charger/enabled` | Is heating enabled? | `{"enabled": false}` |
| `GET /api/evcc/charger/power` | Current heating power in W | `{"power": 4000}` |
| `GET /api/evcc/charger/temp` | Buffer temperature °C | `{"temp": 45.5}` |
| `GET /api/evcc/charger/templimit` | Temperature limit °C | `{"templimit": 85}` |
| `GET /api/evcc/charger/maxpower` | Max possible power W | `{"maxpower": 6000}` |

### Write endpoints (EVCC sends commands)

| Endpoint | Method | Body | Purpose |
|---|---|---|---|
| `/api/evcc/charger/enable` | POST | `true` / `false` | EVCC enables/disables heating |
| `/api/evcc/charger/maxcurrent` | POST | `16` (amps) | EVCC sets max current |
| `/api/evcc/charger/setmaxpower` | POST | `4000` (watts) | EVCC sets desired power (preferred for heating) |

GET variants also supported: `/enable/true`, `/maxcurrent/16`, `/setmaxpower/4000`

EVCC sends plain text body (not JSON) — both formats are handled.

## How EVCC controls the heating elements

Each heating element (2kW) is on a separate phase. The heater supports 1 to 3
phase operation automatically. EVCC controls power via `maxcurrent` (per-phase
amps) with `phases: 3`. Our system maps the total power to 0–3 elements:

| setmaxpower (W) | Elements activated |
|---|---|
| 0 – 1999 | 0 |
| 2000 – 3999 | 1 (2kW) |
| 4000 – 5999 | 2 (4kW) |
| 6000+ | 3 (6kW) |

Formula: `elements = floor(setmaxpower / element_power)`

The `enable` endpoint acts as master switch — when `false`, all elements are off
regardless of `setmaxpower`.
