import argparse
import json
from pathlib import Path

import pandas as pd

from . import config, heart, skin_temp, sleep
from .loaders import PREFIX, SOURCE, load, save

DISCLAIMER = (
    "All values are SIMULATED and validate processing logic only, not real-world accuracy. "
    "Sleep is an actigraphy-style estimate, not sleep stages. "
    "Temperature is skin surface temperature, not core body temperature. "
    "Mood is a non-clinical self-reported wellbeing check-in."
)


def daily_activity(act):
    d = act.assign(date=act["timestamp"].dt.date)
    g = d.groupby("date")
    return pd.DataFrame(
        {
            "movement_min": g["movement_minute"].sum(),
            "exercise_min": g["exercise_minute"].sum(),
            "minutes_recorded": g.size(),
        }
    ).reset_index()


def daily_mood(mood):
    m = mood.copy()
    m["date"] = pd.to_datetime(m["date"]).dt.date
    m["checkin_done"] = ~m["missed"].astype(bool)
    return m[["date", "mood_self_report_1to5", "checkin_done"]]


def build_daily_summary(activity_daily, sleep_nightly, hr_daily, temp_daily, mood_daily):
    s = activity_daily.copy()
    nights = sleep_nightly[sleep_nightly["est_sleep_min"] > 0]
    sl = nights.rename(columns={"sleep_date": "date"})[["date", "est_sleep_min", "est_sleep_h", "est_wake_bouts"]]
    for other in (sl, hr_daily, temp_daily, mood_daily):
        s = s.merge(other, on="date", how="left")
    s["checkin_done"] = s["checkin_done"].fillna(False).astype(bool)
    s["full_day"] = s["minutes_recorded"] >= 1440
    return s


def run(data_dir, out_dir, tolerance_bpm=5.0):
    sl = load(data_dir, "sleep_minute")
    pred = sleep.detect_sleep(sl)
    sleep_scores = sleep.score(pred, sl["true_asleep"])
    nightly = sleep.nightly_summary(sl, pred)
    nights_cmp = sleep.compare_nights(nightly, load(data_dir, "sleep_nights_truth"))

    hr_windows = heart.analyze_windows(load(data_dir, "ppg_raw"), load(data_dir, "ppg_windows"), tolerance_bpm)
    hr_scores = heart.evaluate_windows(hr_windows)
    hr_daily = heart.daily_hr_summary(load(data_dir, "heart_rate_minute"))

    t = load(data_dir, "skin_temp_minute")
    temp_alerts = skin_temp.trend_alerts(t)
    temp_result = skin_temp.evaluate_alerts(temp_alerts, t)
    temp_daily = skin_temp.daily_temp_summary(t, temp_alerts)

    summary = build_daily_summary(
        daily_activity(load(data_dir, "activity_minute")),
        nightly,
        hr_daily,
        temp_daily,
        daily_mood(load(data_dir, "mood_daily")),
    )

    files = {
        "daily_summary": save(summary, out_dir, "daily_summary"),
        "sleep_nightly": save(nightly, out_dir, "sleep_nightly"),
        "sleep_nights_vs_truth": save(nights_cmp, out_dir, "sleep_nights_vs_truth"),
        "hr_windows": save(hr_windows, out_dir, "hr_windows"),
        "alerts_skin_temp": save(temp_alerts, out_dir, "alerts_skin_temp"),
    }

    report = {
        **config.manifest_header(),
        "pipeline_note": DISCLAIMER,
        "sleep_epoch_scores": {k: round(v, 4) if isinstance(v, float) else v for k, v in sleep_scores.items()},
        "heart_rate_window_scores": {k: round(v, 4) if isinstance(v, float) else v for k, v in hr_scores.items()},
        "heart_rate_tolerance_bpm": tolerance_bpm,
        "skin_surface_temp_alerts": {k: str(v) if v is not None and not isinstance(v, (bool, int, float)) else v for k, v in temp_result.items()},
        "files": {k: Path(v).name for k, v in files.items()},
    }
    report_path = Path(out_dir) / f"{PREFIX}report.json"
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    return {
        "sleep_pred": pred,
        "sleep_scores": sleep_scores,
        "nightly": nightly,
        "nights_vs_truth": nights_cmp,
        "hr_windows": hr_windows,
        "hr_scores": hr_scores,
        "temp_alerts": temp_alerts,
        "temp_result": temp_result,
        "summary": summary,
        "report_path": report_path,
    }


def main():
    p = argparse.ArgumentParser(description="Process SIMULATED wearable data for every crew member.")
    p.add_argument("--data", default="data")
    p.add_argument("--out", default="output")
    a = p.parse_args()
    for crew_id in config.crew_ids():
        r = run(Path(a.data) / crew_id, Path(a.out) / crew_id)
        print(f"{crew_id}: {r['report_path']}")


if __name__ == "__main__":
    main()
