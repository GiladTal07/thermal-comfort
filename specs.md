# Consumer Product Specification — Thermal Comfort Monitor

## 1. Hardware

### 1.1 Core Platform
- **V1: Raspberry Pi 5** (existing hardware, prototype in use). Full Python codebase runs as-is; no porting required.
- Consumer product target: replace Pi 5 with a custom PCB. Raspberry Pi Zero 2W or CM4 are the natural Pi-based options; ESP32-S3 is the V2 candidate (see PRD §5).
- ESP32-S3 note: heatmap rendering is on the app and Python processing is already on the server (required for API key architecture), so migrating to ESP32 would only require C drivers for raw sensor reads — no Python reimplementation. See PRD §5 for full comparison.
- All I²C lines should have ESD protection diodes and 4.7 kΩ pull-ups on the PCB
- Dedicated 3.3 V LDO for sensors, isolated from noisy rails

### 1.2 Sensors
| Sensor | Current | Consumer requirement |
|---|---|---|
| SI7021 (temp/humidity) | Adafruit breakout | Reflow-mounted on PCB |
| MLX90640 (32×24 IR array) | Adafruit breakout | Reflow-mounted; field-of-view aperture in enclosure |
| PAV3015 (air speed) | I²C via SMBus | Exposed port in enclosure with mesh guard |
| Pi Camera | libcamera ribbon cable | Fixed-focus module mounted behind flush lens cutout |

- Add calibration traceability: each unit should store its per-sensor calibration offset in non-volatile storage (EEPROM or flash), set at the factory
- Verify PAV3015 formula against NIST-traceable reference before production

### 1.3 Enclosure
- Material: polycarbonate or ABS-PC blend (impact-resistant, paintable)
- Mounting: magnetic wall mount + desk stand, both included
- Camera: flush recessed lens with privacy shutter the user can close
- IR window: IR-transparent cover (polyethylene film or bare aperture) over the MLX90640 field of view
- Air speed port: open mesh grille, no obstruction within 30 mm
- Indicator: RGB LED visible through diffused window (status, reading in progress, ready, error)
- Physical button: optional for V1 — primary trigger is the phone app; button may be added as a convenience but is not required
- Dimensions target: ≤ 120 × 80 × 40 mm

### 1.4 Power
- Input: USB-C PD (5 V / 2 A minimum), wall adapter in box
- No internal battery required for V1; V2 could add a small LiPo for brief outage survival
- Idle power target: < 3 W
- RGB LED state to indicate boot / ready / error

---

## 2. Device Software

### 2.1 Wi-Fi Access Point
- Device always broadcasts its own Wi-Fi AP (`ThermalComfort-XXXX`, last four chars of MAC)
- Device never joins an external Wi-Fi network — it is always the AP
- AP secured with WPA2; default password printed on device label, changeable from app
- Device runs a lightweight HTTP server on the AP interface (see §2.2)

### 2.2 Device HTTP Server
- Serves all data and files to the phone app over the AP connection
- Required endpoints:
  - `GET /status` — device state (idle, capturing, ready, error) + firmware version
  - `GET /reading/latest` — JSON of most recent reading (all sensor fields, PMV, PPD, TSV, notes, blurry flag, sensor fault flag)
  - `GET /reading/latest/photo` — JPEG, served with range-request support
  - `GET /reading/latest/heatmap` — PNG, served with range-request support
  - `GET /readings` — JSON array of all stored readings (metadata only)
  - `POST /trigger` — initiates a capture sequence
  - `POST /config` — accepts met/clo override values for the next reading
- No credentials stored on device; HTTP server is unauthenticated within the AP (WPA2 is the access control)

### 2.3 Error Handling & Resilience (Device)
- Service restarts on crash via systemd; no reboot required to recover from a failed reading
- Sensor read failures: log the fault, complete the reading with remaining sensors, include `sensor_fault` field in JSON
- All errors logged to systemd journal with severity and timestamp, and surfaced via `GET /status`

### 2.4 Data Storage
- All readings stored in SQLite (`data/readings.db`, managed by `data/db.py`) with fields: timestamp, air_temp, humidity, mrt, air_speed, pmv, ppd, tsv, notes, blurry, sensor_fault, photo_path, thermal_path
- Retain at least 90 days of readings; prune older entries automatically

### 2.5 Firmware Updates
- Firmware updated manually by connecting the device to a computer via USB and flashing with standard tooling (e.g. `rpiboot` + `dd`, or Raspberry Pi Imager)
- No OTA mechanism required; updates are infrequent and performed by the developer

### 2.6 Web Dashboard (Secondary — Computer Only)
- Read-only dashboard served at `http://192.168.4.1` for laptop users with ethernet (Wi-Fi to device AP + ethernet for internet)
- Displays: device status, last reading result, reading history table, CSV export
- Cannot trigger a full analysis (no Claude API access); may trigger capture-only via `POST /trigger`
- No SSH access required for any normal operation

---

## 3. Phone App

### 3.1 Platform
- **iOS and Android** both required for V1
- iOS: dual networking via `NEHotspotConfiguration`
- Android: dual networking via `WifiNetworkSpecifier`
- Framework choice (React Native, Flutter, or separate native projects) to be decided during Phase 4

### 3.2 Connection & Dual Networking
- App connects to device AP using platform APIs that maintain cellular internet simultaneously — no network switching required for the user
- App auto-detects `ThermalComfort-XXXX` SSIDs and prompts user to connect
- App polls `GET /status` every 2 seconds while connected to detect new readings

### 3.3 AI Analysis
- App fetches sensor JSON, JPEG, and PNG from device over AP connection
- App calls Claude API over cellular with labeled sensor data and both images
- Static system prompt uses `cache_control` for prompt caching to reduce per-call cost
- Exponential backoff retry on API failure (initial 5 s, max 3 retries)

### 3.4 Report Delivery
- App sends HTML email with AI analysis, sensor readings, and both images embedded inline (CID references)
- Plain-text fallback included for clients that block HTML
- Subject line includes comfort summary readable in notification preview
- Single configured recipient; address shown and editable on the app's main screen

### 3.5 Credentials & Security
- **Anthropic API key** stored on the analysis server only — never in the app or on the device
- **SMTP credentials** stored in platform secure storage (iOS Keychain / Android Keystore)
- Device holds no credentials of any kind

### 3.6 Configuration
- met/clo presets with plain-language labels (e.g. "Seated desk work", "Standing / light movement", "Summer clothing", "Winter clothing") plus manual numeric input
- Recipient email editable inline on main screen
- Reading history view with CSV export

---

## 4. Analysis Server

### 4.1 Hosting
- Personal server (VPS or home server) — not a shared cloud service
- Must be reachable over HTTPS from the phone app

### 4.2 Responsibilities
- Accepts POST from the app containing sensor JSON, JPEG, and raw 24×32 thermal frame
- Renders heatmap PNG from raw thermal frame (existing `thermal_map.py`)
- Calls Claude API with sensor data, JPEG, and heatmap PNG
- Returns analysis text to the app
- Holds Anthropic API key in environment variable or secrets manager

### 4.3 Codebase
- Runs existing Python codebase (`thermal_map.py`, `llm.py` refactored as an HTTP endpoint)
- This is the natural home for the Python processing when migrating to ESP32 in V2

---

## 6. AI & Analysis

### 4.1 Model
- `claude-haiku-4-5` is appropriate for cost at scale; evaluate `claude-sonnet-4-6` if analysis quality becomes a differentiator
- Prompt caching on static system prompt reduces per-report API cost

### 4.2 MRT Calculation
- Current naive pixel mean includes walls/ceiling/floor — not acceptable for production
- Weight by solid angle or restrict to the occupied-zone pixel region
- Document the assumption in the product literature

### 4.3 Report Content
- Summary line at top of email readable in notification preview
- Analysis covers: PMV/PPD comfort level, heatmap hot/cold spots, camera photo observations, actionable recommendations, and a note on occupant variability (age, sex, BMI, acclimatisation)

---

## 7. Regulatory & Safety

### 5.1 Electrical Safety
- UL 62368-1 (North America) or IEC 62368-1 (international) certification for device + power adapter
- Adapter must carry relevant marks (UL, CE, PSE, etc.) for target markets

### 5.2 Radio / EMC
- FCC Part 15 (USA) for Wi-Fi radio
- CE RED directive (EU) for Wi-Fi
- IC certification (Canada) if sold there
- Note: Bluetooth certification not required if BLE is not used in V1

### 5.3 Environmental
- RoHS 3 (EU 2015/863) compliance
- WEEE registration for EU sales

### 5.4 Camera
- Physical privacy shutter on camera aperture
- Camera-active indicator LED hardwired — cannot be disabled by software

---

## 8. Manufacturing

### 6.1 Bill of Materials
- Finalize component selection with at least one alternate source for SI7021, MLX90640, PAV3015
- Target BOM cost < $80 at 1 000-unit volume

### 6.2 Calibration
- Factory calibration of SI7021 offset and PAV3015 polynomial coefficients
- Calibration values written to on-device EEPROM
- Calibration certificate stored in production database, retrievable by serial number

### 6.3 Functional Test
- End-of-line test fixture verifies: all I²C sensors respond, camera captures a valid frame, AP broadcasts and a test client can connect, HTTP server responds to all endpoints, LED cycles through all states, firmware version matches expected release
- A test report generated by connecting the test rig's phone to the AP and completing a full capture → fetch → Claude → email cycle

### 6.4 Packaging
- Box includes: device, USB-C cable (1.5 m), wall adapter, magnetic mount + screws, desk stand, quick-start card with QR code to setup guide

---

## 9. API Cost Model

- API costs (Claude + outbound email) are incurred by the phone app using the user's own Anthropic API key
- At Haiku pricing (~$0.001 per report including images), 4 reports/day ≈ $1.50/month
- Business model options: user supplies own API key (lowest cost to ship), or device ships with bundled credits

---

## 10. Open Items / Decisions Required

- [x] App platform: **iOS + Android**
- [x] SBC: **Raspberry Pi 5** for V1; ESP32-S3 evaluated for V2
- [x] Business model: **user's own API key on personal server**
- [x] Target market: **B2B — office buildings**
- [ ] PAV3015 quadratic formula validation against NIST reference
- [ ] Privacy shutter: manual slider vs motorized
- [ ] Multi-room: single device per room vs hub-and-spoke
- [ ] App framework: React Native / Flutter vs separate native Swift + Kotlin projects
