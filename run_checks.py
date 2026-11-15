import argparse
import json
import re
import shutil
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from healthsim import bridge, config, gamify, heart, pipeline, protocol, simulate, tags
from healthsim.loaders import PREFIX, SOURCE, load

SECTIONS = [
    "meta", "simulation", "schedule", "sleep", "sensors", "crew", "scenarios", "baselines", "alerts", "mood",
    "scoring", "lcd", "serial", "hardware", "live", "link", "blood", "blood_sugar", "blood_pressure", "cabin",
]

STRESS = {
    "ppg_noise_sd": 0.2,
    "ppg_motion_noise_mult": 3.0,
    "ppg_dropout_prob": 0.4,
    "ppg_hrv_sd": 0.05,
    "hr_sensor_noise_sd": 6.0,
    "hr_dropouts_per_day": 15.0,
    "temp_noise_sd": 0.15,
    "temp_drift_sd": 0.2,
    "temp_missing_prob": 0.02,
}

NORMAL_LIMITS = {
    "sleep_accuracy": 0.90,
    "sleep_precision": 0.85,
    "sleep_recall": 0.85,
    "night_error_min": 60,
    "hr_ok_fraction": 0.85,
    "hr_within_tol": 0.95,
    "temp_extra_delay_h": 0,
}

STRESS_LIMITS = {
    "sleep_accuracy": 0.90,
    "sleep_precision": 0.85,
    "sleep_recall": 0.85,
    "night_error_min": 60,
    "hr_ok_fraction": 0.60,
    "hr_within_tol": 0.85,
    "temp_extra_delay_h": 24,
}


class Report:
    def __init__(self):
        self.rows = []

    def check(self, scenario, name, ok, detail=""):
        self.rows.append((scenario, name, bool(ok), detail))
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))

    @property
    def failed(self):
        return [r for r in self.rows if not r[2]]


def check_simulator(rep, data_dir, tag, crew_id):
    d = Path(data_dir)
    sim = config.section("simulation")
    sensors = config.section("sensors")
    sched = config.section("schedule")
    cal = sim["calibration_days"]
    total = config.total_days()
    sc = config.scenario(crew_id)
    crew = config.crew(crew_id)
    onset_days = sc["onset_after_days"]
    onset_min = None if onset_days is None else int(onset_days * 1440)

    csvs = sorted(d.glob(f"{PREFIX}*.csv"))
    frames = {p.stem.replace(PREFIX, ""): pd.read_csv(p) for p in csvs}
    unlabelled = [n for n, f in frames.items() if not (f["data_source"] == SOURCE).all()]
    rep.check(tag, "every CSV row labelled SIMULATED", not unlabelled and len(frames) >= 9, f"{len(frames)} files")
    wrong_crew = [n for n, f in frames.items() if not (f["crew"] == crew_id).all()]
    rep.check(tag, "every CSV row names its crew member", not wrong_crew)
    manifest = json.loads((d / f"{PREFIX}manifest.json").read_text(encoding="utf-8"))
    rep.check(
        tag,
        "manifest carries SIMULATED disclaimer, AI acknowledgement, crew and scenario",
        manifest["data_source"] == SOURCE and "not core" in manifest["disclaimer"] and "AI" in manifest["ai_acknowledgement"]
        and manifest["crew"] == crew_id and manifest["scenario"] == crew["scenario"],
    )

    hr = load(d, "heart_rate_minute")
    ts = hr["timestamp"]
    raw_ts = frames["heart_rate_minute"]["timestamp"]
    start = pd.Timestamp(sim["start_utc"])
    step_ok = (ts.diff().dropna() == pd.Timedelta(minutes=1)).all()
    rep.check(
        tag,
        "timestamps are UTC (Z suffix), start at start_utc, one per minute",
        raw_ts.str.endswith("Z").all() and str(ts.dt.tz) == "UTC" and ts.iloc[0] == start and len(ts) == total * 1440 and step_ok,
        f"{len(ts)} rows",
    )
    step_cols = [f"{n}.{c}" for n, f in frames.items() for c in f.columns if "step" in c.lower()]
    act = frames["activity_minute"]
    rep.check(tag, "no step counts anywhere; movement and exercise minutes instead", not step_cols and {"movement_minute", "exercise_minute"} <= set(act.columns), ", ".join(step_cols))
    missing_truth = [f"{n}.{c}" for n, cols in manifest["ground_truth_columns"].items() for c in cols if c not in frames[n].columns]
    rep.check(tag, "ground-truth labels kept in every table", not missing_truth, ", ".join(missing_truth))

    nights = load(d, "sleep_nights_truth")
    h = nights["true_sleep_min"] / 60
    lo, hi = sensors["sleep_h_limits"]
    rep.check(tag, "true sleep ISS-like, under the scheduled hours and inside limits", h.between(lo, hi).all() and (h < sched["scheduled_sleep_h"]).all(), f"{h.min():.2f}-{h.max():.2f} h")
    crew_mean = manifest["sleep_mean_h"]
    cal_h = h[nights["night_id"] < cal]
    rep.check(tag, "calibration-week sleep mean within 0.5 h of the crew mean", abs(cal_h.mean() - crew_mean) <= 0.5, f"{cal_h.mean():.2f} h against {crew_mean}")
    deficit = nights["true_sleep_deficit_h"]
    if onset_days is None:
        zero_ok = (deficit == 0).all()
        scen_start = cal
        expected_shift = 0.0
    else:
        zero_ok = (deficit[nights["night_id"] < onset_days] == 0).all() and abs(deficit.max() - sc["sleep_deficit_h"]) < 1e-6
        scen_start = int(onset_days + sc["ramp_days"])
        expected_shift = -sc["sleep_deficit_h"]
    rep.check(tag, "injected sleep deficit is zero before onset and reaches the scenario value", zero_ok, f"max {deficit.max():.2f} h")
    scen_h = h[nights["night_id"] >= scen_start]
    shift = scen_h.mean() - cal_h.mean()
    rep.check(tag, "sleep after the ramp shifts by the scenario deficit (within 0.75 h)", len(scen_h) >= 2 and abs(shift - expected_shift) <= 0.75, f"shift {shift:+.2f} h, expected {expected_shift:+.2f}, {len(scen_h)} nights")

    ex = load(d, "exercise_sessions_truth")
    block = sched["exercise_block_min"]
    start_hhmm = crew["exercise_start_utc"]
    same_start = (ex["start"].dt.strftime("%H:%M") == start_hhmm).all()
    one_a_day = ex["start"].dt.date.is_unique and len(ex) == total
    sleep_min = frames["sleep_minute"]
    overlap = int(((act["true_state"] == "exercise") & (sleep_min["true_in_bed"] == 1)).sum())
    rep.check(tag, f"one {block} min exercise block per day at {start_hhmm} UTC, never in bed", one_a_day and same_start and (ex["minutes"] == block).all() and overlap == 0, f"{len(ex)} blocks")

    base = manifest["simulated_person_hr_baseline_bpm"]
    lo_b, hi_b = sensors["hr_baseline_bpm"]
    rep.check(tag, "person HR baseline inside the configured range", lo_b <= base <= hi_b, str(base))
    rise = hr["true_resting_hr_offset_bpm"]
    rise_ok = abs(rise.max() - sc["resting_hr_rise_bpm"]) < 1e-3
    if onset_min is not None:
        rise_ok = rise_ok and (rise.iloc[:onset_min] == 0).all()
    rep.check(tag, "resting HR rise is zero in calibration and reaches the scenario value", rise_ok, f"max {rise.max():.1f} BPM")

    t = load(d, "skin_temp_minute")
    med = t["skin_surface_temp_c"].median()
    off = t["true_injected_offset_c"]
    off_ok = abs(off.max() - sc["skin_temp_rise_c"]) < 1e-3 and (onset_min is None or (off.iloc[:onset_min] == 0).all())
    rep.check(tag, "skin surface temp column named, centred 33-35 C", "skin_surface_temp_c" in t.columns and 33 <= med <= 35, f"median {med:.2f}")
    rep.check(tag, "skin temp offset is zero in calibration and reaches the scenario value", off_ok, f"max {off.max():.2f} C")

    m = load(d, "mood_daily")
    v = m["mood_self_report_1to5"].dropna()
    rep.check(tag, "mood check-ins within 1-5, missed left blank", v.between(1, 5).all() and m.loc[m["missed"], "mood_self_report_1to5"].isna().all())
    rep.check(tag, "mood step size at most 1 per day", (m["true_mood_1to5"].diff().abs().dropna() <= 1).all())


def check_processing(rep, r, tag, limits, crew_id):
    s = r["sleep_scores"]
    rep.check(tag, f"sleep accuracy >= {limits['sleep_accuracy']}", s["accuracy"] >= limits["sleep_accuracy"], f"{s['accuracy']:.3f}")
    rep.check(tag, f"sleep precision >= {limits['sleep_precision']}", s["precision"] >= limits["sleep_precision"], f"{s['precision']:.3f}")
    rep.check(tag, f"sleep recall >= {limits['sleep_recall']}", s["recall"] >= limits["sleep_recall"], f"{s['recall']:.3f}")
    err = r["nights_vs_truth"]["sleep_min_error"].abs()
    rep.check(tag, f"nightly sleep total within {limits['night_error_min']} min", err.notna().all() and err.max() <= limits["night_error_min"], f"max {err.max():.0f} min")

    hs = r["hr_scores"]
    rep.check(tag, f"HR windows usable >= {limits['hr_ok_fraction']:.0%}", hs["ok_fraction"] >= limits["hr_ok_fraction"], f"{hs['ok_fraction']:.1%}")
    rep.check(tag, f"HR within tolerance >= {limits['hr_within_tol']:.0%}", hs["within_tolerance_fraction"] >= limits["hr_within_tol"], f"{hs['within_tolerance_fraction']:.1%}, MAE {hs['mae_bpm']:.2f} BPM")
    w = r["hr_windows"]
    rep.check(tag, "unusable HR windows reported as NaN, not guessed", w.loc[w["status"] != "ok", "est_bpm"].isna().all())

    res = r["temp_result"]
    sc = config.scenario(crew_id)
    rep.check(tag, "skin temp: no alert before any injected rise", res["false_alarm_hours"] == 0, f"{res['false_alarm_hours']} alert hours")
    if res["rise_injected"]:
        limit_h = sc["max_alert_delay_days"] * 24 + limits["temp_extra_delay_h"]
        delay = res["detection_delay_h"]
        rep.check(tag, f"skin temp: alert fires on rise within {limit_h} h", res["fired_after_onset"] and delay <= limit_h, f"delay {delay} h")
    else:
        rep.check(tag, "skin temp: no alert at all for a crew member with no scenario", not r["temp_alerts"]["alert"].any())


def check_summary(rep, r, tag):
    s = r["summary"]
    total = config.total_days()
    rep.check(tag, "daily summary has one row per date, no step column", s["date"].is_unique and len(s) == total and not [c for c in s.columns if "step" in c.lower()] and {"movement_min", "exercise_min"} <= set(s.columns), f"{len(s)} days")


def check_rules(rep):
    base = pd.DataFrame(
        {
            "est_sleep_h": [7.5, 6.5, 5.0],
            "steps": [25000, 4100, 0],
            "active_min": [90, 12, 0],
            "exercise_min": [30, 19, 0],
            "checkin_done": [True, True, False],
            "hr_coverage": [0.95, 0.5, np.nan],
        }
    )
    p = gamify.add_points(base)
    rep.check("rules", "sleep points 30/15/0 for 7.5/6.5/5 h", p["pts_sleep"].tolist() == [30, 15, 0])
    rep.check("rules", "step points capped at 50 and 10 per 2000", p["pts_steps"].tolist() == [50, 20, 0])
    rep.check("rules", "exercise bonus needs 20 min", p["pts_exercise"].tolist() == [20, 0, 0])
    rep.check("rules", "streak bonus grows then resets", p["checkin_streak_days"].tolist() == [1, 2, 0] and p["pts_streak"].tolist() == [0, 5, 0])
    rep.check("rules", "worn-device points need 80% coverage", p["pts_wear"].tolist() == [10, 0, 0])
    fs = 50
    t = np.arange(30 * fs) / fs
    clean = np.round(512 + 150 * np.sin(2 * np.pi * 1.2 * t) ** 21).astype(int)
    off = clean.copy()
    off[: 20 * fs] = 1023
    flat = np.full(30 * fs, 500)
    r_clean = heart.estimate_bpm(clean, fs)
    r_off = heart.estimate_bpm(off, fs)
    r_flat = heart.estimate_bpm(flat, fs)
    rep.check("rules", "HR estimate on synthetic 72 BPM pulse", r_clean["status"] == "ok" and abs(r_clean["est_bpm"] - 72) <= 1, f"{r_clean['est_bpm']:.1f} BPM")
    rep.check("rules", "HR window 2/3 saturated returns NaN", r_off["status"] == "insufficient_signal" and np.isnan(r_off["est_bpm"]))
    rep.check("rules", "HR flat-line window returns NaN", r_flat["status"] == "insufficient_signal" and np.isnan(r_flat["est_bpm"]))


def raises(fn, *args):
    try:
        fn(*args)
    except ValueError:
        return True
    return False


def check_foundation(rep):
    s = config.settings()
    missing = [k for k in SECTIONS if k not in s]
    rep.check("foundation", "settings file has every section", not missing, ", ".join(missing))
    rep.check("foundation", "settings labelled SIMULATED and match loaders", config.SOURCE == SOURCE and config.PREFIX == PREFIX and SOURCE in config.BANNER)
    head = config.manifest_header()
    rep.check("foundation", "manifest header carries disclaimer and AI acknowledgement", "not core" in head["disclaimer"] and "non-clinical" in head["disclaimer"] and "not a radiation dose" in head["disclaimer"] and "AI" in head["ai_acknowledgement"])
    cols, rows = config.lcd_size()
    labels = [config.BANNER] + [a["lcd_label"] for a in s["alerts"].values()]
    too_wide = [t for t in labels if len(t) > cols]
    rep.check("foundation", f"banner and status labels fit {cols} columns", not too_wide, ", ".join(too_wide))
    rep.check("foundation", "every alert has quick help and a contact point", all(a.get("quick_help") and a.get("contact_when") for a in s["alerts"].values()), f"{len(s['alerts'])} indicators")
    sc = s["scoring"]
    rep.check("foundation", "multiplier settings 1x start, 0.25x step, 2x cap", (sc["multiplier_start"], sc["multiplier_step"], sc["multiplier_cap"]) == (1.0, 0.25, 2.0))
    rep.check("foundation", "scoring settings hold no steps and no health values", not any("step" in k and k != "multiplier_step" for k in sc) and sc["points_from_health_values"] is False)
    expected = {c: config.scenario(c)["expected_alerts"] for c in config.crew_ids()}
    rep.check("foundation", "crew is ABC with no expected alerts and DEF with some", config.crew_ids() == ["ABC", "DEF"] and expected["ABC"] == [] and len(expected["DEF"]) >= 4 and set(expected["DEF"]) <= set(s["alerts"]))
    rep.check("foundation", "simulated tags resolve to crew, unknown tag does not", all(tags.lookup(tags.simulated_uid(c)) == c for c in config.crew_ids()) and tags.lookup("SIM-TAG-XYZ") is None)
    tag_doc = json.loads(config.TAGS_PATH.read_text(encoding="utf-8"))
    hashed = all(re.fullmatch(r"[0-9a-f]{64}", h) for h in tag_doc["tags"])
    no_real = all(u.startswith("SIM-") for u in tag_doc["simulated_uids"].values())
    ignored = "config/tags.local.json" in (config.ROOT / ".gitignore").read_text(encoding="utf-8")
    rep.check("foundation", "tag file holds only hashes and SIM- ids, local file ignored by git", hashed and no_real and ignored and tag_doc["data_source"] == SOURCE)
    limit = s["serial"]["line_max_bytes"]
    lines = protocol.frame_lines([config.BANNER, "X" * cols][:rows]) + [protocol.glyph_line(7, [31] * 8), protocol.clear_line(), protocol.status_line("amber"), protocol.beep_line(120)]
    rep.check("foundation", f"serial lines end in newline and stay under {limit} bytes", all(x.endswith(b"\n") and len(x) <= limit for x in lines), f"longest {max(len(x) for x in lines)}")
    rep.check("foundation", "LCD text wider than the screen is refused", raises(protocol.text_line, 0, "X" * (cols + 1)) and raises(protocol.text_line, rows, "X"))
    rep.check("foundation", "custom characters travel as bytes 128-135", protocol.text_line(0, protocol.glyph_char(0) + protocol.glyph_char(7))[2:4] == bytes([128, 135]) and raises(protocol.glyph_char, 8))
    parsed = [protocol.parse_device_line(x) for x in (b"READY 16 2\n", b"TSIM-TAG-ABC\n", b"K3\n", b"Vhumidity=45.5\n", b"??\n")]
    rep.check("foundation", "device messages parse", [p["type"] for p in parsed] == ["ready", "tag", "button", "value", "unknown"] and parsed[0]["cols"] == 16 and tags.lookup(parsed[1]["uid"]) == "ABC" and parsed[3]["value"] == 45.5)


def check_determinism(rep, root):
    short = {"calibration_days": 2, "scenario_days": 1}
    a = simulate.generate(root / "det_a", seed=5, **short)
    b = simulate.generate(root / "det_b", seed=5, **short)
    c = simulate.generate(root / "det_c", seed=6, **short)
    same = all(Path(a[crew][k]).read_bytes() == Path(b[crew][k]).read_bytes() for crew in a for k in a[crew])
    diff = Path(a["ABC"]["heart_rate_minute"]).read_bytes() != Path(c["ABC"]["heart_rate_minute"]).read_bytes()
    rep.check("determinism", "same seed gives identical files, different seed differs", same and diff)
    people = Path(a["ABC"]["heart_rate_minute"]).read_bytes() != Path(a["DEF"]["heart_rate_minute"]).read_bytes()
    rep.check("determinism", "ABC and DEF are different simulated people", people)
    bad = raises(lambda: simulate.generate(root / "det_d", not_a_setting=1))
    rep.check("determinism", "unknown simulator setting is refused", bad)


def fetch(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
        return json.loads(r.read().decode("utf-8")), r.headers


def check_bridge(rep):
    store = bridge.Store(":memory:")
    b = bridge.Bridge(store, "REAL")
    kinds = [b.handle(x) for x in (b"READY 16 2\n", b"TSIM-TAG-ABC\n", b"Vhr=72\n", b"Vhr=999\n", b"Vfoo=1\n", b"K2\n", b"garbage\n", b"TREALCARD-9\n")]
    rows = store.readings()
    rep.check("bridge", "wearable lines become readings, events and ignored noise", kinds == ["ready", "tag", "value", "value", "value", "button", None, "tag"] and len(rows) == 3 and b.ignored == 1)
    rep.check("bridge", "readings are quality-tagged and carry the logged-in crew", [r["quality"] for r in rows] == ["ok", "out_of_range", "unknown_name"] and all(r["crew"] == "ABC" for r in rows) and rows[0]["unit"] == "BPM")
    rep.check("bridge", "real readings labelled REAL, timestamps UTC with Z", all(r["data_source"] == "REAL" and r["timestamp"].endswith("Z") for r in rows))
    ev = store.events()
    dump = store.dump_text()
    rep.check("bridge", "raw tag IDs are never stored, unknown tag does not log in", "SIM-TAG-ABC" not in dump and "REALCARD-9" not in dump and [e["kind"] for e in ev] == ["ready", "login", "button", "unknown_tag"] and b.active_crew == "ABC")

    server = bridge.make_server(store, b, "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    try:
        health, headers = fetch(port, "/api/health")
        latest, _ = fetch(port, "/api/latest")
        page, _ = fetch(port, "/api/readings?since=1&limit=5")
        named, _ = fetch(port, "/api/readings?name=hr")
        events, _ = fetch(port, "/api/events")
        try:
            fetch(port, "/api/readings?since=abc")
            bad = False
        except urllib.error.HTTPError as e:
            bad = e.code == 400
        rep.check("bridge", "HTTP API answers JSON with CORS for the web app", health["status"] == "ok" and headers["Access-Control-Allow-Origin"] == "*" and headers["Content-Type"] == "application/json")
        rep.check("bridge", "every HTTP answer carries the disclaimer and AI acknowledgement", all("disclaimer" in x for x in (health, latest, page, events)))
        rep.check("bridge", "latest, since, name and events queries work", latest["latest"]["hr"]["value"] == 999 and [r["id"] for r in page["readings"]] == [2, 3] and page["last_id"] == 3 and len(named["readings"]) == 2 and len(events["events"]) == 4)
        rep.check("bridge", "bad query is refused with 400", bad)
    finally:
        server.shutdown()
        server.server_close()

    class FakeLink:
        def __init__(self, chunks):
            self.chunks = list(chunks)

        def recv(self, n):
            return self.chunks.pop(0) if self.chunks else b""

    split_store = bridge.Store(":memory:")
    split = bridge.Bridge(split_store, "REAL")
    try:
        bridge.feed_lines(FakeLink([b"Vhr=6", b"8\r\nVhr=", b"70\r\n\r\nK1\r", b"\nVhr=7"]), split)
        closed = False
    except ConnectionError:
        closed = True
    rep.check("bridge", "Bluetooth reader joins split chunks into lines, skips blanks, reports a closed link", closed and [r["value"] for r in split_store.readings()] == [68.0, 70.0] and [e["kind"] for e in split_store.events()] == ["button"])

    sim_store = bridge.Store(":memory:")
    sim = bridge.Bridge(sim_store, "SIMULATED")
    bridge.simulate(sim, count=20, interval_s=0)
    sr = sim_store.readings()
    lo, hi = config.section("live")["values"]["hr"]["range"]
    rep.check("bridge", "simulate mode feeds 20 plausible readings all labelled SIMULATED", len(sr) == 20 and all(r["data_source"] == "SIMULATED" and r["quality"] == "ok" and lo <= r["value"] <= hi for r in sr) and sim.active_crew == config.section("live")["simulate"]["crew"])


def run_scenario(rep, root, scenario, seed, overrides, limits):
    print(f"\n== {scenario} (seed {seed}) ==")
    d = root / scenario
    simulate.generate(d, seed=seed, **overrides)
    for crew_id in config.crew_ids():
        tag = f"{scenario}/{crew_id}"
        print(f" -- {tag}")
        check_simulator(rep, d / crew_id, tag, crew_id)
        r = pipeline.run(d / crew_id, d / crew_id / "out")
        check_processing(rep, r, tag, limits, crew_id)
        check_summary(rep, r, tag)


def main():
    p = argparse.ArgumentParser(description="Check simulator and processing logic on SIMULATED data.")
    p.add_argument("--seeds", type=int, nargs="+", default=[42, 7, 123])
    p.add_argument("--stress-seeds", type=int, nargs="+", default=[99, 2026])
    p.add_argument("--keep", action="store_true")
    a = p.parse_args()
    root = Path(tempfile.mkdtemp(prefix="healthsim_checks_"))
    rep = Report()
    try:
        for seed in a.seeds:
            run_scenario(rep, root, f"normal_seed{seed}", seed, {}, NORMAL_LIMITS)
        for seed in a.stress_seeds:
            run_scenario(rep, root, f"stress_seed{seed}", seed, STRESS, STRESS_LIMITS)
        print("\n== foundation ==")
        check_foundation(rep)
        print("\n== rules and determinism ==")
        check_rules(rep)
        check_determinism(rep, root)
        print("\n== bridge ==")
        check_bridge(rep)
    finally:
        if a.keep:
            print(f"\nkept generated data in {root}")
        else:
            shutil.rmtree(root, ignore_errors=True)
    total = len(rep.rows)
    failed = rep.failed
    print(f"\n{total - len(failed)}/{total} checks passed. Data is SIMULATED; this validates logic only, not accuracy.")
    if failed:
        print("FAILED:")
        for scenario, name, _, detail in failed:
            print(f"  {scenario}: {name} ({detail})")
        print("RESULT: FAIL")
        sys.exit(1)
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
