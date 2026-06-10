import os
import board
import busio
import numpy as np
import adafruit_mlx90640
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy import ndimage
from datetime import datetime

def get_thermal_frame(mlx):
    frame = [0] * 768
    mlx.getFrame(frame)
    return np.array(frame).reshape((24, 32))

def save_maps(data, scale=10, filename=None, output_dir=None):
    if output_dir is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_dir =os.path.join(script_dir, 'thermal_maps')
        os.makedirs(output_dir, exist_ok=True)

    if filename is None:
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')

    vmin = data.min()
    vmax = data.max()
    upscaled = ndimage.zoom(data, scale, order=3)

    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.imshow(upscaled, cmap='inferno', vmin=vmin, vmax=vmax)
    plt.colorbar(im, label='Temperature (C)')
    ax.set_title(f"Bicubic — Min: {vmin:.1f}C Max: {vmax:.1f}C Mean: {data.mean():.1f}C")
    ax.axis('off')
    plt.tight_layout()
    filepath = os.path.join(output_dir, f"{filename}.png")
    plt.savefig(filepath, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved {filepath}")


if __name__ == '__main__':
    print("Connecting to MLX90640...")
    i2c = busio.I2C(board.SCL, board.SDA)

    mlx = adafruit_mlx90640.MLX90640(i2c)
    mlx.refresh_rate = adafruit_mlx90640.RefreshRate.REFRESH_2_HZ

    print("Capturing thermal frame...")
    data = get_thermal_frame(mlx)

    print(f"Raw frame: {data.shape[0]}x{data.shape[1]} pixels")
    print(f"Min: {data.min():.1f}C Max: {data.max():.1f}C Mean:{data.mean():.1f}C")
    print("Extrapolating...")

    save_maps(data, scale=60)
    
    print("\nDone. Image saved to thermal_maps/")
