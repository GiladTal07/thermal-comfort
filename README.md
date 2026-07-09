# Thermal Comfort Monitor

A Raspberry Pi-based device that measures environmental conditions in real time, calculates ISO 7730 thermal comfort indices, and emails an AI-generated comfort analysis. It runs a full-screen touchscreen UI: a Wi-Fi setup screen on first boot, then a live camera preview with a CAPTURE button that triggers the analysis.

## Overview

This project combines hardware sensors, the `pythermalcomfort` library, an infrared thermal camera, and the Claude API to produce a full thermal comfort report for any indoor space. On button press, the device:

1. Reads air temperature, humidity, mean radiant temperature, and air speed from onboard sensors
2. Captures a high-resolution photo of the space via the Pi camera
3. Generates a bicubic-upscaled thermal heatmap from the MLX90640 infrared array
4. Calculates PMV, PPD, and TSV per ISO 7730:2005
5. Sends all sensor data and both images to Claude for analysis
6. Emails the resulting report

## Hardware

| Component | Purpose |
|---|---|
| Raspberry Pi 5 | Host / controller |
| SI7021 | Air temperature and relative humidity |
| MLX90640 (32×24 IR array) | Mean radiant temperature + thermal heatmap |
| PAV3015 (I²C, address `0x28`) | Air speed (m/s) |
| Pi Camera (libcamera) | High-resolution photo of the space |
| BMM150 (I²C, address `0x13`, bus 3) | Compass heading |
| OSOYOO 3.5" HDMI touchscreen | Live camera preview + on-screen CAPTURE button |

## Project Structure

```
thermal-comfort/
├── src/                    # Device application code
│   ├── app.py              # Entry point: touchscreen UI, Wi-Fi setup, capture orchestration
│   ├── llm.py              # Claude API interaction, sensor data formatting, system prompt
│   ├── sensors.py          # Hardware I/O: SI7021, MLX90640, PAV3015, BMM150, Pi camera
│   ├── bmm150.py           # Custom BMM150 magnetometer driver with Bosch trim compensation
│   ├── thermal_map.py      # Generates bicubic-upscaled inferno heatmap from IR frame
│   ├── pmv_calculator.py   # PMV, PPD, TSV via pythermalcomfort (ISO 7730:2005)
│   ├── readings.py         # Orchestrates a full capture: sensors → photo → heatmap → PMV → log
│   ├── mailer.py           # HTML email dispatch via Gmail (SMTP)
│   ├── connection.py       # Wi-Fi management: scan, connect, hotspot, connectivity check
│   └── template.html       # Email report template (professional layout with appendix sections)
├── data/                   # Overwritten on every capture — only the most recent reading is kept
│   ├── data.txt            # Pipe-delimited sensor values
│   ├── image.jpg           # Pi camera photo
│   ├── thermal.png         # Bicubic-upscaled thermal heatmap
│   └── thermal.json        # Raw 24×32 float array
├── data_archive/           # Offline queue — captures saved here when no internet; sent on reconnect
└── wifi_creds.json         # Saved Wi-Fi credentials (SSID + password) for auto-connect on boot
```

## Setup

### 1. Clone the repository

```bash
cd ~
git clone https://github.com/GiladTal07/thermal-comfort
cd thermal-comfort
```

### 2. Install dependencies

```bash
sudo apt install -y python3-picamera2
pip install pythermalcomfort anthropic adafruit-blinka \
            adafruit-circuitpython-mlx90640 smbus2 \
            matplotlib scipy numpy==1.26.4 evdev Pillow \
            markdown screeninfo --break-system-packages
```

### 3. Enable I²C

```bash
sudo raspi-config  # Interface Options → I2C → Enable
```

Then add a second I²C bus for the BMM150 (isolated from the other sensors to prevent interference). Edit `/boot/firmware/config.txt`:

```bash
sudo nano /boot/firmware/config.txt
```

Add at the bottom:

```
dtoverlay=i2c-gpio,bus=3,i2c_gpio_sda=22,i2c_gpio_scl=23
```

Then reboot:

```bash
sudo reboot
```

Wire the BMM150 SDA → GPIO 22 (pin 15) and SCL → GPIO 23 (pin 16). All other sensors remain on GPIO 2/3 (I²C bus 1).

### 4. Configure environment variables

Create a `.env` file inside the project folder:

```bash
nano ~/thermal-comfort/.env
```

Add the following:

```
ANTHROPIC_API_KEY=your-anthropic-api-key
SMTP_USER=your-gmail-address@gmail.com
SMTP_PASSWORD=your-gmail-app-password
SMTP_RECIPIENT=recipient@example.com
```

Lock down the file permissions:

```bash
chmod 600 ~/thermal-comfort/.env
```

For Gmail, use an [App Password](https://support.google.com/accounts/answer/185833) rather than your account password.

### 5. Calibrate the compass heading

The BMM150 heading offset accounts for how the sensor is physically mounted relative to true north. To find the correct value:

1. Point the device at a known bearing (use your phone's compass app)
2. Run the calibration script: `python3 test-files/test_bmm150.py`
3. Note the heading it reports
4. Calculate: `offset = known_bearing - reported_heading`
5. Set `BMM150_OFFSET_DEG` in `src/sensors.py` to that value (currently defaults to `-16.0`)

### 6. Set up the systemd service

Create the service file:

```bash
sudo nano /etc/systemd/system/thermal-comfort.service
```

Paste the following, replacing `your-username` with your actual username:

```ini
[Unit]
Description=Thermal Comfort Monitor
After=graphical.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/home/your-username/thermal-comfort
EnvironmentFile=/home/your-username/thermal-comfort/.env
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/your-username/.Xauthority
ExecStart=/usr/bin/python3 -u /home/your-username/thermal-comfort/src/app.py
Restart=always
RestartSec=1

[Install]
WantedBy=graphical.target
```

Enable and start it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable thermal-comfort
sudo systemctl start thermal-comfort
```

The service will now start automatically on every boot with no monitor needed.

## Usage

### Normal operation

With the service running, the touchscreen shows a Wi-Fi setup screen on first boot. Enter the network credentials and tap **Connect**. Once connected, the live camera preview appears with a **CAPTURE** button at the bottom. Tap it to trigger a capture.

On subsequent boots the device auto-connects using saved credentials and goes straight to the camera preview. A **Wi-Fi** button appears in the bottom-right corner of the camera screen only when the device is not connected.

The app runs two threads simultaneously:

- **Capture thread** (main) — owns the UI, camera preview, sensor reading, and archiving. On button press it writes the capture to `data_archive/` and signals the Reader. It never calls the LLM or sends email directly.
- **Reader thread** (daemon) — waits for work on an internal queue, checks connectivity, calls the Claude API, and sends the email. On startup it scans `data_archive/` for any unsent captures left over from a previous session and retries them automatically.

If the device is offline when CAPTURE is pressed, the capture is archived and the Reader sends it automatically once a connection is established. If the Reader thread crashes unexpectedly, the main thread detects this and restarts it.

### Manual run (no systemd)

```bash
cd ~/thermal-comfort
python3 src/app.py
```

### Capture only (no LLM)

```bash
python3 src/readings.py
```

Each run overwrites `data/` with fixed filenames — only the most recent reading is kept:

```
data/
├── data.txt        # Pipe-delimited sensor values
├── image.jpg       # Pi camera photo
├── thermal.png     # Bicubic-upscaled thermal heatmap
└── thermal.json    # Raw 24×32 float array
```

If any individual sensor fails, the fault is recorded and the reading continues with the remaining sensors.

### Monitoring (over SSH)

```bash
# Check service status
sudo systemctl status thermal-comfort

# Watch live output
sudo journalctl -u thermal-comfort -f

# Restart after a code change
sudo systemctl restart thermal-comfort
```

## Comfort Calculation

PMV and PPD are computed using [`pythermalcomfort`](https://pythermalcomfort.readthedocs.io/) with the ISO 7730:2005 model. Default occupant parameters:

| Parameter | Default | Description |
|---|---|---|
| `met` | 1.1 | Metabolic rate (light sedentary activity) |
| `clo` | 0.61 | Clothing insulation (typical light office wear) |

Air speed from the sensor is automatically converted to relative air speed using `v_relative()` before the PMV calculation. If any input falls outside the model's validated range (air temperature outside 10–30 °C, MRT outside 10–40 °C, air speed above 1 m/s), PMV, PPD, and TSV are not calculated. The report's Appendix A will show a descriptive reason instead — for example, *Not calculated — air temperature exceeds 30 °C (malfunction)* — so the cause is always explicit.

`met` and `clo` can be overridden at runtime by passing them to `capture_data(met=..., clo=...)` or `readings.py`.

## LLM Analysis

The Claude API (`claude-sonnet-4-6`) receives:

- Labeled sensor readings (timestamp, air temp, humidity, MRT, air speed, compass heading with cardinal direction, PMV, PPD, TSV, notes)
- HQ JPEG photo of the space
- Bicubic-upscaled inferno thermal heatmap (brighter = warmer)

The report is structured in six sections:

| Section | Content |
|---|---|
| **Summary** | 2–3 sentence verdict: overall comfort level, PMV/PPD figures, one priority action |
| **Room Description** | What the camera photo shows — layout, windows, blinds, occupancy |
| **Comfort Assessment** | PMV/PPD/TSV interpreted in plain language, including a gender-differentiated comfort note |
| **Findings** | Notable observations from the heatmap and sensors (uneven surface temperatures, humidity, hot/cold zones). Compass heading and time-of-day context are only included when a window, skylight, or glazed surface is visible in the photo |
| **Recommendations** | Individual occupant actions only — blinds, personal fan, extra layer, seat change, etc. Building systems are not criticized unless a malfunction is detected. When PPD exceeds 25 %, all applicable environmental actions are listed |
| **Appendix A — Sensor Data** | Full table of raw sensor values |

The emailed report also includes **Appendix B** (room photo) and **Appendix C** (thermal heatmap) rendered in a styled appendix block, separate from the main report body.

## PMV / PPD Reference

| PMV | Thermal Sensation | Target |
|---|---|---|
| −3 | Cold | |
| −2 | Cool | |
| −1 | Slightly cool | |
| **0** | **Neutral** | ✓ |
| +1 | Slightly warm | |
| +2 | Warm | |
| +3 | Hot | |

ISO 7730 recommends keeping PMV between **−0.5 and +0.5** (PPD < 10%).

## Dependencies

- [pythermalcomfort](https://pythermalcomfort.readthedocs.io/) — ISO 7730:2005 thermal comfort calculations
- [anthropic](https://docs.anthropic.com/) — Claude API client
- [adafruit-circuitpython-mlx90640](https://github.com/adafruit/Adafruit_CircuitPython_MLX90640) — MLX90640 IR array
- [smbus2](https://pypi.org/project/smbus2/) — Direct I²C communication for PAV3015 and BMM150
- [matplotlib](https://matplotlib.org/) + [scipy](https://scipy.org/) — Thermal heatmap generation
- [picamera2](https://github.com/raspberrypi/picamera2) — Live camera preview embedded in the touchscreen UI
- [Pillow](https://python-pillow.org/) — Image conversion for the tkinter preview feed
- [evdev](https://python-evdev.readthedocs.io/) — Raw touch event input for the OSOYOO touchscreen
- [markdown](https://python-markdown.github.io/) — Converts Claude's markdown output to HTML for the email report
- [screeninfo](https://pypi.org/project/screeninfo/) — Detects connected monitor geometry for correct window placement
- [adafruit-blinka](https://github.com/adafruit/Adafruit_Blinka) — CircuitPython hardware abstraction for Raspberry Pi
