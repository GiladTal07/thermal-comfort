# Hardware Wiring

## Component Summary

| Component | Interface | I²C Address | Bus |
|---|---|---|---|
| SI7021 | I²C | `0x40` | Bus 1 — GPIO 2/3 |
| MLX90640 | I²C | `0x33` | Bus 1 — GPIO 2/3 |
| PAV3015 | I²C | `0x28` | Bus 1 — GPIO 2/3 |
| BMM150 | I²C | `0x13` | Bus 3 — GPIO 22/23 |
| Pi Camera | CSI ribbon | — | CAM connector |
| OSOYOO 3.5" touchscreen | HDMI + USB | — | HDMI + USB port |

The SI7021, MLX90640, and PAV3015 share I²C bus 1. The BMM150 is isolated on a separate software-emulated I²C bus (bus 3) to prevent address conflicts and interference.

---

## GPIO Header

Only the pins used by this project are labelled. All other pins can be left unconnected.

```
        3V3  [01] [02]  5V       ┐
SDA / GPIO2  [03] [04]  5V       │ covered by STEMMA QT PCB
SCL / GPIO3  [05] [06]  GND      ┘
             [07] [08]
        GND  [09] [10]
             [11] [12]
             [13] [14]  GND
GPIO22 / SDA [15] [16]  GPIO23 / SCL   ← bus 3 (BMM150)
        3V3  [17] [18]
             [19] [20]  GND
             [21] [22]
             [23] [24]
        GND  [25] [26]
             [27] [28]
             [29] [30]  GND
             [31] [32]
             [33] [34]  GND
             [35] [36]
             [37] [38]
        GND  [39] [40]
```

**Bus 1** — pins 3 (SDA) and 5 (SCL): SI7021, MLX90640, PAV3015 — accessed via STEMMA QT PCB  
**Bus 3** — pins 15 (SDA) and 16 (SCL): BMM150 — wired directly  
**3.3V** — pins 1 and 17  
**GND** — pins 6, 9, 14, 20, 25, 30, 34, 39

---

## I²C Bus 1 — SI7021, MLX90640, PAV3015

Bus 1 connections are made through an **Adafruit Pi STEMMA QT Breakout for Raspberry Pi (#6365)**. This board plugs onto GPIO pins 1-6 and exposes the I²C bus 1 signals (3.3V, GND, SDA, SCL) as STEMMA QT (JST SH 1mm 4-pin) connectors. All three bus 1 sensors plug directly into the breakout board via STEMMA QT cables — no individual wires to the GPIO header are needed for these sensors.

STEMMA QT pinout (standard, left to right): **GND — 3.3V — SDA — SCL**

### SI7021 (temperature + humidity)

Connect with a STEMMA QT cable to any port on the breakout board.

### MLX90640 (IR thermal array)

Connect with a STEMMA QT cable to any port on the breakout board.

### PAV3015 (air speed)

Connect with a STEMMA QT cable to any port on the breakout board.

> **Pull-up resistors**: I²C requires pull-ups on SDA and SCL. The Adafruit breakout board and most sensor breakout boards include these — no external resistors are needed.

---

## I²C Bus 3 — BMM150 (compass)

Bus 3 is a software-emulated I²C bus created by the `i2c-gpio` device tree overlay (see [README.md](README.md#3-enable-ic)). It uses GPIO 22 as SDA and GPIO 23 as SCL.

| Sensor pin | Connects to | Notes |
|---|---|---|
| VCC | Pin 17 (3.3V) | |
| GND | Pin 20 or 25 (GND) | |
| SDA | Pin 15 (GPIO 22) | Bus 3 data |
| SCL | Pin 16 (GPIO 23) | Bus 3 clock |
| CSB / ADDR | GND | Sets I²C address to `0x13` |
| DRDY | Not connected | Driver polls; data-ready pin unused |

> **Mounting orientation**: the BMM150's X and Y axes must be roughly horizontal (parallel to the floor) for heading to be meaningful. The `BMM150_OFFSET_DEG` constant in `sensors.py` corrects for how the sensor is rotated within the enclosure — see the calibration step in the README.

---

## Pi Camera

Connect the camera ribbon cable to the **CAM/MIPI** connector on the Raspberry Pi 5. The cable's metal contacts must face toward the board's connector contacts. Push the ribbon in flat, then press the latch down to lock it.

The app uses `libcamera-still` to capture frames at 1920×1080. No additional wiring is needed beyond the ribbon.

---

## OSOYOO 3.5" Touchscreen

| Cable | Connects to |
|---|---|
| HDMI | Any HDMI port on the Pi 5 |
| USB (touch input) | Any USB port on the Pi 5 |

The display draws power over the HDMI or USB connection — no separate power cable is needed. The touch input appears as a Linux input device; the app discovers it automatically at startup by scanning `/dev/input/` for a device that reports absolute touch coordinates.

---

## Verifying Connections

After wiring and booting, use `i2cdetect` to confirm each device is visible:

```bash
# Bus 1 — should show 0x28 (PAV3015), 0x33 (MLX90640), 0x40 (SI7021)
i2cdetect -y 1

# Bus 3 — should show 0x13 (BMM150)
i2cdetect -y 3
```

Expected output for bus 1:

```
     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:
10:
20:                         28
30:                   33
40: 40
...
```

If an address is missing, check power, GND, SDA, and SCL for that sensor. If bus 3 is empty, confirm the `dtoverlay=i2c-gpio` line is in `/boot/firmware/config.txt` and the Pi has been rebooted.
