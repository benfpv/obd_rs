# OBD Data Reference — obd_rs

Reference log of all data channels, expected ranges, support status, and
how each value flows from the adapter to the dashboard.

---

## Hardware

| Item          | Detail                                          |
|---------------|-------------------------------------------------|
| Adapter       | Veepeak oBDCheck BLE+                           |
| Protocol      | ELM327 over BLE UART                            |
| Vehicle       | FT86 platform (Subaru BRZ / Toyota 86 / FR-S)   |
| BLE services  | `0000fff0-` (primary UART), `00006287-` (alt)    |
| Notify char   | `0000fff1-` (FFF0) / `00006487-` (6287)          |
| Write char    | `0000fff2-` (FFF0) / `00006387-` (6287)          |

---

## Channel Inventory

All channels below are standard OBD-II PIDs — no manufacturer-specific or
non-standard CAN decoding is used.

### HIGH priority (polled fastest — REALTIME 4 Hz / CRUISE 1 Hz)

| Channel   | OBD Mode | PID  | Unit  | Raw Range        | Dashboard Range | Decode Formula                   | Status    |
|-----------|----------|------|-------|------------------|-----------------|----------------------------------|-----------|
| rpm       | 01       | 0C   | rpm   | 0–16 383.75      | 0–9 000         | `((A*256)+B) / 4`               | Supported |
| speed     | 01       | 0D   | km/h  | 0–255            | 0–320           | `A`                              | Supported |
| throttle  | 01       | 11   | %     | 0–100            | 0–100           | `A * 100 / 255`                  | Supported |

### MEDIUM priority (REALTIME 1 Hz / CRUISE 0.5 Hz)

| Channel        | OBD Mode | PID  | Unit | Raw Range        | Dashboard Range | Decode Formula                   | Status    |
|----------------|----------|------|------|------------------|-----------------|----------------------------------|-----------|
| engine_load    | 01       | 04   | %    | 0–100            | 0–100           | `A * 100 / 255`                  | Supported |
| coolant_temp   | 01       | 05   | °C   | −40–215          | −40–160         | `A − 40`                         | Supported |
| intake_temp    | 01       | 0F   | °C   | −40–215          | −40–120         | `A − 40`                         | Supported |
| stft_b1        | 01       | 06   | %    | −100–99.2        | −30–30 (plot)   | `(A − 128) * 100 / 128`         | Supported |
| ltft_b1        | 01       | 07   | %    | −100–99.2        | −30–30 (plot)   | `(A − 128) * 100 / 128`         | Supported |
| spark_advance  | 01       | 0E   | °    | −64–63.5         | −64–64          | `A / 2 − 64`                     | Supported |

### LOW priority (REALTIME 0.2 Hz / CRUISE 0.1 Hz)

| Channel         | OBD Mode | PID  | Unit | Raw Range   | Dashboard Range | Decode Formula     | Status    |
|-----------------|----------|------|------|-------------|-----------------|--------------------|-----------|
| module_voltage  | 01       | 42   | V    | 0–65.535    | 0–20            | `((A*256)+B)/1000` | Supported |

### EXTENDED PIDs (probed at startup — may or may not be supported)

| Channel          | OBD Mode | PID  | Unit  | Raw Range    | Dashboard Range | Decode Formula     | Status               |
|------------------|----------|------|-------|--------------|-----------------|--------------------|-----------------------|
| maf_gps          | 01       | 10   | g/s   | 0–655.35     | text readout    | `((A*256)+B)/100`  | Probed at startup     |
| map_kpa          | 01       | 0B   | kPa   | 0–255        | text readout    | `A`                | Probed at startup     |
| oil_temp         | 01       | 5C   | °C    | −40–215      | 40–160 (plot)   | `A − 40`           | Probed at startup     |

---

## Derived / Computed Channels

These are calculated in software from standard OBD signals, not read from the adapter.

| Channel          | Source Inputs            | Formula                                              | Dashboard Range | Logged | Notes                                          |
|------------------|--------------------------|------------------------------------------------------|-----------------|---------|-------------------------------------------------|
| est_power_kw     | rpm, engine_load         | `(rpm/1000) * (load/100) * 11.5`                     | 0–300 kW        | Yes     | Very rough estimate                             |
| est_torque_nm    | est_power_kw, rpm        | `power_kw * 9549 / max(800, rpm)`                    | 0–600 Nm        | Yes     | Derived from power via P = Tω                   |
| accel_ms2        | speed (Δ), dt            | `(Δspeed_m/s) / dt`                                  | ±0.8 g meter    | Yes     | Longitudinal acceleration from speed derivative |
| inferred_brake   | accel_ms2, throttle_drop | `clip(max(0, −accel*18) + throttle_drop*0.5, 0, 100)`| 0–100%          | Yes     | Inferred only; N/A when stopped                 |

---

## Diagnostic Trouble Codes

| Query   | OBD Mode | Description                | Status    |
|---------|----------|----------------------------|-----------|
| Active DTCs   | 03 | Current confirmed DTCs     | Supported |
| Pending DTCs  | 07 | Pending / freeze-frame DTCs | Supported |

DTC format: `Pxxxx`, `Cxxxx`, `Bxxxx`, `Uxxxx` (prefix from upper 2 bits of byte 1).

DTCs are logged to CSV (semicolon-separated in `dtcs_active` and `dtcs_pending` columns).

---

## Dashboard Panel → Channel Mapping

| Panel                   | Channels Displayed                                                                 |
|-------------------------|-------------------------------------------------------------------------------------|
| DIAGNOSTICS             | coolant_temp, intake_temp (or oil_temp if supported), module_voltage + trend plots  |
| RACING INPUTS           | rpm (rev lights), speed, throttle (pedal), inferred_brake (pedal), accel_ms2 (G-meter), speed plot, throttle+brake plot |
| ENGINE / POWER          | rpm (power band), est_power_kw, est_torque_nm, engine_load, spark_advance, maf_gps, map_kpa, power plot, torque plot |
| ALERTS                  | Active + pending DTC alerts, threshold-based alerts (coolant, fuel trims, voltage)  |
| SYSTEM                  | Connection state, device name, detail, log mode, poll cadence bars                  |
| FUEL TRIMS & EXTENDED   | oil_temp, maf_gps, map_kpa (metric cells), stft_b1, ltft_b1 (readouts + sparklines), oil_temp sparkline |

---

## Plot Ranges Summary

All sparkline charts are clamped to these explicit y_range bounds:

| Plot                 | y_range         | Thresholds        |
|----------------------|-----------------|-------------------|
| Coolant Temp Trend   | 40 – 130 °C     | 95 °C, 112 °C     |
| Module Voltage Trend | 11 – 15 V       | 12.2 V, 14.8 V    |
| Speed Ribbon         | 0 – 260 km/h    | 120 km/h           |
| Throttle + Brake     | 0 – 100 %       | 70 %               |
| Estimated Power      | 0 – 300 kW      | —                  |
| Estimated Torque     | 0 – 600 Nm      | —                  |
| STFT Trend           | autoscaled from history | —           |
| LTFT Trend           | autoscaled from history | —           |
| Oil Temp Trend       | autoscaled from history | —           |

---

## Signal Quality Notes

- **stale** flag on each `Signal` indicates whether data was recently refreshed (age > `SIGNAL_STALE_AGE_S`).
- **confidence** is set to `1.0` when a valid reading is received, `0.0` otherwise.
- **supported** flag is set per-signal after startup probe; `False` means the ECU didn't respond.
- History values are clamped at ingestion (see panel `update()` methods in `obd_rs/ui/`).
- Brake is stored as `NaN` when not observable (vehicle speed ≤ 2 km/h and |accel| ≤ 0.35 m/s²).
- Extended channels (oil_temp, maf, map) use `_vn()` which preserves `NaN` for unsupported signals.

---

## ELM327 Initialization Sequence

| Mode            | Commands Sent      | Notes                               |
|-----------------|--------------------|--------------------------------------|
| Minimal (default) | `ATE0`, `ATSP0`  | Echo off + auto protocol             |
| Full            | `ATZ`, `ATE0`, `ATL0`, `ATS0`, `ATSP0` | Reset, echo off, linefeeds off, spaces off, auto protocol |

Write pacing: minimum 80 ms between BLE writes (`MIN_WRITE_INTERVAL_S = 0.08`).

---

## Connection State Machine

```
DISCONNECTED → SCANNING → CONNECTING → INITIALIZING → READY
                                                      ↓
                                                  RECOVERING → SCANNING
```

- Auto-reconnect on transport error with re-scan fallback.
- `start_notify` has 8 s timeout with retry.
- Response accumulation: wake on any BLE notify chunk, then poll for `>` prompt.

---

## Data Logging

Telemetry is persisted to CSV files in the `logs/` directory only when running in live/connect mode.
In simulated mode, CSV logging is disabled.

| Setting           | Env Var                    | Default  |
|-------------------|----------------------------|----------|
| Log directory     | `OBD_RS_LOG_DIR`           | `logs`   |
| Max total size    | `OBD_RS_LOG_MAX_BYTES`     | 10 MB    |

- One CSV file per session (`session_YYYYMMDD_HHMMSS.csv`).
- Header row: `timestamp` + 13 signal value fields (sorted) + 4 derived fields + per-signal state columns + session context + `dtcs_active` + `dtcs_pending`.
- Derived columns: `est_power_kw`, `est_torque_nm`, `accel_ms2`, `inferred_brake`.
- Per-signal state columns: `<signal>__supported`, `<signal>__stale`, `<signal>__confidence` for every TelemetryState field.
- Session context columns: `connection_state`, `connection_detail`, `device_name`, `log_mode`.
- DTC columns contain semicolon-separated code lists (empty when no DTCs present).
- Rows flushed every 100 samples or 5 seconds.
- When total log directory size exceeds the limit, oldest session files are pruned.
- Last-known values may still appear during disconnects or stale periods, but those rows now carry explicit stale and connection-state markers so the CSV remains truthful.
