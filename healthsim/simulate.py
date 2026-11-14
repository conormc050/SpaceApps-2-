import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import config

STATES = {0: "asleep", 1: "in_bed_awake", 2: "sedentary", 3: "light_activity", 4: "exercise"}
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
SIM_KEYS = {"seed", "start_utc", "calibration_days", "scenario_days"}

GROUND_TRUTH_COLUMNS = {
    "sleep_minute": ["true_asleep", "true_in_bed", "night_id"],
    "sleep_nights_truth": ["true_sleep_min", "true_wake_events", "true_waso_min", "true_sleep_deficit_h"],
    "activity_minute": ["true_state"],
    "exercise_sessions_truth": ["start", "end", "minutes"],
    "heart_rate_minute": ["true_bpm", "dropout", "true_resting_hr_offset_bpm"],
    "ppg_windows": ["true_state", "true_bpm_window", "true_bpm_minute", "dropout_s"],
    "skin_temp_minute": ["true_injected_offset_c", "true_rise_active"],
    "mood_daily": ["true_mood_1to5"],
}


@dataclass
class SimConfig:
    wake_alarm_sd_min: float
    wake_alarm_limit_min: float
    sleep_h_limits: list
    latency_min: list
    linger_min: list
    wake_events: list
    wake_event_len_min: list
    light_bouts_per_day: float
    light_bout_len_min: list
    active_count_threshold: int
    exercise_count_threshold: int
    evening_dim_h: float
    hr_baseline_bpm: list
    hr_circadian_amp: float
    hr_exercise_boost: list
    hr_sensor_noise_sd: float
    hr_dropouts_per_day: float
    hr_exercise_dropout_prob: float
    ppg_fs_hz: int
    ppg_window_s: int
    ppg_every_min: int
    ppg_noise_sd: float
    ppg_motion_noise_mult: float
    ppg_hrv_sd: float
    ppg_dropout_prob: float
    temp_baseline_c: float
    temp_noise_sd: float
    temp_drift_sd: float
    temp_drift_tau_h: float
    temp_resolution_c: float
    temp_missing_prob: float
    mood_missed_prob: float
    mood_checkin_delay_min: list


def sim_settings(overrides):
    sim = dict(config.section("simulation"))
    sim.update({k: v for k, v in overrides.items() if k in SIM_KEYS})
    sensors = dict(config.section("sensors"))
    unknown = set(overrides) - SIM_KEYS - set(sensors)
    if unknown:
        raise ValueError(f"unknown simulator setting: {', '.join(sorted(unknown))}")
    sensors.update({k: v for k, v in overrides.items() if k in sensors})
    return sim, SimConfig(**sensors)


def ema(x, tau):
    a = 1.0 / max(float(tau), 1.0)
    y = np.empty(len(x), dtype=float)
    acc = float(x[0])
    for i, v in enumerate(x):
        acc += a * (v - acc)
        y[i] = acc
    return y


def ou_process(rng, n, sd, tau_min):
    phi = np.exp(-1.0 / tau_min)
    k = np.sqrt(1 - phi**2) * sd
    e = rng.normal(0, 1, n)
    x = np.empty(n)
    acc = rng.normal(0, sd)
    for i in range(n):
        acc = phi * acc + k * e[i]
        x[i] = acc
    return x


def minute_of(t0, day_offset, hour):
    h0 = t0.hour + t0.minute / 60
    return int(round((day_offset * 24 + hour - h0) * 60))


def hhmm(text):
    h, m = text.split(":")
    return int(h) + int(m) / 60


def ramp(n, onset_min, ramp_min):
    if onset_min is None:
        return np.zeros(n)
    t = np.arange(n)
    if ramp_min <= 0:
        return (t >= onset_min).astype(float)
    return np.clip((t - onset_min) / ramp_min, 0.0, 1.0)


def make_plan(crew_id, n):
    c = config.crew(crew_id)
    sc = config.scenario(crew_id)
    sched = config.section("schedule")
    slp = config.section("sleep")
    onset = None if sc["onset_after_days"] is None else int(sc["onset_after_days"] * 1440)
    r = ramp(n, onset, int(sc["ramp_days"] * 1440))
    return {
        "wake_h": hhmm(sched["wake_utc"]),
        "bed_h": hhmm(sched["bedtime_utc"]),
        "exercise_h": hhmm(c["exercise_start_utc"]),
        "exercise_min": int(sched["exercise_block_min"]),
        "checkin_h": hhmm(sched["checkup_times_utc"][-1]),
        "sleep_mean_h": slp["crew_mean_h"].get(crew_id, slp["mean_h"]),
        "night_sd_h": slp["night_sd_h"],
        "deficit_h": sc["sleep_deficit_h"],
        "ramp": r,
        "hr_rise": r * sc["resting_hr_rise_bpm"],
        "temp_offset": r * sc["skin_temp_rise_c"],
    }


def rint(rng, bounds):
    return int(rng.integers(bounds[0], bounds[1] + 1))


def build_schedule(cfg, plan, rng, ts):
    n = len(ts)
    t0 = ts[0]
    days = n // 1440
    state = np.full(n, 2, dtype=int)
    in_bed = np.zeros(n, dtype=bool)
    night_id = np.full(n, -1, dtype=int)
    wake_event = np.zeros(n, dtype=bool)
    wake_light = np.zeros(n, dtype=bool)
    nights = []
    lo_h, hi_h = cfg.sleep_h_limits

    for d in range(days):
        k = rint(rng, cfg.wake_events)
        lens = rng.integers(cfg.wake_event_len_min[0], cfg.wake_event_len_min[1] + 1, size=k)
        latency = rint(rng, cfg.latency_min)
        linger = rint(rng, cfg.linger_min)
        jitter = int(round(float(np.clip(rng.normal(0, cfg.wake_alarm_sd_min), -cfg.wake_alarm_limit_min, cfg.wake_alarm_limit_min))))
        noise = rng.normal(0, plan["night_sd_h"])
        deficit = plan["deficit_h"] * float(plan["ramp"][minute_of(t0, d, plan["bed_h"])])
        target = float(np.clip(plan["sleep_mean_h"] + noise - deficit, lo_h, hi_h)) * 60
        period = int(round(target + lens.sum()))
        out_bed = minute_of(t0, d + 1, plan["wake_h"]) + jitter
        final_wake = out_bed - linger
        onset = final_wake - period
        bed = onset - latency
        if bed < 0 or out_bed >= n:
            continue
        in_bed[bed:out_bed] = True
        night_id[bed:out_bed] = d
        state[bed:out_bed] = 1
        state[onset:final_wake] = 0
        seg = period / k
        for i, length in enumerate(lens):
            lo = int(i * seg) + 20
            hi = max(int((i + 1) * seg) - int(length) - 20, lo + 1)
            s = onset + int(rng.integers(lo, hi))
            state[s : s + length] = 1
            wake_event[s : s + length] = True
            if rng.random() < 0.5:
                wake_light[s : s + length] = True
        nights.append(
            {
                "night_id": d,
                "bedtime": ts[bed],
                "sleep_onset": ts[onset],
                "final_wake": ts[final_wake],
                "out_of_bed": ts[out_bed],
                "true_sleep_min": int((state[onset:final_wake] == 0).sum()),
                "true_wake_events": k,
                "true_waso_min": int((state[onset:final_wake] != 0).sum()),
                "true_sleep_deficit_h": round(deficit, 4),
            }
        )

    for c in range(days):
        for _ in range(rng.poisson(cfg.light_bouts_per_day)):
            s = minute_of(t0, c, rng.uniform(plan["wake_h"] + 1, plan["bed_h"]))
            length = rint(rng, cfg.light_bout_len_min)
            if s < 0 or s + length >= n:
                continue
            sl = slice(s, s + length)
            state[sl] = np.where(state[sl] == 2, 3, state[sl])

    ex_boost = np.zeros(n)
    sessions = []
    for c in range(days):
        s = minute_of(t0, c, plan["exercise_h"])
        length = plan["exercise_min"]
        boost = rng.uniform(cfg.hr_exercise_boost[0], cfg.hr_exercise_boost[1])
        if s < 0 or s + length >= n or in_bed[s : s + length].any():
            continue
        sl = slice(s, s + length)
        state[sl] = 4
        ex_boost[sl] = boost
        sessions.append({"start": ts[s], "end": ts[s + length], "minutes": length})

    return {
        "state": state,
        "in_bed": in_bed,
        "night_id": night_id,
        "wake_event": wake_event,
        "wake_light": wake_light,
        "ex_boost": ex_boost,
        "nights": pd.DataFrame(nights),
        "sessions": pd.DataFrame(sessions),
    }


def simulate_imu(rng, sch):
    state = sch["state"]
    n = len(state)
    mean_by_state = np.array([2.0, 8.0, 60.0, 200.0, 600.0])
    counts = rng.gamma(2.0, mean_by_state[state] / 2.0)
    twitch = (state == 0) & (rng.random(n) < 0.03)
    counts[twitch] += rng.uniform(10, 30, twitch.sum())
    we = sch["wake_event"]
    counts[we] = rng.gamma(2.0, 20.0, we.sum())
    counts = np.round(counts).astype(int)
    accel = 1.0 + counts / 2000.0 + rng.normal(0, 0.005, n)
    return counts, np.round(accel, 4)


def simulate_environment(cfg, plan, rng, sch, hours):
    state = sch["state"]
    n = len(state)
    in_bed = sch["in_bed"]
    day = (hours >= plan["wake_h"]) & (hours < plan["bed_h"] - cfg.evening_dim_h)
    day_mean = np.where(day, 400.0, 120.0)
    lux = rng.lognormal(np.log(day_mean), 0.5)
    lux[in_bed] = rng.lognormal(np.log(1.0), 0.6, in_bed.sum())
    wl = sch["wake_light"]
    lux[wl] = rng.lognormal(np.log(80.0), 0.4, wl.sum())
    snd = np.where(state == 4, rng.normal(65, 6, n), rng.normal(50, 8, n))
    snd[in_bed] = rng.normal(31, 3, in_bed.sum())
    spikes = in_bed & (rng.random(n) < 0.02)
    snd[spikes] += rng.uniform(10, 25, spikes.sum())
    we = sch["wake_event"]
    snd[we] = rng.normal(42, 5, we.sum())
    return np.round(lux, 2), np.round(np.clip(snd, 25, 95), 1)


def simulate_heart_rate(cfg, plan, rng, sch, hours, day_idx):
    state = sch["state"]
    n = len(state)
    days = n // 1440
    base = rng.uniform(cfg.hr_baseline_bpm[0], cfg.hr_baseline_bpm[1])
    daily = rng.normal(0, 1.5, day_idx.max() + 1)
    target = base + daily[day_idx] + cfg.hr_circadian_amp * np.cos(2 * np.pi * (hours - 16) / 24)
    target += np.select([state == 0, state == 1, state == 3], [-6.0, -3.0, 15.0], 0.0)
    target += sch["ex_boost"]
    target[sch["wake_event"]] += 8.0
    target += plan["hr_rise"]
    true_bpm = ema(target, 2) + ema(rng.normal(0, 3, n), 3)
    true_bpm = np.round(np.clip(true_bpm, 40, 190), 1)
    measured = true_bpm + rng.normal(0, cfg.hr_sensor_noise_sd, n)
    dropout = np.zeros(n, dtype=bool)
    for _ in range(rng.poisson(cfg.hr_dropouts_per_day * days)):
        s = int(rng.integers(0, n))
        dropout[s : s + int(rng.integers(1, 21))] = True
    dropout |= (state == 4) & (rng.random(n) < cfg.hr_exercise_dropout_prob)
    measured = np.round(measured)
    measured[dropout] = np.nan
    return true_bpm, measured, dropout, base


def simulate_ppg_window(cfg, rng, bpm_at, motion):
    fs = cfg.ppg_fs_hz
    T = cfg.ppg_window_s
    t = np.arange(T * fs) / fs
    beats = []
    tb = -rng.uniform(0, 60.0 / bpm_at(0.0))
    while tb < T + 1.0:
        rr = 60.0 / bpm_at(min(max(tb, 0.0), T)) * (1 + rng.normal(0, cfg.ppg_hrv_sd))
        beats.append((tb, rr))
        tb += rr
    sig = np.zeros_like(t)
    peaks = []
    for b, rr in beats:
        s = min(1.0, rr / 0.85)
        a = rng.uniform(0.9, 1.1)
        p = b + 0.15 * s
        peaks.append(p)
        sig += a * np.exp(-0.5 * ((t - p) / (0.05 * s)) ** 2)
        sig += 0.3 * a * np.exp(-0.5 * ((t - b - 0.40 * s) / (0.07 * s)) ** 2)
    sig += 0.15 * np.sin(2 * np.pi * rng.uniform(0.2, 0.3) * t + rng.uniform(0, 2 * np.pi))
    sig += rng.normal(0, 0.05) * t / T
    noise = cfg.ppg_noise_sd * (cfg.ppg_motion_noise_mult if motion else 1.0)
    sig += rng.normal(0, noise, t.size)
    adc = np.clip(np.round(512 + 200 * (sig - 0.3)), 0, 1023)
    peaks = np.array(peaks)
    inside = peaks[(peaks >= 0) & (peaks < T)]
    true_bpm = 60.0 / np.mean(np.diff(inside)) if len(inside) > 2 else np.nan
    dropout_s = 0.0
    if rng.random() < cfg.ppg_dropout_prob:
        dropout_s = float(rng.uniform(3, 10))
        s0 = rng.uniform(0, T - dropout_s)
        mask = (t >= s0) & (t < s0 + dropout_s)
        adc[mask] = 0 if rng.random() < 0.5 else 1023
    return t, adc.astype(int), true_bpm, dropout_s


def simulate_ppg(cfg, rng, ts, true_bpm, state):
    n = len(ts)
    minute_idx = np.arange(n)
    meta = []
    frames = []
    for w, m in enumerate(range(0, n - cfg.ppg_window_s // 60 - 1, cfg.ppg_every_min)):
        bpm_at = lambda sec, m=m: float(np.interp(m + sec / 60.0, minute_idx, true_bpm))
        motion = state[m] in (3, 4)
        t, adc, tb, drop = simulate_ppg_window(cfg, rng, bpm_at, motion)
        meta.append(
            {
                "window_id": w,
                "window_start": ts[m],
                "true_state": STATES[int(state[m])],
                "true_bpm_window": round(tb, 2),
                "true_bpm_minute": true_bpm[m],
                "dropout_s": round(drop, 2),
                "fs_hz": cfg.ppg_fs_hz,
            }
        )
        frames.append(
            pd.DataFrame(
                {"window_id": w, "sample_idx": np.arange(len(t)), "t_s": np.round(t, 3), "ppg_adc": adc}
            )
        )
    return pd.DataFrame(meta), pd.concat(frames, ignore_index=True)


def simulate_skin_temp(cfg, plan, rng, sch, hours):
    state = sch["state"]
    n = len(state)
    person = rng.normal(0, 0.2)
    sleep_warm = 0.6 * ema((state == 0).astype(float), 20)
    ex_cool = -0.4 * ema((state == 4).astype(float), 10)
    circ = 0.3 * np.cos(2 * np.pi * (hours - 3) / 24)
    drift = ou_process(rng, n, cfg.temp_drift_sd, cfg.temp_drift_tau_h * 60)
    base = cfg.temp_baseline_c + person + sleep_warm + ex_cool + circ + drift
    noise = rng.normal(0, cfg.temp_noise_sd, n)
    missing = rng.random(n) < cfg.temp_missing_prob
    offset = plan["temp_offset"]
    q = cfg.temp_resolution_c
    y = np.round((base + noise + offset) / q) * q
    y[missing] = np.nan
    return np.round(y, 4), np.round(offset, 4)


def simulate_mood(cfg, plan, rng, ts):
    dates = pd.date_range(ts[0].normalize(), ts[-1].normalize(), freq="D")
    score = int(rng.integers(3, 5))
    rows = []
    for d in dates:
        score = int(np.clip(score + rng.choice([-1, 0, 1], p=[0.25, 0.5, 0.25]), 1, 5))
        delay = rint(rng, cfg.mood_checkin_delay_min)
        checkin = d + pd.Timedelta(minutes=int(round(plan["checkin_h"] * 60)) + delay)
        missed = bool(rng.random() < cfg.mood_missed_prob)
        if checkin < ts[0] or checkin > ts[-1]:
            continue
        rows.append(
            {
                "date": d.date().isoformat(),
                "checkin_time": checkin,
                "mood_self_report_1to5": np.nan if missed else score,
                "true_mood_1to5": score,
                "missed": missed,
            }
        )
    df = pd.DataFrame(rows)
    df["mood_self_report_1to5"] = df["mood_self_report_1to5"].astype("Int64")
    return df


def label(df, crew_id):
    df = df.copy()
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].dt.strftime(TIME_FORMAT)
    df["data_source"] = config.SOURCE
    df["crew"] = crew_id
    return df


def generate_crew(crew_id, out_dir, sim, cfg):
    seed = int(sim["seed"]) + int(config.crew(crew_id)["seed_offset"])
    rng = np.random.default_rng(seed)
    days = int(sim["calibration_days"]) + int(sim["scenario_days"])
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ts = pd.date_range(sim["start_utc"], periods=days * 1440, freq="min")
    if ts.tz is None:
        ts = ts.tz_localize("UTC")
    t0 = ts[0]
    n = len(ts)
    hours = (t0.hour + t0.minute / 60 + np.arange(n) / 60) % 24
    day_idx = ((t0.hour * 60 + t0.minute + np.arange(n)) // 1440).astype(int)
    plan = make_plan(crew_id, n)

    sch = build_schedule(cfg, plan, rng, ts)
    state = sch["state"]
    counts, accel = simulate_imu(rng, sch)
    lux, snd = simulate_environment(cfg, plan, rng, sch, hours)
    true_bpm, sensor_bpm, hr_drop, hr_base = simulate_heart_rate(cfg, plan, rng, sch, hours, day_idx)
    ppg_meta, ppg_raw = simulate_ppg(cfg, rng, ts, true_bpm, state)
    temp, temp_offset = simulate_skin_temp(cfg, plan, rng, sch, hours)
    mood = simulate_mood(cfg, plan, rng, ts)
    state_names = np.array([STATES[i] for i in range(5)])[state]

    tables = {
        "sleep_minute": pd.DataFrame(
            {
                "timestamp": ts,
                "activity_count": counts,
                "light_lux": lux,
                "sound_db": snd,
                "true_asleep": (state == 0).astype(int),
                "true_in_bed": sch["in_bed"].astype(int),
                "night_id": sch["night_id"],
            }
        ),
        "sleep_nights_truth": sch["nights"],
        "activity_minute": pd.DataFrame(
            {
                "timestamp": ts,
                "activity_count": counts,
                "movement_minute": (counts >= cfg.active_count_threshold).astype(int),
                "exercise_minute": (counts >= cfg.exercise_count_threshold).astype(int),
                "accel_mag_mean_g": accel,
                "true_state": state_names,
            }
        ),
        "exercise_sessions_truth": sch["sessions"],
        "heart_rate_minute": pd.DataFrame(
            {
                "timestamp": ts,
                "sensor_bpm": sensor_bpm,
                "true_bpm": true_bpm,
                "dropout": hr_drop.astype(int),
                "true_resting_hr_offset_bpm": np.round(plan["hr_rise"], 4),
            }
        ),
        "ppg_windows": ppg_meta,
        "ppg_raw": ppg_raw,
        "skin_temp_minute": pd.DataFrame(
            {
                "timestamp": ts,
                "skin_surface_temp_c": temp,
                "true_injected_offset_c": temp_offset,
                "true_rise_active": (temp_offset > 0).astype(int),
            }
        ),
        "mood_daily": mood,
    }

    files = {}
    for name, df in tables.items():
        path = out / f"{config.PREFIX}{name}.csv"
        label(df, crew_id).to_csv(path, index=False)
        files[name] = {"path": path.name, "rows": int(len(df))}

    sc = config.scenario(crew_id)
    manifest = {
        **config.manifest_header(),
        "crew": crew_id,
        "initials": config.crew(crew_id)["initials"],
        "scenario": config.crew(crew_id)["scenario"],
        "scenario_settings": sc,
        "scenario_onset_utc": None if sc["onset_after_days"] is None else (t0 + pd.Timedelta(days=sc["onset_after_days"])).strftime(TIME_FORMAT),
        "timezone": "UTC",
        "start_utc": t0.strftime(TIME_FORMAT),
        "days": days,
        "calibration_days": int(sim["calibration_days"]),
        "scenario_days": int(sim["scenario_days"]),
        "seed": seed,
        "sleep_mean_h": plan["sleep_mean_h"],
        "sleep_night_sd_h": plan["night_sd_h"],
        "scheduled_sleep_h": config.section("schedule")["scheduled_sleep_h"],
        "sleep_deficit_applied_at": "scheduled bedtime of each night, scaled by the scenario ramp",
        "exercise": f"one scheduled block of {plan['exercise_min']} min per day at {config.crew(crew_id)['exercise_start_utc']} UTC",
        "steps": "none; microgravity has no steps, so movement_minute and exercise_minute are used",
        "sensor_model": asdict(cfg),
        "sample_rates": {
            "imu_activity": "1 per minute (epoch summary)",
            "light_sound": "1 per minute",
            "heart_rate_minute": "1 per minute",
            "ppg_raw": f"{cfg.ppg_fs_hz} Hz, {cfg.ppg_window_s} s window every {cfg.ppg_every_min} min",
            "skin_surface_temp": f"1 per minute, {cfg.temp_resolution_c} C resolution",
            "mood": "1 check-in per day",
        },
        "state_codes": STATES,
        "ground_truth_columns": GROUND_TRUTH_COLUMNS,
        "simulated_person_hr_baseline_bpm": round(float(hr_base), 1),
        "files": files,
    }
    manifest_path = out / f"{config.PREFIX}manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {name: out / f"{config.PREFIX}{name}.csv" for name in tables} | {"manifest": manifest_path}


def generate(out_dir="data", **overrides):
    sim, cfg = sim_settings(overrides)
    root = Path(out_dir)
    return {crew_id: generate_crew(crew_id, root / crew_id, sim, cfg) for crew_id in config.crew_ids()}


def main():
    p = argparse.ArgumentParser(description="Generate SIMULATED wearable health data for every crew member.")
    p.add_argument("--out", default="data")
    p.add_argument("--seed", type=int, default=None)
    a = p.parse_args()
    overrides = {} if a.seed is None else {"seed": a.seed}
    for crew_id, paths in generate(a.out, **overrides).items():
        print(f"{crew_id}: {Path(paths['manifest']).parent}")


if __name__ == "__main__":
    main()
