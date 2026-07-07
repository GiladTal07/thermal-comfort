"""
Standalone SI7021 test — run with only the SI7021 connected.
Tries smbus2 and busio approaches so we can see which one works.

Usage:
    python3 test_si7021.py
"""

import time

SI7021_ADDRESS = 0x40
I2C_BUS = 1


def test_smbus2_nohold():
    print("\n--- smbus2 / no-hold mode ---")
    import smbus2
    with smbus2.SMBus(I2C_BUS) as bus:
        bus.write_byte(SI7021_ADDRESS, 0xFE)        # soft reset
        time.sleep(0.05)
        bus.write_byte(SI7021_ADDRESS, 0xF3)        # trigger temp, no-hold
        raw_t = None
        for attempt in range(20):
            time.sleep(0.01)
            try:
                data = bus.read_i2c_block_data(SI7021_ADDRESS, 0xF3, 3)
                raw_t = (data[0] << 8) | data[1]
                print(f"  temp read succeeded on attempt {attempt + 1}")
                break
            except OSError as e:
                print(f"  attempt {attempt + 1}: NACK ({e})")
        if raw_t is None:
            print("  FAILED: temperature timed out")
            return

        bus.write_byte(SI7021_ADDRESS, 0xF5)        # trigger humidity, no-hold
        raw_h = None
        for attempt in range(20):
            time.sleep(0.01)
            try:
                data = bus.read_i2c_block_data(SI7021_ADDRESS, 0xF5, 3)
                raw_h = (data[0] << 8) | data[1]
                print(f"  humidity read succeeded on attempt {attempt + 1}")
                break
            except OSError as e:
                print(f"  attempt {attempt + 1}: NACK ({e})")
        if raw_h is None:
            print("  FAILED: humidity timed out")
            return

    temp = round(175.72 * raw_t / 65536 - 46.85, 2)
    hum  = round(125    * raw_h / 65536 - 6,     2)
    print(f"  Temperature: {temp} °C   Humidity: {hum} %")


def test_smbus2_hold():
    print("\n--- smbus2 / hold master mode ---")
    import smbus2
    from smbus2 import i2c_msg
    with smbus2.SMBus(I2C_BUS) as bus:
        bus.write_byte(SI7021_ADDRESS, 0xFE)        # soft reset
        time.sleep(0.05)

        bus.i2c_rdwr(i2c_msg.write(SI7021_ADDRESS, [0xE3]))
        t_msg = i2c_msg.read(SI7021_ADDRESS, 3)
        bus.i2c_rdwr(t_msg)

        bus.i2c_rdwr(i2c_msg.write(SI7021_ADDRESS, [0xE5]))
        h_msg = i2c_msg.read(SI7021_ADDRESS, 3)
        bus.i2c_rdwr(h_msg)

    raw_t = (list(t_msg)[0] << 8) | list(t_msg)[1]
    raw_h = (list(h_msg)[0] << 8) | list(h_msg)[1]
    temp = round(175.72 * raw_t / 65536 - 46.85, 2)
    hum  = round(125    * raw_h / 65536 - 6,     2)
    print(f"  Temperature: {temp} °C   Humidity: {hum} %")


def test_busio_nohold():
    print("\n--- busio / no-hold mode ---")
    import board, busio
    i2c = busio.I2C(board.SCL, board.SDA)
    while not i2c.try_lock():
        pass
    try:
        i2c.writeto(SI7021_ADDRESS, bytes([0xFE]))  # soft reset
        time.sleep(0.05)

        i2c.writeto(SI7021_ADDRESS, bytes([0xF3]))  # temp, no-hold
        t_buf = bytearray(3)
        for attempt in range(20):
            time.sleep(0.01)
            try:
                i2c.readfrom_into(SI7021_ADDRESS, t_buf)
                print(f"  temp read succeeded on attempt {attempt + 1}")
                break
            except OSError as e:
                print(f"  attempt {attempt + 1}: NACK ({e})")
        else:
            print("  FAILED: temperature timed out")
            return

        i2c.writeto(SI7021_ADDRESS, bytes([0xF5]))  # humidity, no-hold
        h_buf = bytearray(3)
        for attempt in range(20):
            time.sleep(0.01)
            try:
                i2c.readfrom_into(SI7021_ADDRESS, h_buf)
                print(f"  humidity read succeeded on attempt {attempt + 1}")
                break
            except OSError as e:
                print(f"  attempt {attempt + 1}: NACK ({e})")
        else:
            print("  FAILED: humidity timed out")
            return
    finally:
        i2c.unlock()

    raw_t = (t_buf[0] << 8) | t_buf[1]
    raw_h = (h_buf[0] << 8) | h_buf[1]
    temp = round(175.72 * raw_t / 65536 - 46.85, 2)
    hum  = round(125    * raw_h / 65536 - 6,     2)
    print(f"  Temperature: {temp} °C   Humidity: {hum} %")


if __name__ == "__main__":
    print("SI7021 isolation test")
    print("=====================")

    try:
        import smbus2 as _smbus2
        with _smbus2.SMBus(I2C_BUS) as _bus:
            _bus.write_byte_data(0x13, 0x4B, 0x01)  # suspend → sleep
            time.sleep(0.003)
            _bus.write_byte_data(0x13, 0x4C, 0x00)  # sleep → normal mode
        time.sleep(0.1)
        print("BMM150 in normal mode\n")
    except Exception as _e:
        print(f"BMM150 wake skipped: {_e}\n")

    for name, fn in [
        ("smbus2 no-hold",   test_smbus2_nohold),
        ("smbus2 hold",      test_smbus2_hold),
        ("busio no-hold",    test_busio_nohold),
    ]:
        try:
            fn()
        except Exception as e:
            print(f"  EXCEPTION: {e}")
