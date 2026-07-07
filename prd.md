# Product Requirements Document — Thermal Comfort Monitor

## 1. Overview

### 1.1 Product Vision
A three-part system: a portable, self-contained sensor device, a companion phone app (iOS and Android), and a personal analysis server. The device measures indoor thermal comfort conditions and calculates standardized comfort indices (ISO 7730). The phone app connects to the device, triggers a capture, fetches the data, and forwards it to the server. The server holds the Anthropic API key, calls Claude, and returns the analysis to the app, which emails the report. No technical knowledge is required to operate the device or app.

### 1.2 System Architecture

The device and app communicate directly over Wi-Fi — no router, no internet connection required on the device side.

```
┌──────────────────────┐  Wi-Fi (AP)  ┌──────────────────────┐  HTTPS  ┌─────────────────────┐
│        DEVICE        │              │      PHONE APP        │         │       SERVER        │
│                      │◄────────────►│                       │◄───────►│                     │
│  HTTP server         │  POST        │  Trigger capture      │         │  Anthropic API key  │
│  Sensors → PMV calc  │  /trigger    │  Fetch data + images  │         │  Claude API call    │
│  Photo + raw thermal │              │  Render heatmap       │         │  Return analysis    │
│  Always broadcasts   │              │  Send email  ─────────────────────────────► SMTP      │
│  AP                  │              │  Show result to user  │         │                     │
└──────────────────────┘              └──────────────────────┘         └─────────────────────┘
                                                 ▲
                                        cellular / Wi-Fi
                                        for internet access
```

**Device:** always broadcasts its own Wi-Fi access point. On receiving a trigger from the app, reads all sensors, captures photo, captures raw 24×32 thermal frame, calculates PMV/PPD, stores the reading locally, and signals ready via LED. Runs a lightweight HTTP server that serves the reading data and image files.

**Phone app (iOS and Android):** connects to the device AP using platform dual-networking (device AP for data transfer + cellular for internet simultaneously — no network switching required). Fetches the latest reading from the device, forwards it to the analysis server, receives the analysis, sends the email report, and displays the result to the user.

**Analysis server:** a personal server hosting the Anthropic API key and a Python endpoint that accepts sensor data and images, calls the Claude API, and returns the analysis. The server also renders the heatmap from the raw thermal frame using the existing Python codebase. SMTP credentials remain in the phone app.

**Credentials:** Anthropic API key lives on the server only. SMTP credentials are stored in the phone app's platform secure storage (iOS Keychain / Android Keystore). The device holds no credentials.

**Computer access:** secondary use case. A laptop with an ethernet connection can connect its Wi-Fi to the device AP and access the device's web dashboard over that connection while keeping internet via ethernet. Wi-Fi-only laptops cannot use the dashboard in the field.

### 1.3 Environment Assumption

The device is designed for **office spaces**. All defaults (met, clo, activity level) are calibrated for typical office use. The AI analysis shall always interpret readings in the context of an office environment.

However, offices contain a diverse population. The analysis shall explicitly acknowledge that comfort is subjective and varies by individual — factors including age, sex, BMI, acclimatisation, and personal preference mean that a space with a neutral PMV will still leave a meaningful fraction of occupants dissatisfied. The report should reflect this rather than treating PMV as an absolute verdict.

### 1.4 Target Market & Users

**Market:** B2B — office buildings. Residential and consumer use cases are out of scope for V1.

| User | Context | Primary need |
|---|---|---|
| Facilities manager | Office building | On-demand comfort snapshots for complaint response and HVAC tuning |
| Building engineer | Large commercial office space | Standards-compliant measurement with data history |
| HSE / workplace compliance officer | Corporate office | Evidence-based comfort reporting for occupant wellbeing programmes |

---

## 2. User Stories

### Setup & Onboarding
- As a new user, I want to install the app, open it near the device, and be guided through setup in under two minutes, so that I do not need IT assistance or any technical knowledge.
- As a user, I want to enter my recipient email and API credentials once in the app, so that I never have to reconfigure them unless I choose to.

### Taking a Reading
- As a user, I want to tap a button in the app to trigger a reading, so that I can get an immediate comfort assessment of any space from my phone.
- As a user, I want the email report to include the thermal heatmap and camera photo alongside the written analysis, so that I can see exactly what the device observed.
- As a user, I want to be notified if the camera photo is blurry, so that I know the image in the report may not accurately represent the space.

### Report Content
- As a reader of the report, I want to understand the comfort level at a glance from the subject line or email preview, so that I do not have to open the full report to know whether action is needed.
- As a reader, I want the report to tell me not just the current comfort level but also what is causing any discomfort and what I can do about it, so that the report is actionable.

### Configuration
- As a user, I want to quickly change the recipient email address from the app's main screen, so that I can direct a report to whoever is relevant before pressing the button.
- As a user in a space with occupants in unusual clothing or doing non-sedentary activity, I want to select a met/clo preset in the app before triggering a reading, so that the comfort calculation reflects actual conditions.

### Data & History
- As a user, I want to view a history of past readings in the app, so that I can identify trends across visits.
- As a user, I want to export my reading history as a CSV, so that I can analyse the data in a spreadsheet.

### Reliability
- As a user, I want the app to retry the Claude API call automatically if it fails, so that a brief network hiccup does not require me to repeat the whole process.
- As a user, I want the device to stay ready between button presses without needing to be restarted, so that it works reliably as a portable appliance.

### Privacy & Trust
- As a user, I want a physical shutter I can close over the camera, so that I can guarantee the camera is not active when I do not want it to be.
- As a user, I want a visible indicator when the camera is active, so that I always know when a photo is being taken.
- As a user, I want my API keys and SMTP credentials stored in the app (not on the device), so that losing or lending the device does not expose my credentials.

---

## 3. Functional Requirements

### 3.1 Sensor Acquisition (Device)

**FR-S1** — The device shall measure air temperature (°C) and relative humidity (%) using the SI7021 sensor on every reading.

**FR-S2** — The device shall measure mean radiant temperature (°C) from the MLX90640 32×24 IR array on every reading. The MRT calculation shall weight pixel values by solid angle from the device position or restrict to the occupied-zone pixel region; a naive mean of all 768 pixels is not acceptable for the production firmware.

**FR-S3** — The device shall measure air speed (m/s) using the PAV3015 sensor on every reading. The conversion formula shall be validated against a NIST-traceable anemometer before release.

**FR-S4** — The device shall capture a 1920×1080 JPEG photo of the space using the Pi Camera module on every reading.

**FR-S4a** — The camera module is fixed-focus (Module 1/2), so focus cannot be queried from the camera hardware. After capture, the device shall compute the Laplacian variance of the greyscale image as a sharpness score. If the score falls below a calibrated threshold, the reading shall be flagged as `blurry: true` in the data served to the app; the app and email report shall surface this warning.

**FR-S5** — The device shall capture the raw 24×32 float array from the MLX90640 and store it with the reading. Heatmap rendering (bicubic upscaling, inferno colormap) is performed by the phone app, not the device.

**FR-S6** — If a single sensor fails during a reading, the device shall log the fault, complete the reading with the remaining sensors, include a `sensor_fault` field in the served data, and not abort the entire reading.

### 3.2 Comfort Calculation (Device)

**FR-C1** — PMV, PPD, and TSV shall be calculated on the device per ISO 7730:2005 using the `pythermalcomfort` library.

**FR-C2** — Air speed shall be converted to relative air speed using `v_relative()` before the PMV calculation.

**FR-C3** — The device shall use default met/clo values for the PMV calculation (`met=1.1`, `clo=0.61`). The phone app shall be able to send override values to the device before triggering a reading; the device shall use those values for that reading only.

**FR-C4** — Input values outside the ISO 7730 valid range (air temp < 10 °C or > 30 °C, air speed > 1 m/s, MRT < 10 °C or > 40 °C) shall be flagged in the `notes` field of the reading.

**FR-C5** — The AI analysis shall acknowledge occupant variability in every report: even at a neutral PMV, individuals differ in comfort perception due to age, sex, BMI, acclimatisation, and personal preference. The report shall not imply that a single PMV value represents comfort for all occupants.

### 3.3 Device HTTP Server

**FR-H1** — The device shall run a lightweight HTTP server on its AP interface, accessible at `http://192.168.4.1` (or equivalent gateway IP).

**FR-H2** — The server shall expose the following endpoints:
- `GET /status` — device state (idle, capturing, ready, error) and firmware version
- `GET /reading/latest` — JSON of the most recent reading (all sensor fields, PMV, PPD, TSV, notes, blurry flag, sensor fault flag, timestamps)
- `GET /reading/latest/photo` — the JPEG file for the most recent reading
- `GET /reading/latest/thermal` — the raw 24×32 float array as JSON for the most recent reading
- `GET /readings` — JSON array of all stored readings (metadata only, no images)
- `POST /trigger` — trigger a new capture (equivalent to pressing the button)
- `POST /config` — accept met/clo override values for the next reading

**FR-H3** — Image files shall be served with correct `Content-Type` headers and support HTTP range requests so the app can stream large files without loading them entirely into memory.

### 3.4 Triggers

**FR-T1** — The phone app's "Take Reading" button shall send `POST /trigger` to the device, initiating an immediate capture sequence. This is the sole trigger; no scheduled readings or physical button are required.

**FR-T2** — The device may optionally include a physical button (GPIO 17) as a secondary trigger for convenience, but it is not a product requirement for V1.

### 3.5 Device LED States

**FR-L1** — The RGB LED shall communicate device state:
- Solid white: idle, ready for a reading
- Pulsing blue: capture in progress (sensors, photo, PMV)
- Solid green: capture complete, data ready for app to fetch
- Solid amber: capture complete but photo flagged as blurry
- Solid red: capture failed (sensor fault or camera error)
- Pulsing red: device error requiring attention

### 3.6 Phone App — Connection

**FR-APP-C1** — The app shall be available on both iOS and Android. It shall connect to the device AP using the platform dual-networking API (iOS: `NEHotspotConfiguration`; Android: `WifiNetworkSpecifier`) so that cellular internet remains active while connected to the device.

**FR-APP-C2** — The app shall automatically detect a device AP (`ThermalComfort-XXXX` SSID pattern) and prompt the user to connect, rather than requiring manual Wi-Fi switching.

**FR-APP-C3** — The app shall poll `GET /status` every 2 seconds while connected to detect when a new reading is ready.

### 3.7 Phone App — AI Analysis

**FR-APP-A1** — Once a reading is ready, the app shall fetch the sensor JSON, JPEG, and raw 24×32 thermal frame from the device over the AP connection. The app shall render the thermal heatmap locally (bicubic upscaling, inferno colormap) before sending to Claude and including in the email.

**FR-APP-A2** — The app shall POST the sensor JSON, JPEG, and raw thermal frame to the analysis server over cellular/internet. The server renders the heatmap, calls the Claude API, and returns the analysis text to the app.

**FR-APP-A3** — The server's system prompt shall instruct Claude to cover: current comfort level based on PMV/PPD, temperature distribution and hot/cold spots visible in the heatmap, observations from the camera photo, specific actionable recommendations, and a note on occupant variability.

**FR-APP-A4** — The server shall use prompt caching (`cache_control`) on the static system prompt to minimise per-call API cost.

**FR-APP-A5** — If the server call fails (timeout, network error, server error), the app shall retry with exponential backoff (initial delay 5 s, max 3 retries) and display a clear error to the user if all retries fail.

### 3.8 Phone App — Report Delivery

**FR-APP-R1** — After the analysis is complete, the app shall send an HTML email containing the AI analysis, formatted sensor readings, thermal heatmap image, and camera photo to the configured recipient.

**FR-APP-R2** — The email subject line shall include a one-line comfort summary (e.g. "Thermal Comfort Report — Neutral (PMV +0.2, PPD 5.5%)") readable in a notification preview.

**FR-APP-R3** — The email shall include a plain-text alternative for clients that block HTML.

**FR-APP-R4** — The app shall send reports to a single configured recipient address. The recipient address shall be displayed and editable on the app's main screen — not buried in settings — so it can be changed in one step before triggering a reading.

**FR-APP-R5** — Images shall be embedded inline (CID references) rather than sent as attachments.

**FR-APP-R6** — If SMTP delivery fails, the app shall display an error and offer a retry button; the analysis text shall remain visible in the app even if email fails.

### 3.9 Phone App — Configuration & UI

**FR-APP-U1** — The app's main screen shall show: device connection status, last reading summary (PMV, PPD, TSV), recipient email (editable inline), met/clo preset selector, and a "Trigger reading" button.

**FR-APP-U2** — The app shall provide plain-language presets for met/clo appropriate to an office context (e.g. "Seated desk work", "Standing / light movement", "Summer clothing", "Winter clothing") plus a manual numeric input.

**FR-APP-U3** — The app shall store SMTP credentials in the platform secure enclave (iOS Keychain / Android Keystore). The Anthropic API key is stored on the server only and is never present in the app or on the device.

**FR-APP-U4** — The app shall display a history of past readings fetched from the device, and provide a CSV export of all stored readings.

### 3.10 Device Provisioning

**FR-P1** — The device shall always broadcast a Wi-Fi AP named `ThermalComfort-XXXX` (last four characters of the device MAC address). The device does not join any external Wi-Fi network.

**FR-P2** — The AP shall use WPA2 with a default password printed on the device label. The password shall be changeable from the app.

**FR-P3** — On first launch, the app shall guide the user through: connecting to the device AP, entering SMTP credentials and Anthropic API key (stored in the app), and selecting a met/clo default. No credentials are entered on the device.

### 3.11 Device Web Dashboard (Secondary)

**FR-D1** — The device shall serve a read-only web dashboard at `http://192.168.4.1` accessible from a browser connected to the device AP.

**FR-D2** — The dashboard shall display: device status, the last reading's sensor values and comfort result, and a history table of past readings.

**FR-D3** — The dashboard shall not support triggering a full analysis (no Claude API access from the dashboard — that requires the phone app). It may support triggering a capture-only reading via `POST /trigger`.

**FR-D4** — The dashboard shall provide a CSV export of stored readings.

### 3.12 Data Storage (Device)

**FR-DS1** — All readings shall be stored in a local SQLite database with fields: timestamp, air_temp, humidity, mrt, air_speed, pmv, ppd, tsv, notes, blurry, sensor_fault, photo_path, thermal_path. The heatmap is not stored on the device; it is rendered by the app on fetch.

**FR-DS2** — The device shall retain at least 90 days of readings. Older entries may be pruned automatically.

### 3.13 Firmware Updates

**FR-FW1** — Device firmware shall be updated manually by connecting the device to a computer via USB and flashing using standard tooling (e.g. `rpiboot` + `dd`, or the Raspberry Pi Imager). No OTA mechanism is required.

**FR-FW2** — The phone app shall be updated via the standard App Store channel.

### 3.14 Error Handling & Resilience (Device)

**FR-E1** — The device shall recover from a failed capture (sensor timeout, camera error) without requiring a reboot. The systemd service shall restart on crash.

**FR-E2** — All errors shall be logged to the systemd journal with severity and timestamp, and surfaced via the `/status` endpoint so the app can display them.

---

## 4. Non-Functional Requirements

### 4.1 Performance

**NFR-P1** — Time from button press to email sent shall be under 3 minutes under normal cellular conditions.

**NFR-P2** — Device idle power consumption shall be under 3 W.

**NFR-P3** — The device shall boot to ready state (LED solid white, AP broadcasting, HTTP server live) within 45 seconds of power-on.

**NFR-P4** — Image transfer from device to phone over the AP shall complete in under 20 seconds for a 5 MB JPEG.

### 4.2 Reliability

**NFR-R1** — The device shall operate continuously for at least 30 days without requiring any user intervention.

**NFR-R2** — Mean time between failures (MTBF) target: > 2 years for the electronic assembly.

### 4.3 Physical

**NFR-PH1** — Outer dimensions shall not exceed 120 × 80 × 40 mm.

**NFR-PH2** — The device shall operate within an ambient temperature range of 10–40 °C and 20–80% RH (non-condensing).

**NFR-PH3** — The enclosure shall be suitable for indoor wall or desk mounting in an office environment (no exposed PCB, no sharp edges).

### 4.4 Security

**NFR-S1** — The device AP shall use WPA2 encryption.

**NFR-S2** — No API keys or SMTP credentials shall be stored on the device.

**NFR-S3** — App credentials shall be stored in the platform secure enclave (iOS Keychain / Android Keystore).

**NFR-S4** — The camera-active indicator LED shall be hardwired and cannot be disabled by software.

### 4.5 Privacy

**NFR-PR1** — Photos are transferred from device to phone over the local AP and then sent to the Claude API by the phone. They are not stored in any cloud beyond what the API requires for the single inference call.

**NFR-PR2** — The app shall display a privacy notice on first launch explaining what data is captured, when it is transmitted, and how to use the physical privacy shutter.

### 4.6 Regulatory

**NFR-REG1** — The device and included power adapter shall be certified to UL 62368-1 / IEC 62368-1 for electrical safety.

**NFR-REG2** — The device shall carry FCC Part 15 authorization (USA) and CE RED marking (EU) for Wi-Fi radio emissions.

**NFR-REG3** — All components shall comply with RoHS 3 (EU 2015/863).

---

## 5. Platform Decision: ESP32 vs Raspberry Pi

### 5.1 Context

Two microcontroller/SBC platforms were evaluated as the device compute core. The architecture (Option 4) is relevant here: because the phone app handles the Claude API call, email, and heatmap rendering, the device only needs to read sensors, capture a photo, capture the raw thermal frame, run the PMV calculation, and serve data over HTTP. It does not need to make outbound HTTPS calls with large image payloads, nor render any graphics.

### 5.2 Comparison

| Criterion | ESP32-S3 (+ OCTAL PSRAM) | Raspberry Pi 5 |
|---|---|---|
| **Cost** | ~$5–10 | ~$60–80 |
| **Idle power** | ~0.25 W | ~3–5 W |
| **Boot time** | Instant | 30–45 s |
| **RAM** | 512 KB SRAM + up to 8 MB PSRAM | 4–8 GB |
| **OS** | Bare-metal / RTOS | Linux (Raspberry Pi OS) |
| **Language** | C/C++ or MicroPython (sensor/camera only); Python processing runs on a server | Python (existing codebase runs entirely on device) |
| **Camera** | OV2640 — 2 MP max, hardware JPEG | Pi Camera Module — 8–12 MP, `libcamera` |
| **Thermal heatmap** | Not required — app renders from raw frame | Not required — app renders from raw frame |
| **PMV calculation** | Python runs on server — no C reimplementation needed | `pythermalcomfort` runs on device |
| **MLX90640 driver** | Arduino/ESP-IDF library available (C only, but just raw frame capture) | Adafruit CircuitPython library (existing) |
| **Server dependency** | Required — Python processing hosted externally | None — self-contained |
| **Wi-Fi AP** | Built-in | Built-in |
| **Form factor** | Excellent — small, no SD card boot | Larger, requires SD card |
| **Consumer robustness** | High — no OS to corrupt | Lower — SD card wear, Linux boot failures |
| **Development effort** | High — full rewrite in C | Low — existing Python codebase works |

### 5.3 The RAM Question

Under the original architecture (device calls Claude directly), the ESP32 was ruled out: a 1920×1080 JPEG base64-encoded (~5–7 MB) plus TLS overhead exceeds even the largest PSRAM configuration. Under Option 4, this is no longer a constraint — the device only needs to hold the JPEG in PSRAM long enough to serve it over HTTP in chunks, which is feasible.

### 5.4 The Camera Quality Question

The OV2640 on ESP32-CAM modules maxes out at 2 MP with notably worse dynamic range and low-light performance than the Pi Camera. Since the photo is sent to Claude for visual analysis of an office space, image quality directly affects report quality. This is the strongest technical argument against the ESP32 for this application.

### 5.5 The Rewrite Question

Under the ESP32 path, the Python processing code (`pythermalcomfort`, Laplacian variance blur check) would not be rewritten in C — it would run on a server instead. The ESP32 firmware only needs to handle raw sensor reads and camera capture in C, which is well-supported by existing Arduino/ESP-IDF libraries. The phone app forwards raw sensor data and the JPEG to the server; the server returns PMV/PPD results and the blur flag; the app then calls Claude and sends the email as normal.

The trade-off introduced is a **server dependency**: the ESP32 path requires a hosted Python server to be running and reachable for every reading. The Pi path is fully self-contained with no external dependencies beyond the Claude API.

### 5.6 Recommendation

**V1: Raspberry Pi 5 (decided).** The existing Pi 5 hardware is in use for the prototype. The full existing Python codebase runs as-is. Pi 5 is overkill for this workload but eliminates any porting risk for V1.

**V2: ESP32-S3 is a strong candidate.** With heatmap rendering on the app and Python processing already on the server (required for the API key architecture), there is no C reimplementation required — the ESP32 firmware only needs to read sensors and serve raw data, which existing Arduino/ESP-IDF libraries handle well. The BOM saving (~$55–70/unit at volume), instant boot, and superior consumer form factor are compelling. The remaining trade-off is camera quality (OV2640 2MP vs Pi Camera).

---

## 6. Out of Scope (V1)

- Internal battery / offline operation
- Cloud-hosted dashboard or multi-device fleet management
- Scheduled / automatic readings (button-only trigger is intentional)
- Multiple recipient addresses
- Device joining an external Wi-Fi network (device is always the AP)
- Computer-only workflow without ethernet (Wi-Fi-only laptops cannot use the dashboard in the field)
- Motorized privacy shutter (manual slider only)
- PoE power input
- Integration with building management systems (BACnet, Modbus)
- Continuous monitoring / streaming sensor data
- User accounts or multi-user access controls
