"""
BMM150 magnetometer driver.

Pure Python port of the Bosch BMM150 Sensor API (C), covering:
- Power-on and normal-mode initialisation
- Trim register compensation for X, Y, Z axes
- Compass heading calculation

Usage:
    mag = BMM150(bus=3, offset_deg=-90.0)
    heading = mag.heading()       # 0-360°, clockwise from north
    x, y, z = mag.read()         # compensated field in µT
"""

import math
import time
import smbus2


class BMM150OverflowError(RuntimeError):
    """Raised when the sensor reports an overflow on the X or Y axis."""


class BMM150:
    # Registers
    _REG_CHIP_ID = 0x40
    _REG_DATA    = 0x42   # 8 bytes: X_LSB X_MSB Y_LSB Y_MSB Z_LSB Z_MSB RHALL_LSB RHALL_MSB
    _REG_POWER   = 0x4B
    _REG_OPMODE  = 0x4C
    _REG_TRIM    = 0x5D   # 21 bytes through 0x71

    _CHIP_ID     = 0x32
    _OVERFLOW_XY = -4096   # sentinel from Bosch API
    _OVERFLOW_Z  = -16384  # sentinel from Bosch API

    def __init__(self, bus: int, address: int = 0x13, offset_deg: float = 0.0):
        """
        Args:
            bus:        I2C bus number (e.g. 3).
            address:    I2C address (default 0x13).
            offset_deg: Mounting offset added to the computed heading so that
                        the sensor's physical orientation maps to true north.
                        Tune empirically: point the device at a known bearing,
                        read heading(), then set offset_deg = known - raw.
        """
        self._bus     = bus
        self._address = address
        self._offset  = offset_deg
        self._trim    = self._setup()

    # ------------------------------------------------------------------ setup

    def _setup(self) -> dict:
        with smbus2.SMBus(self._bus) as bus:
            bus.write_byte_data(self._address, self._REG_POWER, 0x01)  # power on
            time.sleep(0.003)

            chip_id = bus.read_byte_data(self._address, self._REG_CHIP_ID)
            if chip_id != self._CHIP_ID:
                raise RuntimeError(
                    f"BMM150 not found at 0x{self._address:02X} "
                    f"(got chip ID 0x{chip_id:02X}, expected 0x{self._CHIP_ID:02X})"
                )

            bus.write_byte_data(self._address, self._REG_OPMODE, 0x00)  # normal mode
            time.sleep(0.02)

            raw = bus.read_i2c_block_data(self._address, self._REG_TRIM, 21)

        return self._parse_trim(raw)

    @staticmethod
    def _parse_trim(raw: bytes) -> dict:
        """Parse the 21 trim bytes (0x5D-0x71) into a coefficient dict."""
        def s8(b):        return b if b < 128 else b - 256
        def u16(lo, hi):  return (hi << 8) | lo
        def s16(lo, hi):  v = u16(lo, hi); return v if v < 32768 else v - 65536

        # Offsets relative to 0x5D:
        #   [0]=0x5D  [1]=0x5E  [2-4]=reserved  [5-6]=0x62-63
        #   [7]=0x64  [8]=0x65  [9-10]=reserved  [11-12]=0x68-69
        #   [13-14]=0x6A-6B  [15-16]=0x6C-6D  [17-18]=0x6E-6F
        #   [19]=0x70  [20]=0x71
        return {
            "dig_x1":   s8(raw[0]),
            "dig_y1":   s8(raw[1]),
            "dig_z4":   s16(raw[5],  raw[6]),
            "dig_x2":   s8(raw[7]),
            "dig_y2":   s8(raw[8]),
            "dig_z2":   s16(raw[11], raw[12]),
            "dig_z1":   u16(raw[13], raw[14]),
            "dig_xyz1": ((raw[16] & 0x7F) << 8) | raw[15],
            "dig_z3":   s16(raw[17], raw[18]),
            "dig_xy2":  s8(raw[19]),
            "dig_xy1":  raw[20],
        }

    # --------------------------------------------------------------- raw read

    def _read_raw(self) -> tuple[int, int, int, int]:
        with smbus2.SMBus(self._bus) as bus:
            bus.write_byte_data(self._address, self._REG_OPMODE, 0x00)
            time.sleep(0.02)
            d = bus.read_i2c_block_data(self._address, self._REG_DATA, 8)

        # X — 13-bit signed
        raw_x = (d[1] << 5) | (d[0] >> 3)
        if raw_x & 0x1000:
            raw_x -= 0x2000

        # Y — 13-bit signed
        raw_y = (d[3] << 5) | (d[2] >> 3)
        if raw_y & 0x1000:
            raw_y -= 0x2000

        # Z — 15-bit signed
        raw_z = (d[5] << 7) | (d[4] >> 1)
        if raw_z & 0x4000:
            raw_z -= 0x8000

        # RHALL — 14-bit unsigned (Hall resistance, used in compensation)
        rhall = (d[7] << 6) | (d[6] >> 2)

        return raw_x, raw_y, raw_z, rhall

    # ------------------------------------------------- Bosch compensation (float)

    def _comp_x(self, raw_x: int, rhall: int) -> float:
        t = self._trim
        if raw_x == self._OVERFLOW_XY or rhall == 0 or t["dig_xyz1"] == 0:
            return float("nan")
        f = t["dig_xyz1"] * 16384.0 / rhall - 16384.0
        return (
            raw_x
            * ((t["dig_xy2"] * f * f / 268435456.0 + f * t["dig_xy1"] / 16384.0 + 256.0)
               * (t["dig_x2"] + 160.0))
            / 8192.0
            + t["dig_x1"] * 8.0
        ) / 16.0

    def _comp_y(self, raw_y: int, rhall: int) -> float:
        t = self._trim
        if raw_y == self._OVERFLOW_XY or rhall == 0 or t["dig_xyz1"] == 0:
            return float("nan")
        f = t["dig_xyz1"] * 16384.0 / rhall - 16384.0
        return (
            raw_y
            * ((t["dig_xy2"] * f * f / 268435456.0 + f * t["dig_xy1"] / 16384.0 + 256.0)
               * (t["dig_y2"] + 160.0))
            / 8192.0
            + t["dig_y1"] * 8.0
        ) / 16.0

    def _comp_z(self, raw_z: int, rhall: int) -> float:
        t = self._trim
        if raw_z == self._OVERFLOW_Z:
            return float("nan")
        if t["dig_z2"] == 0 or t["dig_z1"] == 0 or rhall == 0 or t["dig_xyz1"] == 0:
            return float("nan")
        return (
            (raw_z - t["dig_z4"]) * 131072.0
            - t["dig_z3"] * (rhall - t["dig_xyz1"])
        ) / ((t["dig_z2"] + t["dig_z1"] * rhall / 32768.0) * 4.0)

    # ------------------------------------------------------------------ public

    def read(self) -> tuple[float, float, float]:
        """Return compensated (x, y, z) magnetic field in µT. NaN on overflow."""
        raw_x, raw_y, raw_z, rhall = self._read_raw()
        return (
            self._comp_x(raw_x, rhall),
            self._comp_y(raw_y, rhall),
            self._comp_z(raw_z, rhall),
        )

    def heading(self) -> float:
        """
        Return compass heading in degrees (0-360, clockwise from north).

        Raises BMM150OverflowError if X or Y overflowed this read.
        Adjust offset_deg at construction time to align with true north.
        """
        x, y, _ = self.read()
        if math.isnan(x) or math.isnan(y):
            raise BMM150OverflowError("X/Y axis overflow — heading unavailable")
        deg = math.degrees(math.atan2(-y, x)) - 90.0 + self._offset
        return round(deg % 360.0, 1)
