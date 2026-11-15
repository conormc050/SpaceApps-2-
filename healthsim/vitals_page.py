import json
from pathlib import Path

import pandas as pd
import streamlit as st

STATE_PATH = Path("data/demo/demo_state.json")

st.set_page_config(page_title="Live Vitals", page_icon="🫀", layout="wide")
state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
rules = state["rules"]

st.title("🫀 Live Vitals & Baseline")
st.info(f"{state['banner']}: demo values for logic validation only. Not medical advice.")

st.subheader("Tag login")
choice = st.radio("Tag tapped on the wearable (simulated)", list(state["crews"]), horizontal=True)
if st.button("Log in with tag", type="primary"):
    st.session_state["crew"] = choice
    st.rerun()

crew_id = st.session_state.get("crew")
if not crew_id:
    st.caption("Tap a tag to see that crew member's latest check-up.")
    st.stop()

n = state["crews"][crew_id]
st.success(f"Welcome, {crew_id}. Check-up received from the wearable.")

hr_delta = n["hr_now"] - n["hr_base"]
skin_delta = n["skin_now"] - n["skin_base"]
sleep_drop = n["sleep_base"] - n["sleep_now"]
wbc_drop = 1 - n["wbc_now"] / n["wbc_base"]
plt_drop = 1 - n["plt_now"] / n["plt_base"]
amber = {
    "Resting heart rate": hr_delta >= rules["hr"],
    "Skin surface temperature": skin_delta >= rules["skin"],
    "Sleep last night": sleep_drop >= rules["sleep"],
    "White cells": wbc_drop >= rules["blood"],
    "Platelets": plt_drop >= rules["blood"],
}
blood_flag = amber["White cells"] and amber["Platelets"]
overall = "AMBER" if any(amber.values()) else "GREEN"

c1, c2, c3 = st.columns(3)
c1.metric("Heart rate", f"{n['hr_now']} BPM", f"{hr_delta:+d} vs your baseline", delta_color="inverse")
c1.caption("Same number as the wrist display")
c2.metric("Movement today", f"{n['movement_min']} min")
c3.metric("Status", ("🟢 " if overall == "GREEN" else "🟠 ") + overall)

st.subheader("Compared with your own baseline")
rows = [
    ("Resting heart rate", f"{n['hr_base']} BPM", f"{n['hr_now']} BPM", f"{hr_delta:+d} BPM"),
    ("Skin surface temperature", f"{n['skin_base']} C", f"{n['skin_now']} C", f"{skin_delta:+.1f} C"),
    ("Sleep last night", f"{n['sleep_base']} h", f"{n['sleep_now']} h", f"{-sleep_drop:+.1f} h"),
    ("White cells", f"{n['wbc_base']} (x1000/uL)", f"{n['wbc_now']} (x1000/uL)", f"{-wbc_drop:+.0%}"),
    ("Platelets", f"{n['plt_base']} (x1000/uL)", f"{n['plt_now']} (x1000/uL)", f"{-plt_drop:+.0%}"),
]
table = pd.DataFrame(
    [
        {"Indicator": name, "Baseline": base, "Now": now, "Change": change, "Status": "🟠 AMBER" if amber[name] else "🟢 OK"}
        for name, base, now, change in rows
    ]
)
st.dataframe(table, hide_index=True)
st.caption("Skin temperature is skin surface temperature, not core body temperature. Blood panel is a simulated, planned sensor.")

if overall == "GREEN":
    st.success("All indicators are within your own baseline. No action needed.")
else:
    st.subheader("What to do")
    st.warning("Quick help: " + state["quick_help"]["resting_hr"])
    st.warning("Quick help: " + state["quick_help"]["sleep"])
    if blood_flag:
        st.error(
            "White cells and platelets are both falling: contact the flight surgeon straight away. "
            "This is an exposure indicator only, with many possible causes. It is not a radiation dose."
        )
    st.info("📡 Summary queued for Earth on the delayed link. Mood is only sent if abnormal.")

st.subheader("Cabin environment")
k1, k2, k3 = st.columns(3)
k1.metric("Temperature", f"{state['cabin']['temperature_c']:.0f} C")
k2.metric("Humidity", f"{state['cabin']['humidity_pct']:.0f} %")
k3.metric("Pressure", f"{state['cabin']['pressure_kpa']:.1f} kPa")

st.subheader("Score")
s1, s2 = st.columns(2)
s1.metric("This check-up", f"+{state['score']['points']}", f"x{state['score']['multiplier']:.2f} multiplier")
s2.dataframe(pd.DataFrame(state["scoreboard"]), hide_index=True)
st.caption("Points reward taking check-ups, never health values. Scoreboard values are examples.")
