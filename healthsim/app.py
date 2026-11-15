from datetime import datetime
import os
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Health Tracking Hub", page_icon="🏃", layout="wide"
)

st.title("🏃 Health Activity & Telemetry Hub")

# --- SECTION 1: DYNAMIC CHECK-IN SIDEBAR (No form wrapper) ---
with st.sidebar:
  st.header("📝 Daily Health & Check-in")

  user_id = st.text_input("User ID (e.g., user_123)")
  active_minutes = st.number_input(
      "Active Minutes today", min_value=0.0, value=30.0
  )
  exercise_minutes = st.number_input(
      "Exercise Minutes today", min_value=0.0, value=10.0
  )

  st.divider()
  st.subheader("🦴 Bone & Posture Check")
  posture_change = st.radio(
      "Noticed changes in posture or back feel?", ["No", "Yes"], index=0
  )

  # This second question will dynamically appear ONLY when "Yes" is selected above
  aches_reported = "No"
  if posture_change == "Yes":
    aches_reported = st.radio(
        "Any new or persistent aches in back or hips?", ["No", "Yes"], index=0
    )

  st.divider()
  st.subheader("🧠 Mental Health Check")
  mental_health_score = st.slider(
      "How are you feeling today? (1 = Very Poor, 5 = Excellent)",
      min_value=1,
      max_value=5,
      value=3,
  )

  st.markdown("---")
  submitted = st.button("Submit Questionnaire", type="primary")

  if submitted:
    if not user_id:
      st.error("Please enter a User ID.")
    else:
      # Check if medical escalation is needed
      needs_medical_review = posture_change == "Yes" and aches_reported == "Yes"

      # Save record
      now_str = datetime.now()
      new_row = {
          "user_id": user_id,
          "date": now_str.strftime("%Y-%m-%d"),
          "active_minutes": active_minutes,
          "exercise_minutes": exercise_minutes,
          "posture_change": posture_change,
          "back_hip_aches": aches_reported,
          "mental_health_score": mental_health_score,
          "last_checkin": now_str.strftime("%Y-%m-%d %H:%M:%S"),
      }

      csv_path = "data/ABC/Activity_Summary.csv"
      os.makedirs(os.path.dirname(csv_path), exist_ok=True)
      df_new = pd.DataFrame([new_row])

      if os.path.exists(csv_path):
        df_new.to_csv(csv_path, mode="a", header=False, index=False)
      else:
        df_new.to_csv(csv_path, index=False)

      # Display appropriate user feedbacks
      if needs_medical_review:
        st.warning(
            "🚨 Sending data to earth/nasa medical team/professionals, will be"
            " in touch with plan"
        )
      else:
        st.success(f"Activity & check-in saved successfully for {user_id}!")

# --- SECTION 2: LIVE SUMMARY & LEADERBOARD DISPLAY ---
st.header("📊 Live Activity & Summary")
summary_path = "data/ABC/Activity_Summary.csv"

if st.button("🔄 Refresh Data"):
  st.rerun()

if os.path.exists(summary_path):
  df_summary = pd.read_csv(summary_path)
  if not df_summary.empty:
    st.dataframe(df_summary, use_container_width=True)
  else:
    st.info("Summary file is currently empty.")
else:
  st.warning("Waiting for activity summary file...")