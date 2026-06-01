# Thermal Comfort Monitor

A Raspberry Pi-based device that measures environmental conditions in real time, calculates ISO 7730 thermal comfort indices, and emails an AI-generated comfort analysis — triggered by the press of a physical button.

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
| Raspberry Pi (any model with I²C + GPIO) | Host / controller |
| SI7021 | Air temperature and relative humidity |
| MLX90640 (32×24 IR array) | Mean radiant temperature + thermal heatmap |
| PAV3015 (I²C, address `0x28`) | Air speed (m/s) |
| Pi Camera (libcamera) | High-resolution photo of the space |
| Pushbutton on GPIO 17 | Trigger a reading |

## Project Structure

```
thermal-comfort/
├── sensors.py          # Hardware I/O: reads SI7021, MLX90640, PAV3015, Pi camera
├── thermal_map.py      # Generates bicubic-upscaled inferno heatmap from IR frame
├── pmv_calculator.py   # Calculates PMV, PPD, TSV via pythermalcomfort (ISO 7730:2005)
├── readings.py         # Orchestrates a full capture: sensors → photo → heatmap → PMV → log
├── llm.py              # Sends data + images to Claude; emails the analysis
└── mailer.py           # SMTP email dispatch via Gmail
```

## Setup

### 1. Install dependencies

```bash
pip install pythermalcomfort anthropic adafruit-circuitpython-si7021 \
            adafruit-circuitpython-mlx90640 smbus2 gpiozero \
            matplotlib scipy numpy
```

### 2. Enable I²C on the Pi

```bash
sudo raspi-config  # Interface Options → I2C → Enable
```

### 3. Configure environment variables

The following environment variables must be set before running:

```bash
export ANTHROPIC_API_KEY="your-anthropic-api-key"
export SMTP_USER="your-gmail-address@gmail.com"
export SMTP_PASSWORD="your-gmail-app-password"
export SMTP_RECIPIENT="recipient@example.com"
```

For Gmail, use an [App Password](https://support.google.com/accounts/answer/185833) rather than your account password.

## Usage

### Button-triggered (hardware)

With a button wired to GPIO 17:

```bash
python llm.py
# Waiting for button press...
```

Press the button — the device captures a full reading, runs the analysis, and sends the email.

### Manual run on an existing data folder

If you already have a captured data folder (e.g. from running `readings.py` directly):

```bash
python llm.py data/2025-01-15_14-30-00
```

### Capture only (no LLM)

To take a reading and save the data without running the analysis:

```bash
python readings.py
```

Each run saves its output to `data/<timestamp>/` containing:

```
data/2025-01-15_14-30-00/
├── readings.txt          # Pipe-delimited sensor log
├── 2025-01-15_14-30-00.jpg  # Pi camera photo
└── 2025-01-15_14-30-00.png  # Thermal heatmap
```

## Comfort Calculation

PMV and PPD are computed using [`pythermalcomfort`](https://pythermalcomfort.readthedocs.io/) with the ISO 7730:2005 model. Default occupant parameters:

| Parameter | Default | Description |
|---|---|---|
| `met` | 1.1 | Metabolic rate (light sedentary activity) |
| `clo` | 0.61 | Clothing insulation (typical light office wear) |

Air speed from the sensor is automatically converted to relative air speed using `v_relative()` before the PMV calculation.

Input validation flags out-of-range conditions (e.g. temperature outside 10–30 °C, air speed above 1 m/s) and includes them as notes in the reading.

## LLM Analysis

The Claude API (`claude-haiku-4-5`) receives:

- Labeled sensor readings (timestamp, air temp, humidity, MRT, air speed, PMV, PPD, TSV, notes)
- HQ JPEG photo of the space
- Bicubic-upscaled inferno thermal heatmap (brighter = warmer)

Claude is prompted as a thermal comfort expert and asked to cover: current comfort level based on PMV/PPD, temperature distribution and hot/cold spots in the heatmap, observations from the photo, and actionable recommendations.

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
