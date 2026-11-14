from pathlib import Path

import numpy as np
import pandas as pd

SOURCE = "SIMULATED"
PREFIX = "SIMULATED_"
TIME_COLS = [
    "timestamp",
    "window_start",
    "checkin_time",
    "bedtime",
    "sleep_onset",
    "final_wake",
    "out_of_bed",
    "start",
    "end",
]


def load(data_dir, name):
    df = pd.read_csv(Path(data_dir) / f"{PREFIX}{name}.csv")
    if "data_source" not in df.columns or not (df["data_source"] == SOURCE).all():
        raise ValueError(f"{name} is not labelled {SOURCE}")
    for c in TIME_COLS:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c])
    return df


def save(df, out_dir, name):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    df = df.copy()
    df["data_source"] = SOURCE
    path = out / f"{PREFIX}{name}.csv"
    df.to_csv(path, index=False)
    return path


def runs(x):
    x = np.asarray(x)
    if len(x) == 0:
        return np.array([], int), np.array([], int), x[:0]
    change = np.flatnonzero(x[1:] != x[:-1]) + 1
    starts = np.concatenate([[0], change])
    lengths = np.diff(np.concatenate([starts, [len(x)]]))
    return starts, lengths, x[starts]
