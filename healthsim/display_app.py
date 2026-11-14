import os
import pandas as pd
import streamlit as st

# Page Configuration
st.set_page_config(
    page_title="Activity Summary Viewer", page_icon="📊", layout="centered"
)

st.title("📊 Health Activity Summary Dashboard")
st.write(
    "Showing the latest processed points and streaks from your Raspberry Pi"
    " hub."
)

# Path to your summary CSV file
SUMMARY_CSV_PATH = "data/ABC/activity_summary.csv"

# Add a manual refresh button
if st.button("🔄 Refresh Data"):
  st.rerun()

# Check if the summary file exists
if os.path.exists(SUMMARY_CSV_PATH):
  # Read the CSV file
  df = pd.read_csv(SUMMARY_CSV_PATH)

  if df.empty:
    st.info("The summary file exists, but it is currently empty.")
  else:
    # Display quick summary metrics at the top if columns exist
    if "points" in df.columns and "streak_days" in df.columns:
      col1, col2 = st.columns(2)
      with col1:
        st.metric(
            label="Highest Points Record", value=round(df["points"].max(), 1)
        )
      with col2:
        st.metric(
            label="Longest Streak Record", value=int(df["streak_days"].max())
        )
      st.divider()

    # Display the main data table
    st.subheader("Leaderboard & Activity Records")
    st.dataframe(df, use_container_width=True)

    # Option to download the summary straight from the browser
    csv_data = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Download Summary CSV",
        data=csv_data,
        file_name="activity_summary.csv",
        mime="text/csv",
    )
else:
  st.warning(
      f"⚠️ Waiting for summary file... Could not find `{SUMMARY_CSV_PATH}` yet."
      " Run your tracker script to generate it!"
  )