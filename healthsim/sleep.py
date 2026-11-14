import numpy as np
import pandas as pd

from .loaders import runs

METHOD = "actigraphy-style sleep/wake estimate from movement, light and sound (1-min epochs); not sleep stages"


def drop_short_runs(x, value, min_len):
    x = np.asarray(x, dtype=bool).copy()
    starts, lengths, vals = runs(x)
    for s, n, v in zip(starts, lengths, vals):
        if v == value and n < min_len:
            x[s : s + n] = not value
    return x


def detect_sleep(df, act_thr=10.0, lux_thr=10.0, db_thr=40.0, window=5, min_sleep_bout=10, min_wake_bout=2):
    act = df["activity_count"].rolling(window, center=True, min_periods=1).mean()
    lux = df["light_lux"].rolling(window, center=True, min_periods=1).median()
    snd = df["sound_db"].rolling(window, center=True, min_periods=1).median()
    asleep = ((act < act_thr) & (lux < lux_thr) & (snd < db_thr)).to_numpy()
    asleep = drop_short_runs(asleep, True, min_sleep_bout)
    asleep = drop_short_runs(asleep, False, min_wake_bout)
    return asleep.astype(int)


def score(pred, truth):
    p = np.asarray(pred).astype(bool)
    t = np.asarray(truth).astype(bool)
    tp = int((p & t).sum())
    fp = int((p & ~t).sum())
    fn = int((~p & t).sum())
    tn = int((~p & ~t).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "accuracy": (tp + tn) / len(p),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
    }


def nightly_summary(df, pred):
    d = pd.DataFrame({"timestamp": df["timestamp"], "asleep": np.asarray(pred).astype(int)})
    d["sleep_date"] = (d["timestamp"] + pd.Timedelta(hours=12)).dt.date
    rows = []
    for date, g in d.groupby("sleep_date"):
        a = g["asleep"].to_numpy()
        idx = np.flatnonzero(a)
        if len(idx) == 0:
            rows.append({"sleep_date": date, "est_sleep_min": 0, "est_onset": pd.NaT, "est_final_wake": pd.NaT, "est_wake_bouts": 0})
            continue
        core = a[idx[0] : idx[-1] + 1]
        _, _, vals = runs(core)
        rows.append(
            {
                "sleep_date": date,
                "est_sleep_min": int(a.sum()),
                "est_onset": g["timestamp"].iloc[idx[0]],
                "est_final_wake": g["timestamp"].iloc[idx[-1]] + pd.Timedelta(minutes=1),
                "est_wake_bouts": int((vals == 0).sum()),
            }
        )
    out = pd.DataFrame(rows)
    out["est_sleep_h"] = (out["est_sleep_min"] / 60).round(2)
    out["method"] = METHOD
    return out


def compare_nights(nightly, truth_nights):
    t = truth_nights.copy()
    t["sleep_date"] = t["final_wake"].dt.date
    m = t.merge(nightly, on="sleep_date", how="left")
    m["sleep_min_error"] = m["est_sleep_min"] - m["true_sleep_min"]
    return m[["night_id", "sleep_date", "true_sleep_min", "est_sleep_min", "sleep_min_error", "true_wake_events", "est_wake_bouts"]]
