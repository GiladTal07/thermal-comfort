import os
import json
from pathlib import Path
from datetime import datetime
from sensors import read_sensor_values, capture_photo, check_focus
from thermal_map import save_maps
from pmv_calculator import calculate_pmv, DEFAULT_CLO, DEFAULT_MET

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(_project_root, 'data')


_DATA_FILES = ['data.txt', 'image.jpg', 'thermal.png', 'thermal.json']

def capture_data(met=DEFAULT_MET, clo=DEFAULT_CLO) -> str:
    os.makedirs(DATA_DIR, exist_ok=True)
    for f in _DATA_FILES:
        p = Path(DATA_DIR) / f
        if p.exists():
            p.unlink()
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')

    print("Reading sensors...")
    air_temp, humidity, mean_radiant, thermal, air_speed, mag, sensor_faults = read_sensor_values()
    print(f"Sensors done. air_temp={air_temp} humidity={humidity} mrt={mean_radiant} air_speed={air_speed} mag={mag}")
    if sensor_faults:
        print(f"Sensor faults: {'; '.join(sensor_faults)}")

    print("Capturing photo...")
    photo_path = capture_photo('image', output_dir=DATA_DIR)
    print(f"Photo done: {photo_path}")
    sharpness, blurry = check_focus(photo_path) if photo_path else (None, False)
    if blurry:
        print(f"Warning: photo flagged as blurry (sharpness={sharpness})")

    if thermal is not None:
        print("Saving thermal map...")
        save_maps(thermal, filename='thermal', output_dir=DATA_DIR)
        with open(os.path.join(DATA_DIR, 'thermal.json'), 'w') as f:
            json.dump(thermal.tolist(), f)

    pmv = ppd = tsv = calc_notes = None
    if all(v is not None for v in [air_temp, humidity, mean_radiant, air_speed]):
        result = calculate_pmv(air_temp, humidity, mean_radiant, air_speed, clo=clo, met=met)
        pmv, ppd, tsv, calc_notes = result['pmv'], result['ppd'], result['tsv'], result['notes']

    notes_parts = []
    if sensor_faults:
        notes_parts.append("SENSOR FAULT: " + "; ".join(sensor_faults))
    if blurry:
        notes_parts.append("BLURRY PHOTO")
    if calc_notes:
        notes_parts.append(calc_notes)
    notes = " | ".join(notes_parts) if notes_parts else "No notes."

    mag_x, mag_y, mag_z = mag if mag is not None else (None, None, None)
    line = f"{timestamp} | {air_temp} | {humidity} | {mean_radiant} | {air_speed} | {pmv} | {ppd} | {tsv} | {mag_x} | {mag_y} | {mag_z} | {notes}"
    with open(os.path.join(DATA_DIR, 'data.txt'), 'w') as f:
        f.write(line + '\n')

    print("Done.")
    return DATA_DIR


if __name__ == '__main__':
    capture_data()
