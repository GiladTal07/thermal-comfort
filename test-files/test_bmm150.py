"""
BMM150 magnetometer test — reports compass heading (degrees from magnetic north).

Usage:
    python3 test_bmm150.py
"""

import smbus2
import time
import math

BMM150_ADDRESS = 0x13
I2C_BUS = 3

CARDINALS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']


def cardinal(deg):
    return CARDINALS[round(deg / 45) % 8]


def s8(v):
    return v if v <= 127 else v - 256


def read_trim_data(bus):
    t   = bus.read_i2c_block_data(BMM150_ADDRESS, 0x5D, 2)
    tz  = bus.read_i2c_block_data(BMM150_ADDRESS, 0x62, 4)
    txy = bus.read_i2c_block_data(BMM150_ADDRESS, 0x68, 10)
    return {
        'x1':   s8(t[0]),
        'y1':   s8(t[1]),
        'x2':   s8(tz[2]),
        'y2':   s8(tz[3]),
        'z1':   (txy[3] << 8) | txy[2],
        'z2':   (txy[1] << 8) | txy[0],
        'z3':   (txy[7] << 8) | txy[6],
        'z4':   (tz[1]  << 8) | tz[0],
        'xy1':  txy[9],
        'xy2':  s8(txy[8]),
        'xyz1': ((txy[5] & 0x7F) << 8) | txy[4],
    }


def compensate_x(raw_x, raw_r, trim):
    if raw_x == -4096:
        return -32768
    r = raw_r if raw_r != 0 else trim['xyz1']
    if r == 0:
        return -32368
    c0 = trim['xyz1'] * 16384 // r - 0x4000
    c1 = trim['xy2'] * (c0 * c0 // 128) + c0 * trim['xy1'] * 128
    c2 = (trim['x2'] + 0xA0) * (c1 // 512 + 0x100000) // 4096
    return (raw_x * c2 // 8192 + trim['x1'] * 8) // 16


def compensate_y(raw_y, raw_r, trim):
    if raw_y == -4096:
        return -32768
    r = raw_r if raw_r != 0 else trim['xyz1']
    if r == 0:
        return -32368
    c0 = trim['xyz1'] * 16384 // r - 0x4000
    c1 = trim['xy2'] * (c0 * c0 // 128) + c0 * trim['xy1'] * 128
    c2 = (trim['y2'] + 0xA0) * (c1 // 512 + 0x100000) // 4096
    return (raw_y * c2 // 8192 + trim['y1'] * 8) // 16


def wake(bus):
    bus.write_byte_data(BMM150_ADDRESS, 0x4B, 0x01)
    time.sleep(0.003)
    bus.write_byte_data(BMM150_ADDRESS, 0x4C, 0x00)
    time.sleep(0.02)


def read_axes(bus, trim):
    data = bus.read_i2c_block_data(BMM150_ADDRESS, 0x42, 8)

    raw_x = (data[1] << 5) | (data[0] >> 3)
    if raw_x & 0x1000:
        raw_x -= 0x2000

    raw_y = (data[3] << 5) | (data[2] >> 3)
    if raw_y & 0x1000:
        raw_y -= 0x2000

    raw_r = (data[7] << 6) | (data[6] >> 2)

    cx = compensate_x(raw_x, raw_r, trim)
    cy = compensate_y(raw_y, raw_r, trim)

    return cx, cy


def heading(x, y):
    deg = math.degrees(math.atan2(x, y))
    if deg < 0:
        deg += 360
    return round(deg, 1)


with smbus2.SMBus(I2C_BUS) as bus:
    chip_id = bus.read_byte_data(BMM150_ADDRESS, 0x40)
    if chip_id == 0x32:
        print("BMM150 found (chip ID 0x32)")
    else:
        print(f"Warning: unexpected chip ID 0x{chip_id:02X} (expected 0x32) — check wiring")

    wake(bus)
    trim = read_trim_data(bus)
    print(f"Trim data loaded: xyz1={trim['xyz1']}  x1={trim['x1']}  y1={trim['y1']}")
    print("Reading... press Ctrl+C to stop.\n")

    try:
        while True:
            x, y = read_axes(bus, trim)
            h = heading(x, y)
            print(f"  {h:6.1f}°  {cardinal(h):<2}   (cx={x:+8.1f}  cy={y:+8.1f})")
            time.sleep(1.0)
    except KeyboardInterrupt:
        print()