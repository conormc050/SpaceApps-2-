"""
Baseline activity tracker.

Reads a CSV of daily user activity and reports, per user:
  - active minutes, exercise minutes and steps (latest day + averages)
  - whether they've checked in within the last 24 hours
  - whether they have a streak of multiple consecutive days

Expected CSV columns (header row required):
    user_id, date, active_minutes, exercise_minutes, steps, last_checkin

  date          -> YYYY-MM-DD (one row per user per day)
  last_checkin  -> ISO timestamp, e.g. 2026-11-14 09:30:00

Usage:
    python activity_tracker.py data.csv
"""

import sys
from datetime import datetime, timedelta

import pandas as pd
import subprocess

# Config#
CSV_PATH = "data/ABC/Activity_Data.csv"
MIN_STREAK_DAYS = 2           # "multiple days in a row" = at least this many
CHECKIN_WINDOW = timedelta(hours=24)
# A day counts toward a streak if the user hit any of these minimums.
# Set all to 0 to count any logged day.
STREAK_MIN_ACTIVE_MINUTES = 1
STREAK_MIN_EXERCISE_MINUTES = 0


def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)

    required = {"user_id", "date", "active_minutes", "exercise_minutes", "last_checkin"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV is missing columns: {sorted(missing)}")

    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
    df["last_checkin"] = pd.to_datetime(df["last_checkin"], errors="coerce")

    for col in ("active_minutes", "exercise_minutes"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Drop rows with unusable dates, and duplicate user/day rows
    df = df.dropna(subset=["date"])
    df = df.sort_values(["user_id", "date"]).drop_duplicates(
        subset=["user_id", "date"], keep="last"
    )
    return df


def checked_in_last_24h(last_checkin, now: datetime) -> bool:
    if pd.isna(last_checkin):
        return False
    return (now - last_checkin) <= CHECKIN_WINDOW


def current_streak(user_df: pd.DataFrame, today: pd.Timestamp) -> int:
    """Length of the run of consecutive qualifying days ending today
    (or yesterday, so a streak isn't lost before the day is over)."""
    qualifying = user_df[
        (user_df["active_minutes"] >= STREAK_MIN_ACTIVE_MINUTES)
        & (user_df["exercise_minutes"] >= STREAK_MIN_EXERCISE_MINUTES)
    ]
    days = set(qualifying["date"])
    if not days:
        return 0

    if today in days:
        cursor = today
    elif (today - timedelta(days=1)) in days:
        cursor = today - timedelta(days=1)
    else:
        return 0

    streak = 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak

def points_for_stuff(user_df: pd.DataFrame, today: pd.Timestamp) -> int:#
    day_rows = user_df[user_df["date"] == today]
    if day_rows.empty:
        return 0.0

    row = day_rows.iloc[-1]
    total_points = 0
    streak = current_streak(user_df, today)
    active_minutes = row["active_minutes"]
    exercise_minutes = row["exercise_minutes"]
    excercise_points = (exercise_minutes * 1.5)


    if streak >= MIN_STREAK_DAYS & streak <=5:
        total_points =round(1.2 * (1 * excercise_points + active_minutes))

        return total_points
    
    elif 15<= streak >= 6:
        total_points =round(1.4 * (1 * excercise_points + active_minutes))

        return total_points  

    elif streak >= 16:
        total_points = round(1.6 * (1 * excercise_points + active_minutes))

        return total_points


def summarise(df: pd.DataFrame, now: datetime = None) -> pd.DataFrame:
    now = now or datetime.now()
    

    rows = []

    for user_id, user_df in df.groupby("user_id"):
        user_df = user_df.sort_values("date")
        for _,row in user_df.iterrows():
            streak = current_streak(user_df, row["date"])
            row_date = row["date"]
            rows.append({
                "user_id": user_id,
                "latest_date": row["date"].date(),
                "active_minutes": row["active_minutes"],
                "exercise_minutes": row["exercise_minutes"],
                "avg_active_minutes": round(user_df["active_minutes"].mean(), 1),
                "checked_in_24h": checked_in_last_24h(row["last_checkin"], now),
                "streak_days": streak,
                "has_streak": streak >= MIN_STREAK_DAYS,
                "points": points_for_stuff(user_df, row_date)
            })
    return pd.DataFrame(rows) 


def combine_activity_data(questionnaire_path, sensor_path, output_path):
    # 1. Load both CSV files
    df_questionnaire = pd.read_csv(questionnaire_path)
    df_sensors = pd.read_csv(sensor_path)
    
    # 2. Normalize the date columns so they match perfectly (YYYY-MM-DD)
    df_questionnaire["date"] = pd.to_datetime(df_questionnaire["date"]).dt.normalize().dt.date
    df_sensors["date"] = pd.to_datetime(df_sensors["date"]).dt.normalize().dt.date
    
    # 3. Merge the datasets together
    # Using an 'inner' join keeps only rows where both questionnaire and sensor data exist for that user/date.
    # Change to 'outer' if you want to keep data even if one side is missing.
    combined_df = pd.merge(
        df_questionnaire, 
        df_sensors, 
        on=["user_id", "date"], 
        how="inner"
    )
    
    # 4. Save the combined result to a new master CSV
    combined_df.to_csv(output_path, index=False)
    print(f"Successfully combined data! Saved to {output_path}")
    print(combined_df.head())

def main():
    if len(sys.argv) < 2:
        print("Usage: python healthsim/pointsSystem.py data/ABC/Activity_Data.csv")
        sys.exit(1)

    df = load_data(sys.argv[1])
    summary = summarise(df)

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", None)
    print(summary.to_string(index=False))

    summary.to_csv("activity_summary.csv", index=False)
    print("\nSaved summary to activity_summary.csv")
    # sends the csv to a pi via scp, need to change the ip to the pi's ip address.
    # subprocess.run(["scp", "activity_summary.csv", "pi@192.168.1.50:/home/pi/"])


# Inside main(), after saving the CSV:

if __name__ == "__main__":
    # Update these paths to match your actual file locations
    # q_file = "data/ABC/Activity_Data.csv"
    # pi_file = "data/ABC/Pi_Sensor_Data.csv"
    # master_file = "data/ABC/Master_Combined_Activity.csv"
    
    # combine_activity_data(q_file, pi_file, master_file)
    main()