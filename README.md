# Thermal Comfort Monitor

A Raspberry Pi-based device that measures environmental conditions in real time, calculates ISO 7730 thermal comfort indices, and emails an AI-generated comfort analysis — triggered by the press of a physical button. Runs headlessly with no monitor required.

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
| Pushbutton on GPIO 17 | Trigger a reading |

## Project Structure

```
thermal-comfort/
├── src/                    # Device application code
│   ├── main.py             # Entry point: waits for button press, triggers capture + analysis
│   ├── sensors.py          # Hardware I/O: SI7021, MLX90640, PAV3015, Pi camera; blur detection
│   ├── thermal_map.py      # Generates bicubic-upscaled inferno heatmap from IR frame
│   ├── pmv_calculator.py   # PMV, PPD, TSV via pythermalcomfort (ISO 7730:2005)
│   ├── readings.py         # Orchestrates a full capture: sensors → photo → heatmap → PMV → log
│   ├── llm.py              # Sends data + images to Claude; emails the analysis
│   ├── mailer.py           # HTML email dispatch via Gmail (SMTP)
│   └── template.html       # Email report template (professional layout with appendix sections)
└── data/                   # Overwritten on every capture — only the most recent reading is kept
    ├── data.txt            # Pipe-delimited sensor values
    ├── image.jpg           # Pi camera photo
    ├── thermal.png         # Bicubic-upscaled thermal heatmap
    └── thermal.json        # Raw 24×32 float array
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
pip install pythermalcomfort anthropic adafruit-blinka adafruit-circuitpython-si7021 \
            adafruit-circuitpython-mlx90640 smbus2 gpiozero \
            matplotlib scipy numpy opencv-python markdown --break-system-packages
```

### 3. Enable I²C

```bash
sudo raspi-config  # Interface Options → I2C → Enable
sudo reboot
```

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

### 5. Set up the systemd service

Create the service file:

```bash
sudo nano /etc/systemd/system/thermal-comfort.service
```

Paste the following, replacing `your-username` with your actual username:

```ini
[Unit]
Description=Thermal Comfort Monitor
After=multi-user.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/home/your-username/thermal-comfort
EnvironmentFile=/home/your-username/thermal-comfort/.env
ExecStart=/usr/bin/python3 -u /home/your-username/thermal-comfort/src/main.py
Restart=always
RestartSec=1

[Install]
WantedBy=multi-user.target
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

With the service running, press the button on GPIO 17. The device will capture sensors + photo, call Claude, and email the report.

### Manual run (no systemd)

```bash
cd ~/thermal-comfort
python3 src/main.py
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

If the photo's Laplacian variance falls below the blur threshold (100.0), the reading is flagged `BLURRY PHOTO` in the notes field. If any individual sensor fails, the fault is recorded and the reading continues with the remaining sensors.

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

Air speed from the sensor is automatically converted to relative air speed using `v_relative()` before the PMV calculation. Input validation flags out-of-range conditions (e.g. temperature outside 10–30 °C, air speed above 1 m/s) and includes them as notes in the reading.

`met` and `clo` can be overridden at runtime by passing them to `capture_data(met=..., clo=...)` or `readings.py`.

## LLM Analysis

The Claude API (`claude-haiku-4-5`) receives:

- Labeled sensor readings (timestamp, air temp, humidity, MRT, air speed, PMV, PPD, TSV, notes)
- HQ JPEG photo of the space
- Bicubic-upscaled inferno thermal heatmap (brighter = warmer)

The report is structured in six sections, modeled on a doctor's visit summary:

| Section | Content |
|---|---|
| **Summary** | 2–3 sentence verdict: overall comfort level, PMV/PPD figures, one priority action |
| **Room Description** | What the camera photo shows — layout, windows, blinds, occupancy |
| **Comfort Assessment** | PMV/PPD/TSV interpreted in plain language against ISO 7730 bands |
| **Findings** | Notable observations from the heatmap and sensors (radiant asymmetry, humidity, hot/cold zones) |
| **Recommendations** | Individual occupant actions only — blinds, personal fan, extra layer, seat change, etc. Building systems are not criticized unless a malfunction is detected |
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
- [adafruit-circuitpython-si7021](https://github.com/adafruit/Adafruit_CircuitPython_SI7021) — SI7021 temperature/humidity sensor
- [adafruit-circuitpython-mlx90640](https://github.com/adafruit/Adafruit_CircuitPython_MLX90640) — MLX90640 IR array
- [smbus2](https://pypi.org/project/smbus2/) — I²C communication for PAV3015 air speed sensor
- [gpiozero](https://gpiozero.readthedocs.io/) — GPIO button input
- [matplotlib](https://matplotlib.org/) + [scipy](https://scipy.org/) — Thermal heatmap generation
- [opencv-python](https://pypi.org/project/opencv-python/) — Laplacian variance blur detection on camera photos
- [markdown](https://python-markdown.github.io/) — Converts Claude's markdown output to HTML for the email report
- [adafruit-blinka](https://github.com/adafruit/Adafruit_Blinka) — CircuitPython hardware abstraction for Raspberry Pi
