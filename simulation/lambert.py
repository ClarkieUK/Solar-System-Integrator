from poliastro.core.iod import izzo
from poliastro.bodies import Sun, Earth, Mars
from datetime import datetime
import bisect
import numpy as np
from lamberthub import izzo2015
from pathlib import Path

# paths 
ROOT = Path(__file__).resolve().parents[1]
TRACE_DIR = ROOT / "data" / "traces"
TRACE_DIR.mkdir(parents=True, exist_ok=True)

def lambert(host : str, target : str, t0 : float, r0 : np.array, desired_mission_duration : int) -> dict :

    # load positions [x,y,z] , velocities [vx,vy,vz]
    trace_path = TRACE_DIR / f"{target}_TRACE.csv"
    sun_trace_path = TRACE_DIR / "SUN_TRACE.csv"

    dates_target = np.genfromtxt(trace_path, delimiter=',', usecols=[0], skip_header=True, dtype=str)

    _data_target = np.genfromtxt(trace_path, delimiter=',', usecols=[1,2,3], skip_header=True)
    _data_v_target = np.genfromtxt(trace_path, delimiter=',', usecols=[4,5,6], skip_header=True)

    _sun = np.genfromtxt(sun_trace_path, delimiter=',', usecols=[1,2,3], skip_header=True)
    _sun_v = np.genfromtxt(sun_trace_path, delimiter=',', usecols=[4,5,6], skip_header=True)

    # convert to heliocentric (target relative to Sun)
    data_target = _data_target - _sun
    data_v_target = _data_v_target - _sun_v

    info = get_dt(t0, host, target, dates_target, data_target, data_v_target, desired_mission_duration)

    # use time-interpolated target state instead of just the lower sample
    r_target = info[f"{target}_LOC_INTERP"]
    corrected_duration = info["INTERP_DT"]

    v_i, v_f = izzo(Sun.k, r0, r_target, corrected_duration, 0, True, False, 150, 1e-8)
    # alt
    # v_i, v_f = izzo2015(Sun.k, r0, r_target, corrected_duration, 0, True, True, 35, 0.00001, 1e-6)

    return v_i, info[f"{target}_VEL_INTERP"], corrected_duration


def get_dt(t0 : float, host : str, target : str, target_dates : np.array, target_trace : np.array, target_velocity_trace : np.array, mission_duration : float):
    periods = {
        "MARS": 686.980 * 24 * 60 * 60,
        "EARTH": 365 * 24 * 60 * 60,
    } # if you want to launch between different bodies youd have to add their periods here... :(

    # convert to unix timestamps
    timestamps = [datetime.strptime(ts, "%A %B %d %Y %H:%M:%S").timestamp() for ts in target_dates]

    # convert duration to seconds
    delta_t = mission_duration * 24 * 60 * 60

    # nominal target time
    t_target = t0 + delta_t

    # correct for wrapping assuming approximately periodic motion
    orbit_time = periods.get(target)
    if orbit_time is not None and orbit_time > 0:
        while t_target > timestamps[-1]:
            t_target -= orbit_time
        while t_target < timestamps[0]:
            t_target += orbit_time

    # find floor and ceil using bisect
    idx = bisect.bisect_left(timestamps, t_target)

    floor_idx = max(0, idx - 1)
    ceil_idx = min(idx, len(timestamps) - 1)

    t_floor = timestamps[floor_idx]
    t_ceil = timestamps[ceil_idx]

    loc_lower = target_trace[floor_idx]
    loc_upper = target_trace[ceil_idx]
    vel_lower = target_velocity_trace[floor_idx]
    vel_upper = target_velocity_trace[ceil_idx]

    # linear interpolation in time for smoother, more consistent target state
    if t_ceil == t_floor:
        alpha = 0.0
    else:
        alpha = (t_target - t_floor) / (t_ceil - t_floor)
        alpha = max(0.0, min(1.0, alpha))

    loc_interp = (1.0 - alpha) * loc_lower + alpha * loc_upper
    vel_interp = (1.0 - alpha) * vel_lower + alpha * vel_upper

    return {
        f"{target}_LOC_LOWER": loc_lower,
        f"{target}_LOC_UPPER": loc_upper,
        f"{target}_VEL_LOWER": vel_lower,
        f"{target}_VEL_UPPER": vel_upper,
        f"{target}_LOC_INTERP": loc_interp,
        f"{target}_VEL_INTERP": vel_interp,
        "LOWER_DT": t_floor - t0,
        "UPPER_DT": t_ceil - t0,
        "INTERP_DT": t_target - t0,
        "LOWER_TIME": datetime.fromtimestamp(float(t_floor)),
        "UPPER_TIME": datetime.fromtimestamp(float(t_ceil)),
        "TARGET_TIME": datetime.fromtimestamp(float(t_target)),
    }


def cycle(start, where, orbit_time) -> float :
    difference = where - start 
    if difference > start + orbit_time:
        return difference % orbit_time
    else:
        return where