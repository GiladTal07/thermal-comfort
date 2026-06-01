import board
import busio
import numpy as np
import adafruit_si7021
import adafruit_mlx90640
import os
import subprocess
from datetime import datetime
import smbus2

_si7021 = None
_mlx90640 = None

PAV3015_ADDRESS = 0x28
I2C_BUS = 1

def read_air_speed():
	# Read air velocity from PAV3015. Returns speed in ms
	with smbus2.SMBus(I2C_BUS) as bus:
		data = bus.read_i2c_block_data(PAV3015_ADDRESS, 0x00, 2)

	raw = (data[1] << 8) | data[0]
	return round(1e-6 * raw**2 + 5.06e-5 * raw + 1e-6, 4)

def init_sensors():
	global _si7021, _mlx90640
	if _si7021 is None or _mlx90640 is None:
		i2c = busio.I2C(board.SCL, board.SDA)
		_si7021 = adafruit_si7021.SI7021(i2c)
		_mlx90640 = adafruit_mlx90640.MLX90640(i2c)
		_mlx90640.refresh_rate = adafruit_mlx90640.RefreshRate.REFRESH_2_HZ

def read_sensor_values():
	init_sensors()
	frame = [0] * 768
	_mlx90640.getFrame(frame)
	thermal = np.array(frame).reshape(24, 32)
	air_temp = round(_si7021.temperature, 2)
	humidity = round(_si7021.relative_humidity, 2)
	mrt = round(float(np.mean(thermal)), 2)
	air_speed = read_air_speed()
	return air_temp, humidity, mrt, thermal, air_speed

def capture_photo(timestamp=None, output_dir=None):
	if output_dir is None:
		output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'photos')
	
	if timestamp is None:
		timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
		
	filename = timestamp.replace(' ', '_').replace(':', '-') + '.jpg'
	filepath = os.path.join(output_dir, filename)
	
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
