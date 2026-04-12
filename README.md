# obd_rs

Real-time OBD-II racing dashboard built with Python and OpenCV.

Connects to an ELM327-compatible BLE adapter over Bluetooth Low Energy
(tested with [Veepeak oBDCheck BLE+](https://www.veepeak.com/)), reads
standard OBD-II PIDs, and renders a live dashboard with gauges, trend plots,
alert cards, and derived telemetry (estimated power, torque, longitudinal
G-force, inferred braking).

> **Platform:** Windows-first. Requires Python 3.12+ and a BLE-capable host.

---

## Quick start

```bash
# 1. Create a virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate        # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run
python main.py                # interactive mode chooser
```

On Windows you can also double-click `run_obd_rs.bat`.

---

## Data sources

Data source is selected at startup via an interactive chooser, or overridden
with the `OBD_RS_DATA_SOURCE` environment variable:

| Value        | Description                            | Provider                                     |
|--------------|----------------------------------------|----------------------------------------------|
| `simulated`  | Synthetic telemetry for UI development | `obd_rs/providers/simulated_provider.py`     |
| `live`       | Real BLE adapter polling               | `obd_rs/providers/live_provider.py`          |
| `replay`     | Recorded CSV session playback          | `obd_rs/providers/replay_provider.py`        |

```bash
# Example: skip the chooser and go straight to simulation
set OBD_RS_DATA_SOURCE=simulated
python main.py
```

### Replay controls

When running in replay mode, the following keyboard shortcuts are available:

| Key | Action                                  |
|-----|-----------------------------------------|
| `P` | Toggle pause / resume                   |
| `O` | Stop replay                             |
| `J` | Seek backward 5 s                       |
| `L` | Seek forward 5 s                        |
| `S` | Skip to next frame ≥ 5 km/h            |

---

## Adapter compatibility

This project is built around standard ELM327-style ASCII commands and standard
OBD-II PID decoding, so it is not hard-wired to Veepeak at the protocol level.
The current live transport is, however, optimized for BLE adapters that expose
a transparent UART-like GATT interface.

### Tested

- Veepeak oBDCheck BLE+

### Likely compatible

- Other **BLE** adapters that are ELM327-compatible
- Adapters that accept standard `AT` commands and OBD-II modes `01`, `03`, and `07`
- Devices exposing notify/write GATT characteristics similar to common UART-style BLE designs

### May require code changes

- BLE adapters with different GATT layouts, initialization quirks, or timing behavior
- Adapters that do not expose a standard notify/write characteristic pair
- Devices that identify themselves with names that do not match the current scan hints

### Not currently targeted

- Classic Bluetooth SPP adapters
- Wi-Fi OBD adapters
- Vendor-specific non-ELM protocols

In short: the app is **tested on Veepeak**, but the architecture is general
enough that other BLE ELM327-style readers may work with little or no change.
For a public release, the safest wording is: **tested with Veepeak oBDCheck
BLE+, with partial compatibility for other BLE ELM327-compatible adapters**.

---

## Features

- **Provider-based architecture** — hard separation between simulated, live,
  and replay data sources behind a common `TelemetryProvider` ABC.
- **Tiered polling scheduler** — deadline-based cadence with REALTIME and
  CRUISE modes; high-priority PIDs (RPM, speed, throttle) polled faster than
  diagnostics.
- **Alert engine** — separate channels for Issues/Defects and Possible Issues,
  with stale-signal guards to avoid false positives.
- **OpenCV dashboard** — six panel sections (Diagnostics, Racing Inputs,
  Engine/Power, Alerts, System, Fuel Trims & Extended) with gauges, bars,
  sparklines, and overlay cards.
- **CSV telemetry logging** — rolling per-session logs with per-signal state
  tracking and automatic retention pruning (live mode only).
- **Read-only safety** — no ECU write operations; the BLE send path rejects
  commands outside an explicit read-only allowlist.
- **Replay mode** — playback of recorded CSV sessions with pause, seek, and
  skip-to-speed controls.
- **Disconnect utility** — best-effort BLE disconnect for post-session cleanup.

---

## Architecture

### Provider contract

All data sources implement the `TelemetryProvider` ABC (`obd_rs/providers/base.py`),
which defines 11 abstract methods covering lifecycle, querying, and diagnostics.

Replay providers additionally implement the `PlaybackCapable` mixin for
playback controls (pause, stop, seek, skip-to-speed). The app uses capability
checks (`isinstance`) rather than mode strings for feature gating.

### Type safety

Mode selection uses the `DataSource` enum (`obd_rs/config.py`) throughout the
stack — startup UI, app orchestrator, and dashboard panels all receive typed
enum values instead of raw strings.

### Module layout

```
main.py                          Entry point
obd_rs/
├── config.py                    Environment-driven configuration, enums
├── app.py                       Main orchestrator (decomposed async loop)
├── startup.py                   Interactive mode / device / file chooser
├── scheduler.py                 Deadline-based cadence polling
├── alerts.py                    Heuristic alert engine
├── data_processing.py           Derived telemetry calculations
├── models.py                    TelemetryState, Signal, AlertEvent
├── obd_client.py                ELM327 protocol boundary
├── ble_adapter.py               BLE transport layer (bleak)
├── buffer.py                    Ring buffer for sample history
├── data_logger.py               Rolling CSV writer
├── logging_policy.py            Cadence mode management
├── physics.py                   Power / torque / accel estimators
├── windowing.py                 OpenCV window helpers
├── providers/
│   ├── base.py                  TelemetryProvider ABC + PlaybackCapable
│   ├── simulated_provider.py    Synthetic telemetry source
│   ├── live_provider.py         BLE + OBD live source
│   └── replay_provider.py       Recorded CSV playback
└── ui/
    ├── __init__.py              Package re-exports
    ├── _helpers.py              Shared rendering primitives
    ├── _dashboard.py            DashboardUI coordinator
    ├── _diagnostics.py          Coolant / Oil / Intake / Voltage panel
    ├── _racing.py               Rev strip, speed bar, pedals, G-meter
    ├── _engine.py               Power band, RPM/Load, sparklines
    ├── _alerts_panel.py         Scrolling alert list
    ├── _system.py               Connection state, cadence bars, comm stats
    └── _fuel_trims.py           STFT/LTFT, extended metrics, sparklines
tests/                           pytest test suite (137 tests)
```

---

## Utilities

### Disconnect

Best-effort BLE disconnect for post-session adapter cleanup:

```bash
python disconnect.py
python disconnect.py --address AA:BB:CC:DD:EE:FF
```

### Read-only safety check

Verifies that all commands the app would issue are on the read-only allowlist
and that known unsafe commands are rejected:

```bash
python check_read_only_safety.py
```

---

## Configuration

All settings are optional and read from environment variables with sensible
defaults. See `obd_rs/config.py` for the full list.

| Variable                        | Default       | Description                           |
|---------------------------------|---------------|---------------------------------------|
| `OBD_RS_DATA_SOURCE`            | *(interactive)* | `simulated`, `live`, or `replay`    |
| `OBD_RS_REPLAY_FILE`            | —             | Path to a recorded CSV for replay     |
| `OBD_RS_WINDOW_W` / `_H`       | 1200 × 760    | Dashboard window size                 |
| `OBD_RS_FPS`                    | 20            | Target render frame rate              |
| `OBD_RS_NAME_HINTS`             | `VEEPEAK,OBD,OBDII,ELM327` | BLE device name filters |
| `OBD_RS_MINIMAL_WRITES`         | `1`           | Use minimal ELM327 init sequence      |
| `OBD_RS_BLE_SCAN_TIMEOUT_S`     | 5.0           | BLE discovery timeout                 |
| `OBD_RS_MAX_RECONNECT_ATTEMPTS` | 3             | Auto-reconnect retry budget           |
| `OBD_RS_SIGNAL_STALE_AGE_S`     | 2.0           | Seconds before a signal is marked stale |
| `OBD_RS_RPM_REDLINE`            | 8000          | Rev-light redline threshold           |
| `OBD_RS_LOG_DIR`                | `logs`        | CSV telemetry output directory        |
| `OBD_RS_LOG_MAX_BYTES`          | 10 MB         | Max total log directory size          |

---

## Testing

```bash
python -m pytest tests/ -v
```

137 tests covering providers, scheduler, alerts, physics, BLE safety, buffer,
data logger, replay controls, UI helpers, and app-level integration.

---

## Safety

- **No ECU write operations are implemented.** The BLE adapter send path
  rejects any command outside a read-only allowlist (`ensure_safe_obd_command`).
- CSV telemetry logging is active only in live mode; simulated and replay modes
  do not write log files.
- Run `python check_read_only_safety.py` to verify the allowlist before making
  changes to the protocol layer.

---

## License

Released under the MIT License. See the LICENSE file for the full text.
