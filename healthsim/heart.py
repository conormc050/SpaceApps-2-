import numpy as np
import pandas as pd
from scipy.signal import butter, find_peaks, sosfiltfilt

from .loaders import runs


def valid_mask(adc, fs, flat_s=0.5, pad_s=0.2):
    adc = np.asarray(adc)
    bad = (adc <= 0) | (adc >= 1023)
    flat = np.diff(adc, prepend=adc[0] - 1) == 0
    starts, lengths, vals = runs(flat)
    for s, n, v in zip(starts, lengths, vals):
        if v and n >= flat_s * fs:
            bad[max(s - 1, 0) : s + n] = True
    k = max(int(pad_s * fs), 1)
    bad = np.convolve(bad.astype(int), np.ones(2 * k + 1, int), mode="same") > 0
    return ~bad


def segments(mask, min_len):
    starts, lengths, vals = runs(mask)
    return [(int(s), int(s + n)) for s, n, v in zip(starts, lengths, vals) if v and n >= min_len]


def dominant_period(y, fs, min_bpm, max_bpm):
    y = y - y.mean()
    ac = np.correlate(y, y, mode="full")[len(y) - 1 :]
    if ac[0] <= 0:
        return np.nan
    ac = ac / ac[0]
    lo = int(fs * 60 / max_bpm)
    hi = min(int(fs * 60 / min_bpm), len(ac) - 1)
    seg = ac[lo : hi + 1]
    pk, _ = find_peaks(seg)
    if len(pk) == 0:
        return (lo + int(np.argmax(seg))) / fs
    best = seg[pk].max()
    first = pk[seg[pk] >= 0.8 * best][0]
    return (lo + first) / fs


def estimate_bpm(adc, fs, min_bpm=40, max_bpm=200, min_valid_frac=0.5, min_seg_s=5.0):
    adc = np.asarray(adc, dtype=float)
    mask = valid_mask(adc, fs)
    valid_frac = float(mask.mean())
    segs = segments(mask, int(min_seg_s * fs))
    empty = {"est_bpm": np.nan, "n_beats": 0, "valid_frac": valid_frac, "status": "insufficient_signal"}
    if valid_frac < min_valid_frac or not segs:
        return empty
    sos = butter(2, [0.5, 4.0], btype="band", fs=fs, output="sos")
    filtered = [(s, sosfiltfilt(sos, adc[s:e])) for s, e in segs]
    period = dominant_period(max(filtered, key=lambda x: len(x[1]))[1], fs, min_bpm, max_bpm)
    if not np.isfinite(period):
        return empty
    rrs = []
    n_beats = 0
    for _, y in filtered:
        p, _ = find_peaks(y, distance=max(1, int(0.6 * period * fs)), prominence=0.5 * np.std(y))
        n_beats += len(p)
        rr = np.diff(p) / fs
        rrs.extend(rr[(rr > 0.6 * period) & (rr < 1.5 * period)])
    if len(rrs) < 3:
        return {**empty, "n_beats": n_beats}
    return {"est_bpm": 60.0 / float(np.mean(rrs)), "n_beats": n_beats, "valid_frac": valid_frac, "status": "ok"}


def analyze_windows(raw, meta, tolerance_bpm=5.0):
    rows = []
    for _, w in meta.iterrows():
        adc = raw.loc[raw["window_id"] == w["window_id"], "ppg_adc"].to_numpy()
        r = estimate_bpm(adc, int(w["fs_hz"]))
        rows.append({"window_id": int(w["window_id"]), "window_start": w["window_start"], **r})
    out = pd.DataFrame(rows).merge(meta[["window_id", "true_bpm_window", "true_state", "dropout_s"]], on="window_id")
    out["abs_error_bpm"] = (out["est_bpm"] - out["true_bpm_window"]).abs()
    out["within_tolerance"] = out["abs_error_bpm"] <= tolerance_bpm
    out["est_bpm"] = out["est_bpm"].round(1)
    return out


def evaluate_windows(results):
    ok = results[results["status"] == "ok"]
    return {
        "windows": int(len(results)),
        "ok_windows": int(len(ok)),
        "ok_fraction": len(ok) / len(results) if len(results) else 0.0,
        "within_tolerance_fraction": float(ok["within_tolerance"].mean()) if len(ok) else 0.0,
        "mae_bpm": float(ok["abs_error_bpm"].mean()) if len(ok) else np.nan,
        "max_error_bpm": float(ok["abs_error_bpm"].max()) if len(ok) else np.nan,
    }


def daily_hr_summary(hr):
    d = hr.assign(date=hr["timestamp"].dt.date)
    g = d.groupby("date")["sensor_bpm"]
    return pd.DataFrame(
        {
            "hr_mean_bpm": g.mean().round(1),
            "hr_p05_bpm": g.quantile(0.05).round(1),
            "hr_max_bpm": g.max(),
            "hr_coverage": g.apply(lambda s: s.notna().mean()).round(3),
        }
    ).reset_index()
