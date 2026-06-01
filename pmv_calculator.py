from pythermalcomfort.models import pmv_ppd_iso
from pythermalcomfort.utilities import v_relative, clo_dynamic_iso


DEFAULT_CLO = 0.61
DEFAULT_MET = 1.1


def calculate_pmv(air_temp, humidity, mrt, air_speed, clo=DEFAULT_CLO, met=DEFAULT_MET):
    vr  = v_relative(v=air_speed, met=met)
    # clo_d = clo_dynamic_iso(clo=clo, met=met, v=air_speed)
    
    # print(f"\nair_temp={air_temp}, humidity={humidity}, mrt={mrt}, vr={vr}, clo_d={clo}")
    
    notes = ""
    if (air_temp<10):
        notes += "Temperature too low, "
    elif (air_temp>30):
        notes += "Temperature too high, "
    elif (mrt<10):
        notes += "Surface temperature too low, "
    elif (mrt>40):
        notes += "Surface temperature too high, "
    elif (vr<0):
        notes += "Negative air speed, "
    elif (vr>1):
        notes += "Air speed too high, "
    else:
        notes = "No notes.  "

    result = pmv_ppd_iso(
        tdb=air_temp,
        tr=mrt,
        vr=vr,
        rh=humidity,
        met=met,
        clo=clo,
        model="7730-2005"
    )
    # print(result)

    pmv = round(result.pmv, 2)
    ppd = round(result.ppd, 1)

    return {
        'pmv':          pmv,
        'ppd':          ppd,
        'tsv':          result.tsv,
        'notes':        notes[:-2]
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
