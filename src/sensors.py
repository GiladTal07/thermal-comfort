import board
import busio
import numpy as np
import adafruit_mlx90640
import cv2
import os
import time
import subprocess
from datetime import datetime
import smbus2

_mlx90640 = None
_i2c = None

SI7021_ADDRESS = 0x40
PAV3015_ADDRESS = 0x28
BMM150_ADDRESS = 0x13
I2C_BUS = 1
BLUR_THRESHOLD = 100.0

def read_bmm150():
    with smbus2.SMBus(I2C_BUS) as bus:
        bus.write_byte_data(BMM150_ADDRESS, 0x4B, 0x01)  # power on
        time.sleep(0.003)
        bus.write_byte_data(BMM150_ADDRESS, 0x4C, 0x02)  # forced mode
        time.sleep(0.02)
        data = bus.read_i2c_block_data(BMM150_ADDRESS, 0x42, 6)
    x = ((data[1] << 5) | (data[0] >> 3))
    if x > 4095: x -= 8192
    y = ((data[3] << 5) | (data[2] >> 3))
    if y > 4095: y -= 8192
    z = ((data[5] << 7) | (data[4] >> 1))
    if z > 16383: z -= 32768
    return round(x * 0.3, 2), round(y * 0.3, 2), round(z * 0.3, 2)

def read_air_speed():
    with smbus2.SMBus(I2C_BUS) as bus:
        data = bus.read_i2c_block_data(PAV3015_ADDRESS, 0x00, 2)
    raw = (data[1] << 8) | data[0]
    return round(1e-6 * raw**2 + 5.06e-5 * raw + 1e-6, 4)

def _weighted_mrt(thermal):
    rows, cols = thermal.shape  # 24 x 32
    r = np.linspace(-1, 1, rows)
    c = np.linspace(-1, 1, cols)
    col_grid, row_grid = np.meshgrid(c, r)
    weights = np.exp(-(row_grid**2 + col_grid**2) / (2 * 0.5**2))
    weights /= weights.sum()
    return round(float(np.sum(thermal * weights)), 2)

def read_si7021():
    while not _i2c.try_lock():
        pass
    try:
        _i2c.writeto(SI7021_ADDRESS, bytes([0xFE]))  # soft reset
        time.sleep(0.05)
        _i2c.writeto(SI7021_ADDRESS, bytes([0xE3]))  # temp, hold master
        t_buf = bytearray(3)
        _i2c.readfrom_into(SI7021_ADDRESS, t_buf)
        _i2c.writeto(SI7021_ADDRESS, bytes([0xE5]))  # humidity, hold master
        h_buf = bytearray(3)
        _i2c.readfrom_into(SI7021_ADDRESS, h_buf)
    finally:
        _i2c.unlock()
    raw_t = (t_buf[0] << 8) | t_buf[1]
    raw_h = (h_buf[0] << 8) | h_buf[1]
    return round(175.72 * raw_t / 65536 - 46.85, 2), round(125 * raw_h / 65536 - 6, 2)

def init_sensors():
    global _mlx90640, _i2c
    if _mlx90640 is None:
        print("Opening I2C bus...")
        _i2c = busio.I2C(board.SCL, board.SDA)
        print("I2C bus open. Initialising MLX90640...")
        _mlx90640 = adafruit_mlx90640.MLX90640(_i2c)
        print("MLX90640 done. Setting refresh rate...")
        _mlx90640.refresh_rate = adafruit_mlx90640.RefreshRate.REFRESH_2_HZ
        print("Refresh rate set.")

def read_sensor_values():
    sensor_faults = []

    print("Initialising I2C...")
    try:
        init_sensors()
        print("I2C init done.")
    except Exception as e:
        return None, None, None, None, None, None, [f"I2C init failed: {e}"]

    thermal = None
    mrt = None
    print("Reading MLX90640...")
    try:
        frame = [0] * 768
        _mlx90640.getFrame(frame)
        thermal = np.array(frame).reshape(24, 32)
        mrt = _weighted_mrt(thermal)
        print(f"MLX90640 done. mrt={mrt}")
    except Exception as e:
        sensor_faults.append(f"MLX90640: {e}")
        print(f"MLX90640 error: {e}")

    air_temp = None
    humidity = None
    print("Reading SI7021...")
    try:
        air_temp, humidity = read_si7021()
        print(f"SI7021 done. temp={air_temp} humidity={humidity}")
    except Exception as e:
        sensor_faults.append(f"SI7021: {e}")
        print(f"SI7021 error: {e}")

    air_speed = None
    print("Reading PAV3015...")
    try:
        air_speed = read_air_speed()
        print(f"PAV3015 done. air_speed={air_speed}")
    except Exception as e:
        sensor_faults.append(f"PAV3015: {e}")
        print(f"PAV3015 error: {e}")

    mag = None
    print("Reading BMM150...")
    try:
        mag = read_bmm150()
        print(f"BMM150 done. mag={mag}")
    except Exception as e:
        sensor_faults.append(f"BMM150: {e}")
        print(f"BMM150 error: {e}")

    return air_temp, humidity, mrt, thermal, air_speed, mag, sensor_faults

def check_focus(image_path):
    img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return 0.0, True
    variance = cv2.Laplacian(img, cv2.CV_64F).var()
    return round(float(variance), 2), variance < BLUR_THRESHOLD

def capture_photo(filename=None, output_dir=None):
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'photos')

    if filename is None:
        filename = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')

    filepath = os.path.join(output_dir, f"{filename}.jpg")

    result = subprocess.run(
        ['libcamera-still', '-o', filepath,
         '--width', '1920', '--height', '1080',
         '--nopreview', '-t', '1',
         '--hflip', '--vflip'],
        capture_output=True, text=True
    )

    if result.returncode == 0:
        print(f"Photo saved: {filepath}")
        return filepath
    else:
        print(f"Camera error: {result.stderr}")
        return None

if __name__ == '__main__':
    print(read_sensor_values())
    capture_photo()
