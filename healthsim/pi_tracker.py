"""
Raspberry Pi 5 Activity Tracker & Bluetooth Listener.
Reads incoming data from an Arduino via Bluetooth (/dev/rfcomm0),
logs it to CSV, and calculates points/streaks.
"""

from datetime import datetime, timedelta
import os
import sys
import serial
import pandas as pd

# --- CONFIGURATION ---
BLUETOOTH_PORT = "/dev/rfcomm0"  # Standard Pi Bluetooth serial binding path
BAUD_RATE = 9600
SENSOR_CSV_PATH = "data/ABC/Pi_Sensor_Data.csv"
MIN_STREAK_DAYS = 2
CHECKIN_WINDOW = timedelta(hours=24)
STREAK_MIN_ACTIVE_MINUTES = 1
STREAK_MIN_EXERCISE_MINUTES = 0


def load_data(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        # Return an empty DataFrame with correct columns if file doesn't exist yet
        return pd.DataFrame(columns=["user_id", "date", "active_minutes", "exercise_minutes", "last_checkin"])
        
    df = pd.read_csv(path)
    required = {"user_id", "date", "active_minutes", "exercise_minutes", "last_checkin"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV is missing columns: {sorted(missing)}")

    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
    df["last_checkin"] = pd.to_datetime(df["last_checkin"], errors="coerce")

    for col in ("active_minutes", "exercise_minutes"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

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
    qualifying = user_df[
        (user_df["active_minutes"] >= STREAK_MIN_ACTIVE_MINUTES)
        & (user_df["exercise_minutes"] >= STREAK_MIN_EXERCISE_MINUTES)
        & (user_df["date"] <= today)
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


def points_for_stuff(user_df: pd.DataFrame, today: pd.Timestamp) -> float:
    day_rows = user_df[user_df["date"] == today]
    if day_rows.empty:
        return 0.0
    
    row = day_rows.iloc[-1]
    streak = current_streak(user_df, today)
    
    active_minutes = row["active_minutes"]
    exercise_minutes = row["exercise_minutes"]
    exercise_points = exercise_minutes * 1.5

    if 2 <= streak <= 5:
        return round(1.2 * (exercise_points + active_minutes), 2)
    elif 6 <= streak <= 15:
        return round(1.4 * (exercise_points + active_minutes), 2)
    elif streak >= 16:
        return round(1.6 * (exercise_points + active_minutes), 2)
    
    return 0.0


def summarise(df: pd.DataFrame, now: datetime = None) -> pd.DataFrame:
    now = now or datetime.now()
    rows = []
    
    for user_id, user_df in df.groupby("user_id"):
        user_df = user_df.sort_values("date")
        
        for _, row in user_df.iterrows():
            row_date = row["date"]
            streak = current_streak(user_df, row_date)
            
            rows.append({
                "user_id": user_id,
                "date": row_date.date(),
                "active_minutes": row["active_minutes"],
                "exercise_minutes": row["exercise_minutes"],
                "checked_in_24h": checked_in_last_24h(row["last_checkin"], now),
                "streak_days": streak,
                "has_streak": streak >= MIN_STREAK_DAYS,
                "points": points_for_stuff(user_df, row_date)
            })
            
    return pd.DataFrame(rows)


def log_incoming_bluetooth_data():
    """Listens to the Bluetooth port and appends incoming Arduino data to CSV."""
    print(f"Listening for Arduino on Bluetooth port {BLUETOOTH_PORT}...")
    
    os.makedirs(os.path.dirname(SENSOR_CSV_PATH), exist_ok=True)
    
    try:
        ser = serial.Serial(BLUETOOTH_PORT, BAUD_RATE, timeout=1)
        print("Connected! Waiting for data stream... (Press Ctrl+C to stop & run summary)\n")
        
        while True:
            if ser.in_waiting > 0:
                raw_line = ser.readline().decode('utf-8', errors='ignore').strip()
                if raw_line:
                    print(f"Received: {raw_line}")
                    parts = raw_line.split(",")
                    
                    if len(parts) >= 3:
                        user_id = parts[0].strip()
                        active_mins = float(parts[1].strip())
                        exercise_mins = float(parts[2].strip())
                        
                        now_str = datetime.now()
                        new_row = {
                            "user_id": user_id,
                            "date": now_str.strftime("%Y-%m-%d"),
                            "active_minutes": active_mins,
                            "exercise_minutes": exercise_mins,
                            "last_checkin": now_str.strftime("%Y-%m-%d %H:%M:%S")
                        }
                        
                        df_new = pd.DataFrame([new_row])
                        file_exists = os.path.exists(SENSOR_CSV_PATH)
                        df_new.to_csv(SENSOR_CSV_PATH, mode="a", header=not file_exists, index=False)
                        print(f"-> Logged to {SENSOR_CSV_PATH}\n")
                        
    except serial.SerialException as e:
        print(f"\n[Note] Could not open Bluetooth port {BLUETOOTH_PORT}: {e}")
        print("If testing without Arduino connected, running summary on existing data...")
    except KeyboardInterrupt:
        print("\nStopped listening. Generating final activity summary...")


def main():
    # 1. Listen for incoming Bluetooth data (Stays in loop until you press Ctrl+C)
    log_incoming_bluetooth_data()

    # 2. Once stopped or if testing, load the logged data and compute points summary
    df = load_data(SENSOR_CSV_PATH)
    if df.empty:
        print("No sensor data found in CSV to summarize.")
        return

    summary = summarise(df)

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", None)
    print("\n--- Activity & Points Summary ---")
    print(summary.to_string(index=False))

    output_summary_path = "data/ABC/activity_summary.csv"
    summary.to_csv(output_summary_path, index=False)
    print(f"\nSaved summary to {output_summary_path}")


if __name__ == "__main__":
    main()