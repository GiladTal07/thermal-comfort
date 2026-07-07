from pythermalcomfort.models import pmv_ppd_iso
from pythermalcomfort.utilities import v_relative, clo_dynamic_iso

DEFAULT_CLO = 0.61
DEFAULT_MET = 1.1

def calculate_pmv(air_temp, humidity, mrt, air_speed, clo=DEFAULT_CLO, met=DEFAULT_MET):
    if any(v is None for v in [air_temp, humidity, mrt, air_speed]):
        raise ValueError(f"Cannot calculate PMV: missing sensor values")
    vr  = v_relative(v=air_speed, met=met)
    
    notes = ""
    if air_temp < 10:
        notes += "Temperature too low, "
    if air_temp > 30:
        notes += "Temperature too high, "
    if mrt < 10:
        notes += "Surface temperature too low, "
    if mrt > 40:
        notes += "Surface temperature too high, "
    if vr < 0:
        notes += "Negative air speed, "
    if vr > 1:
        notes += "Air speed too high, "

    result = pmv_ppd_iso(
        tdb=air_temp,
        tr=mrt,
        vr=vr,
        rh=humidity,
        met=met,
        clo=clo,
        model="7730-2005"
    )

    pmv = round(result.pmv, 2)
    ppd = round(result.ppd, 1)

    return {
        'pmv':          pmv,
        'ppd':          ppd,
        'tsv':          result.tsv,
        'notes':        notes[:-2] if notes else "No notes.",
    }

if __name__ == '__main__':
    result = calculate_pmv(
        air_temp=22.0,
        humidity=50.0,
        mrt=24.0,
        air_speed=0.1
    )

    print(f"PMV:         {result['pmv']}  (-3 cold → 0 neutral → +3 hot)")
    print(f"PPD:         {result['ppd']} %  (predicted % dissatisfied)")
    print(f"Verdict:     {result['tsv']}")
