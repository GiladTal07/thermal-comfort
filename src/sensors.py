import board
import busio
import numpy as np
import adafruit_si7021
import adafruit_mlx90640
import cv2
import os
import subprocess
from datetime import datetime
import smbus2

_si7021 = None
_mlx90640 = None

PAV3015_ADDRESS = 0x28
I2C_BUS = 1
BLUR_THRESHOLD = 100.0

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

def init_sensors():
    global _si7021, _mlx90640
    if _si7021 is None or _mlx90640 is None:
        i2c = busio.I2C(board.SCL, board.SDA)
        _si7021 = adafruit_si7021.SI7021(i2c)
        _mlx90640 = adafruit_mlx90640.MLX90640(i2c)
        _mlx90640.refresh_rate = adafruit_mlx90640.RefreshRate.REFRESH_2_HZ

def read_sensor_values():
    sensor_faults = []

    try:
        init_sensors()
    except Exception as e:
        return None, None, None, None, None, [f"I2C init failed: {e}"]

    thermal = None
    mrt = None
    try:
        frame = [0] * 768
        _mlx90640.getFrame(frame)
        thermal = np.array(frame).reshape(24, 32)
        mrt = _weighted_mrt(thermal)
    except Exception as e:
        sensor_faults.append(f"MLX90640: {e}")

    air_temp = None
    humidity = None
    try:
        air_temp = round(_si7021.temperature, 2)
        humidity = round(_si7021.relative_humidity, 2)
    except Exception as e:
        sensor_faults.append(f"SI7021: {e}")

    air_speed = None
    try:
        air_speed = read_air_speed()
    except Exception as e:
        sensor_faults.append(f"PAV3015: {e}")

    return air_temp, humidity, mrt, thermal, air_speed, sensor_faults

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
         '--nopreview', '-t', '1'],
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
