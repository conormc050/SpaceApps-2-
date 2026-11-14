import numpy as np
import pandas as pd

ACTIVE_COUNT_THR = 150
EXERCISE_COUNT_THR = 400
# take out the sleep counting for points we dont really need that mf.
RULES = {
    "active_count_thr": 150,
    "exercise_count_thr":400,
    "full_day_minutes": 1440,
    "sleep_full_h": 7.0,
    "sleep_full_pts": 30,
    "sleep_partial_h": 6.0,
    "sleep_partial_pts": 15,
    "steps_per_block": 2000,
    "pts_per_step_block": 10,
    "steps_cap": 50,
    "active_pts_per_min": 1,
    "active_cap": 30,
    "exercise_min": 20,
    "exercise_pts": 20,
    "checkin_pts": 10,
    "wear_coverage": 0.8,
    "wear_pts": 10,
    "streak_pts_per_day": 5,
    "streak_cap": 25,

    "mission_days": 30,

    
}

def _cfg(rules=None):
    return {**RULES, **(rules or {})}

PTS_COLS =["pts_steps", "pts_active", "pts_exercise", "pts_checkin", "pts_wear", "pts_streak", "pts_mission"]

def daily_activity(act, rules=None):
    r=_cfg(rules)
    d = act.assign(
        date=act["timestamp"].dt.date,
        active=act["activity_count"] >= r["active_count_thr"],
        exercise=act["activity_count"] >= r["exercise_count_thr"],
    )
    return (
        {
            d.groupby("date")
              .agg(steps=("steps", "sum"), active_min=("active", "sum"), exercise_min=("exercise", "sum"), minutes_recorded=("timestamp", lambda x: x.dt.minute.count()))
        }
    ).reset_index()


def daily_mood(mood):
    m = mood.copy()
    m["date"] = pd.to_datetime(m["date"]).dt.date
    m["checkin_done"] = ~m["missed"].astype(bool)
    return m[["date", "mood_self_report_1to5", "checkin_done"]]


def build_daily_summary(activity_daily, sleep_nightly, hr_daily, temp_daily, mood_daily, rules=None):
    r = _cfg(rules)
    s=activity_daily.copy()
    sl = sleep_nightly.rename(columns={"sleep_date": "date"})[
        ["date", "est_sleep_min", "est_sleep_h", "est_wake_bouts"]]
    # sl = sleep_nightly.rename(columns={"sleep_date": "date"})[["date", "est_sleep_min", "est_sleep_h", "est_wake_bouts"]]
    for other in (sl, hr_daily, temp_daily, mood_daily):
        s = s.merge(other, on="date", how="left")
    s["checkin_done"] = s["checkin_done"].fillna(False).astype(bool)
    s["full_day"] = s["minutes_recorded"] >= r["full_day_minutes"]
    return s.sort_values("date").reset_index(drop=True)


def checkin_streak(done):
    streak = []
    n = 0
    for d in done:
        n = n + 1 if d else 0
        streak.append(n)
    return np.array(streak)


def add_points(summary, rules=RULES):
    s = summary.copy()
    sleep_h = s["est_sleep_h"].fillna(0)
    s["pts_sleep"] = np.select(
        [sleep_h >= rules["sleep_full_h"], sleep_h >= rules["sleep_partial_h"]],
        [rules["sleep_full_pts"], rules["sleep_partial_pts"]],
        0,
    )
    s["pts_steps"] = np.minimum(rules["steps_cap"], (s["steps"] // rules["steps_per_block"]) * rules["pts_per_step_block"]).astype(int)
    s["pts_active"] = np.minimum(rules["active_cap"], s["active_min"] * rules["active_pts_per_min"]).astype(int)
    s["pts_exercise"] = np.where(s["exercise_min"] >= rules["exercise_min"], rules["exercise_pts"], 0)
    s["pts_checkin"] = np.where(s["checkin_done"], rules["checkin_pts"], 0)
    s["pts_wear"] = np.where(s["hr_coverage"].fillna(0) >= rules["wear_coverage"], rules["wear_pts"], 0)
    s["checkin_streak_days"] = checkin_streak(s["checkin_done"])
    s["pts_streak"] = np.minimum(rules["streak_cap"], np.maximum(s["checkin_streak_days"] - 1, 0) * rules["streak_pts_per_day"])
    cols = ["pts_sleep", "pts_steps", "pts_active", "pts_exercise", "pts_checkin", "pts_wear", "pts_streak"]
    s["points_total"] = s[cols].sum(axis=1).astype(int)
    s["points_cumulative"] = s["points_total"].cumsum()
    return s

def mission_Points(summary, rules=RULES):
    s= summary.copy()
    s["pts_mission"] = np.where(s["points_cumulative"] / rules["mission_days"], 100, 0)