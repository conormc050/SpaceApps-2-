# two pipeplines for headers and data formth eone csv file
from datetime import datetime
import os
import pandas as pd
import streamlit as st

st.title("Activity & Excercise Tracker Questionnaire")

# Create a simple form for users to fill out
with st.form("questionnaire_form"):
  user_id = st.text_input("User ID (e.g., user_123)")
  active_minutes = st.number_input(
      "Active Minutes today", min_value=0, value=30
  )
  exercise_minutes = st.number_input(
      "Exercise Minutes today", min_value=0, value=0
  )

  submitted = st.form_submit_button("Submit Activity")

  if submitted:
    if not user_id:
      st.error("Please enter a User ID.")
    else:
      # Format data matching your CSV columns
      new_row = {
          "user_id": user_id,
          "date": datetime.now().strftime("%Y-%m-%d"),
          "active_minutes": active_minutes,
          "exercise_minutes": exercise_minutes,
          "last_checkin": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
      }

      csv_path = "data/ABC/Activity_Data.csv"

      # Append the new submission directly into your CSV file
      df_new = pd.DataFrame([new_row])
      if os.path.exists(csv_path):
        df_new.to_csv(csv_path, mode="a", header=False, index=False)
      else:
        df_new.to_csv(csv_path, index=False)

      st.success(
          f"Success! Data saved for {user_id} in {csv_path}."
      )