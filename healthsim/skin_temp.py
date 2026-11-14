import numpy as np
import pandas as pd

LABEL = "skin surface temperature (not core body temperature)"


def hourly(df):
    return df.set_index("timestamp")["skin_surface_temp_c"].resample("1h").median()


def trend_alerts(df, threshold_c=0.5, current_h=24, baseline_h=72, min_baseline_h=48, sustain_h=6):
    h = hourly(df)
    cur = h.rolling(current_h, min_periods=int(current_h * 0.75)).mean()
    base = h.shift(current_h).rolling(baseline_h, min_periods=min_baseline_h).mean()
    delta = cur - base
    above = (delta >= threshold_c).astype(int)
    alert = above.rolling(sustain_h, min_periods=sustain_h).sum() >= sustain_h
    out = pd.DataFrame(
        {
            "hour": h.index,
            "current_24h_mean_skin_surface_temp_c": cur.round(3).to_numpy(),
            "baseline_72h_mean_skin_surface_temp_c": base.round(3).to_numpy(),
            "delta_c": delta.round(3).to_numpy(),
            "alert": alert.to_numpy(),
        }
    )
    out["status"] = np.where(base.isna().to_numpy(), "warming_up", np.where(out["alert"], "alert", "normal"))
    out["measurement"] = LABEL
    return out


def alert_events(alerts):
    a = alerts["alert"].to_numpy()
    edges = np.flatnonzero(a & ~np.concatenate([[False], a[:-1]]))
    return alerts.iloc[edges][["hour", "delta_c"]].reset_index(drop=True)


def evaluate_alerts(alerts, truth_df):
    truth = truth_df.set_index("timestamp")["true_rise_active"].resample("1h").max().reindex(alerts["hour"]).fillna(0).to_numpy()
    a = alerts["alert"].to_numpy()
    onset_idx = np.flatnonzero(truth)
    onset = alerts["hour"].iloc[onset_idx[0]] if len(onset_idx) else None
    before = a[: onset_idx[0]] if len(onset_idx) else a
    after = a[onset_idx[0] :] if len(onset_idx) else np.array([], bool)
    first = alerts["hour"].iloc[np.flatnonzero(after)[0] + onset_idx[0]] if after.any() else None
    return {
        "rise_injected": onset is not None,
        "rise_onset": onset,
        "false_alarm_hours": int(before.sum()),
        "fired_after_onset": bool(after.any()),
        "first_alert": first,
        "detection_delay_h": (first - onset).total_seconds() / 3600 if first is not None else None,
    }


def daily_temp_summary(df, alerts):
    d = df.assign(date=df["timestamp"].dt.date)
    s = d.groupby("date")["skin_surface_temp_c"].agg(["mean", "min", "max"]).round(2)
    s.columns = ["skin_surface_temp_mean_c", "skin_surface_temp_min_c", "skin_surface_temp_max_c"]
    al = alerts.assign(date=alerts["hour"].dt.date).groupby("date")["alert"].any().rename("skin_surface_temp_trend_alert")
    return s.join(al).fillna({"skin_surface_temp_trend_alert": False}).reset_index()
