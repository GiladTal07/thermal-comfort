import os
from datetime import datetime
from sensors import read_sensor_values, capture_photo, check_focus
from thermal_map import save_maps
from pmv_calculator import calculate_pmv, DEFAULT_CLO, DEFAULT_MET

def capture_data(met=DEFAULT_MET, clo=DEFAULT_CLO) -> str:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    run_dir = os.path.join(script_dir, 'data', timestamp)
    os.makedirs(run_dir)

    air_temp, humidity, mean_radiant, thermal, air_speed, sensor_faults = read_sensor_values()
    if sensor_faults:
        print(f"Sensor faults: {'; '.join(sensor_faults)}")

    photo_path = capture_photo(timestamp, output_dir=run_dir)
    sharpness, blurry = check_focus(photo_path) if photo_path else (None, False)
    if blurry:
        print(f"Warning: photo flagged as blurry (sharpness={sharpness})")

    if thermal is not None:
        save_maps(thermal, filename=timestamp, output_dir=run_dir)

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

    line = f"{timestamp} | {air_temp} | {humidity} | {mean_radiant} | {air_speed} | {pmv} | {ppd} | {tsv} | {notes}"
    with open(os.path.join(run_dir, 'readings.txt'), 'a') as f:
        f.write(line + '\n')

    print("Done.")
    return run_dir

if __name__ == '__main__':
    capture_data()
