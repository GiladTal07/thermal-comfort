import os
from datetime import datetime
from sensors import read_sensor_values, capture_photo
from thermal_map import save_maps
from pmv_calculator import calculate_pmv

def capture_data() -> str:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    run_dir = os.path.join(script_dir, 'data', timestamp)
    os.makedirs(run_dir)

    air_temp, humidity, mean_radiant, thermal, air_speed = read_sensor_values()
    capture_photo(timestamp, output_dir=run_dir)
    save_maps(thermal, filename=timestamp, output_dir=run_dir)
    result = calculate_pmv(air_temp, humidity, mean_radiant, air_speed)

    line = f"{timestamp} | {air_temp} | {humidity} | {mean_radiant}  | {air_speed} | {result['pmv']} | {result['ppd']} | {result['tsv']} | {result['notes']}"
    with open(os.path.join(run_dir, 'readings.txt'), 'a') as f:
        f.write(line + '\n')
        
    print("Done.")
    return run_dir

if __name__ == '__main__':
    capture_data()
