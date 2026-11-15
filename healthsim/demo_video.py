import argparse
import math
import textwrap
from pathlib import Path

from PIL import Image

from . import config, protocol
from .diagrams import Canvas, color
from .loaders import load

OUT_NAME = "slide4_demo.gif"
FPS = 10
OUT_SIZE = (1280, 720)
SCENES = [("title", 0.0, 3.0), ("abc_check", 3.0, 13.0), ("abc_web", 13.0, 21.0), ("def_run", 21.0, 30.5), ("def_web", 30.5, 40.5), ("end", 40.5, 44.5)]
EXAMPLE_SCOREBOARD = (("ABC", 14000), ("DEF", 12490))


def demo_numbers(data_root=None):
    cal = config.section("simulation")["calibration_days"]
    out = {}
    for crew in config.crew_ids():
        d = Path(data_root) / crew if data_root else config.data_dir(crew)
        hr = load(d, "heart_rate_minute")
        act = load(d, "activity_minute")
        skin = load(d, "skin_temp_minute")
        nights = load(d, "sleep_nights_truth")
        state = act["true_state"].to_numpy()
        h = hr.assign(date=hr["timestamp"].dt.date)
        rest = h[state == "sedentary"].groupby("date")["sensor_bpm"].median()
        ex = h[state == "exercise"].groupby("date")["sensor_bpm"].median()
        st = skin.assign(date=skin["timestamp"].dt.date).groupby("date")["skin_surface_temp_c"].mean()
        sleep_h = nights["true_sleep_min"] / 60
        mv = act.assign(date=act["timestamp"].dt.date).groupby("date")["movement_minute"].sum()
        blood = config.crew(crew)["blood_baseline"]
        sc = config.scenario(crew)
        out[crew] = {
            "hr_base": int(round(rest.iloc[:cal].mean())),
            "hr_now": int(round(rest.iloc[-1])),
            "hr_exercise": int(round(ex.iloc[-1])),
            "skin_base": round(float(st.iloc[:cal].mean()), 1),
            "skin_now": round(float(st.iloc[-1]), 1),
            "sleep_base": round(float(sleep_h[nights["night_id"] < cal].mean()), 1),
            "sleep_now": round(float(sleep_h.iloc[-1]), 1),
            "movement_min": int(mv.iloc[-1]),
            "wbc_base": blood["wbc_thousand_per_ul"],
            "wbc_now": round(blood["wbc_thousand_per_ul"] * (1 - sc["wbc_drop_fraction"]) + 1e-9, 1),
            "plt_base": blood["platelets_thousand_per_ul"],
            "plt_now": int(round(blood["platelets_thousand_per_ul"] * (1 - sc["platelet_drop_fraction"]))),
        }
    return out


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def beat(t, bpm):
    return 1.0 + 0.16 * max(0.0, math.sin(2 * math.pi * t * bpm / 60.0)) ** 2


def base(caption):
    c = Canvas(supersample=1)
    c.banner()
    c.text((70, 44), caption, 44, "bold", max_w=1300)
    c.text((70, 1042), "Illustrated demo with simulated data. Not medical advice.", 22, fill=color("muted"))
    return c


def lcd_text(c, lines, box, size=74):
    for line in lines:
        protocol.check_text(line)
    c.rect(box, fill=color("text"), radius=20)
    for i, line in enumerate(lines):
        c.text((box[0] + 36, box[1] + 22 + i * 100), line, size, "mono", fill=color("background"))


def draw_device(c, lines, leds, finger=False, heart_scale=1.0, tap=None, flash=False, t=0.0):
    c.card((860, 190, 1830, 880), fill=color("card"), outline=color("accent"))
    lcd_text(c, lines, (910, 240, 1780, 480))
    for x, name in zip((1010, 1170, 1330), ("red", "amber", "green")):
        lit = name in leds and (not flash or int(t * 4) % 2 == 0)
        c.circle((x, 575), 46, fill=color(name) if lit else color("line"))
    c.circle((1620, 575), 86, outline=color("red"), width=4)
    if finger:
        c.circle((1620, 575), 70, fill=color("card_alt"))
        c.icon_heart(1620, 570, 44 * heart_scale, color("red"))
    c.text((1620, 690), "pulse sensor", 26, fill=color("muted"), anchor="mm")
    c.rect((910, 690, 1290, 830), fill=color("card_alt"), outline=color("accent"), radius=22, width=3)
    c.text((1100, 760), "tag reader", 30, fill=color("muted"), anchor="mm")
    if tap is not None:
        x = 540 + (1000 - 540) * tap
        c.rect((x - 60, 700, x + 60, 790), fill=color("gold"), outline=color("text"), radius=14, width=3)
        c.rect((x - 36, 720, x - 6, 746), fill=color("card"), radius=4)


def draw_person(c, cx, cy, s, run=None, wrist=False):
    ink = color("text")
    teal = color("accent")
    gold = color("gold")

    def seg(a, b, w, col):
        c.line([a, b], col, w)
        c.circle(a, w / 2, fill=col)
        c.circle(b, w / 2, fill=col)

    hip = (cx, cy + 62 * s)
    if run is None:
        feet = ((cx - 30 * s, cy + 215 * s), (cx + 30 * s, cy + 215 * s))
        arm_l = (cx - 78 * s, cy + 50 * s)
        elbow_r, hand_r = (cx + 105 * s, cy + 8 * s), (cx + 150 * s, cy - 35 * s)
    else:
        ph = run
        feet = []
        for sign in (1, -1):
            feet.append((cx + sign * math.sin(ph) * 80 * s, cy + (215 - 30 * max(0.0, sign * math.cos(ph))) * s))
        arm_l = (cx - math.sin(ph) * 85 * s, cy + 20 * s)
        elbow_r, hand_r = (cx + 60 * s, cy + 5 * s), (cx + math.sin(ph) * 85 * s + 40 * s, cy + 20 * s)
    for f in feet:
        knee = ((hip[0] + f[0]) / 2, (hip[1] + f[1]) / 2)
        seg(hip, knee, 34 * s, ink)
        seg(knee, f, 30 * s, ink)
        c.rect((f[0] - 30 * s, f[1] - 4 * s, f[0] + 34 * s, f[1] + 16 * s), fill=gold, radius=10)
    c.rect((cx - 54 * s, cy - 80 * s, cx + 54 * s, cy + 72 * s), fill=teal, radius=34 * s)
    c.rect((cx - 54 * s, cy - 80 * s, cx + 54 * s, cy - 52 * s), fill=gold, radius=14 * s)
    c.circle((cx, cy - 128 * s), 40 * s, fill=teal)
    c.rect((cx - 24 * s, cy - 142 * s, cx + 34 * s, cy - 112 * s), fill=color("card"), radius=14 * s)
    seg((cx - 54 * s, cy - 52 * s), arm_l, 28 * s, teal)
    seg((cx + 54 * s, cy - 52 * s), elbow_r, 28 * s, teal)
    seg(elbow_r, hand_r, 26 * s, teal)
    if wrist:
        c.rect((hand_r[0] - 26 * s, hand_r[1] - 18 * s, hand_r[0] + 26 * s, hand_r[1] + 18 * s), fill=color("card"), outline=gold, radius=8, width=3)
        c.circle((hand_r[0] - 12 * s, hand_r[1]), 5 * s, fill=color("green"))
        c.line([(hand_r[0] + 26 * s, hand_r[1] - 18 * s), (860, 190)], teal, 3)
        c.line([(hand_r[0] + 26 * s, hand_r[1] + 18 * s), (860, 880)], teal, 3)
    return hand_r


def caption_bar(c, text):
    c.rect((70, 940, 840, 1005), fill=color("accent"), radius=30)
    c.text((105, 972), text, 34, "bold", fill=color("on_accent"), anchor="lm", max_w=700)


def scene_title(u, n):
    c = base("Demo: one check-up, two crew members")
    c.text((960, 420), "Check-up on the wrist,", 90, "bold", anchor="mm")
    c.text((960, 530), "result on the web app", 90, "bold", anchor="mm", fill=color("accent"))
    c.text((960, 680), "ABC has a normal day. DEF is drifting from their own baseline.", 38, anchor="mm", fill=color("muted"))
    c.text((960, 760), "All data in this demo is simulated.", 38, "bold", anchor="mm")
    return c


def scene_abc_check(u, n, t):
    num = n["ABC"]
    c = base("Normal day: crew member ABC")
    bpm = num["hr_now"]
    tap = None
    leds = ()
    finger = False
    if u < 1.5:
        lines, step = ["SIMULATED DATA", "HEALTH MONITOR"], "Switch on"
    elif u < 3.5:
        lines, step = ["> 3/4 ID SCAN", "Tap your tag..."], "1  Tap your tag"
        tap = clamp((u - 1.9) / 1.0)
    elif u < 5.0:
        lines, step, leds = ["ID: ABC", "Welcome back"], "Logged in as ABC", ("amber",)
    elif u < 6.5:
        lines, step, leds, finger = ["PULSE MONITOR", "Place Finger..."], "2  Finger on the sensor", ("amber",), True
    else:
        lines, step, leds, finger = ["PULSE MONITOR", f"BPM: {bpm}"], "3  Normal reading, green light", ("green",), True
    draw_person(c, 270, 560, 1.6, wrist=True)
    draw_device(c, lines, leds, finger, beat(t, bpm), tap, t=t)
    caption_bar(c, step)
    return c


def browser(c, title):
    c.card((90, 150, 1830, 1010), fill=color("card"))
    c.rect((90, 150, 1830, 215), fill=color("card_alt"), radius=28)
    for i, name in enumerate(("red", "amber", "green")):
        c.circle((135 + i * 36, 183), 10, fill=color(name))
    c.rect((300, 160, 1500, 206), fill=color("card"), radius=22)
    c.text((330, 183), title, 24, "mono", fill=color("muted"), anchor="lm")
    c.text((1790, 183), "illustration of the web app", 22, fill=color("muted"), anchor="rm")


def login_card(c, crew, u):
    c.card((560, 330, 1360, 800), fill=color("background"))
    c.text((960, 400), "Crew software", 52, "bold", anchor="mm")
    c.text((960, 480), "Log in with your tag", 34, fill=color("muted"), anchor="mm")
    c.rect((660, 540, 1260, 620), fill=color("card_alt"), outline=color("accent"), radius=40, width=3)
    c.text((960, 580), "Tag detected" if u > 0.6 else "Waiting for tag...", 34, anchor="mm")
    if u > 1.2:
        c.rect((660, 660, 1260, 740), fill=color("accent"), radius=40)
        c.text((960, 700), f"Welcome, {crew}", 38, "bold", fill=color("on_accent"), anchor="mm")


def tile(c, box, title, big, unit, note=None, hot=False):
    c.card(box, fill=color("card_alt") if hot else color("card"), outline=color("accent") if hot else color("line"))
    c.text((box[0] + 28, box[1] + 22), title, 28, "bold", fill=color("muted"))
    c.text((box[0] + 28, box[1] + 80), big, 110 if hot else 64, "bold", fill=color("text"))
    wbig = c.text_width(big, 110 if hot else 64, "bold")
    c.text((box[0] + 28 + wbig + 14, box[1] + (170 if hot else 120)), unit, 34 if hot else 28, fill=color("muted"))
    if note:
        c.text((box[0] + 28, box[3] - 46), note, 26, "bold", fill=color("accent"))


def scoreboard(c, box, earned=True):
    c.card(box, fill=color("accent"), outline=color("accent"))
    sc = config.section("scoring")
    c.text((box[0] + 28, box[1] + 18), "SCORE", 30, "bold", fill=color("gold"))
    if earned:
        c.text((box[0] + 28, box[1] + 62), f"+{sc['checkup_points'] + sc['on_time_bonus']} this check-up", 40, "bold", fill=color("on_accent"))
        c.text((box[0] + 28, box[1] + 116), f"Multiplier x{sc['multiplier_start'] + sc['multiplier_step']:.2f}", 30, fill=color("on_accent_muted"))
    y = box[1] + 176
    c.text((box[0] + 28, y), "SCOREBOARD (example)", 22, "bold", fill=color("on_accent_muted"))
    for i, (name, pts) in enumerate(EXAMPLE_SCOREBOARD):
        c.text((box[0] + 28, y + 36 + i * 52), f"{i + 1}  {name}   {pts}", 38, "bold", fill=color("on_accent"))


def scene_abc_web(u, n, t):
    num = n["ABC"]
    c = base("Same reading on the web app: ABC")
    browser(c, "habitat-hub:8501")
    if u < 2.2:
        login_card(c, "ABC", u)
        return c
    v = u - 2.2
    if v > 0.0:
        tile(c, (130, 250, 760, 560), "HEART RATE", str(num["hr_now"]), "BPM", "Same number as the wrist", hot=True)
        c.icon_heart(660, 380, 42 * beat(t, num["hr_now"]), color("red"))
    if v > 0.5:
        tile(c, (130, 590, 440, 790), "MOVEMENT TODAY", str(num["movement_min"]), "min")
        tile(c, (460, 590, 760, 790), "STATUS", "GREEN", "", None)
        c.circle((690, 640), 18, fill=color("green"))
    if v > 1.0:
        c.card((790, 250, 1260, 790))
        c.text((820, 272), "Compared with your baseline", 30, "bold")
        rows = (
            ("Resting heart rate", f"{num['hr_base']} to {num['hr_now']} BPM"),
            ("Skin surface temp", f"{num['skin_base']} to {num['skin_now']} C"),
            ("Sleep last night", f"{num['sleep_base']} to {num['sleep_now']} h"),
        )
        for i, (label, val) in enumerate(rows):
            y = 350 + i * 130
            c.text((820, y), label, 26, fill=color("muted"))
            c.text((820, y + 38), val, 34, "bold")
            c.rect((1130, y + 14, 1228, y + 56), fill=color("green"), radius=20)
            c.text((1179, y + 35), "OK", 24, "bold", fill=color("card"), anchor="mm")
    if v > 1.8:
        scoreboard(c, (1290, 250, 1800, 790))
    if v > 2.6:
        c.card((130, 820, 1260, 990), fill=color("card_alt"))
        c.text((160, 840), "Cabin", 28, "bold", fill=color("muted"))
        env = config.section("cabin")["baseline"]
        c.text((160, 890), f"{env['temperature_c']:.0f} C     {env['humidity_pct']:.0f} % humidity     {env['pressure_kpa']:.1f} kPa", 38, "bold")
    return c


def scene_def_run(u, n, t):
    num = n["DEF"]
    c = base("Worrying trend: crew member DEF")
    if u < 5.5:
        c.rect((120, 800, 980, 850), fill=color("text"), radius=20)
        for i in range(-1, 15):
            x = 120 + ((i * 60 - (t * 220 if u < 3.5 else 0)) % 900)
            c.rect((x, 810, x + 24, 822), fill=color("muted"), radius=4)
        run = (t * 2 * math.pi * 2.2) if u < 3.5 else None
        draw_person(c, 550, 520, 1.4, run=run)
        if u < 3.5:
            bpm = int(70 + (num["hr_exercise"] - 70) * clamp(u / 3.0))
            note = "Scheduled exercise block"
            caption = "Exercise: heart rate climbs"
        else:
            bpm = int(num["hr_exercise"] - (num["hr_exercise"] - num["hr_now"]) * clamp((u - 3.5) / 2.0))
            note = "Rest 5 minutes"
            caption = "Rest, then measure again"
        tile(c, (1100, 250, 1800, 600), "HEART RATE", str(bpm), "BPM", note, hot=True)
        c.icon_heart(1660, 380, 42 * beat(t, bpm), color("red"))
        caption_bar(c, caption)
        return c
    v = u - 5.5
    if v < 1.5:
        lines, leds, finger = ["PULSE MONITOR", "Place Finger..."], ("amber",), True
        step = "Measure again, after rest"
    elif v < 2.6:
        lines, leds, finger = ["PULSE MONITOR", f"BPM: {num['hr_now']}"], ("amber",), True
        step = "Resting reading, above baseline"
    else:
        lines, leds, finger = ["!! PI5 ALERT !!", "CHECK VITALS!"], ("red",), False
        step = "Hub flags it: check vitals"
    draw_person(c, 270, 560, 1.6, wrist=True)
    draw_device(c, lines, leds, finger, beat(t, num["hr_now"]), None, flash=v >= 2.6, t=t)
    caption_bar(c, step)
    return c


def chip(c, x, y, label, key, w=150):
    c.rect((x, y, x + w, y + 44), fill=color(key), radius=22)
    c.text((x + w / 2, y + 22), label, 24, "bold", fill=color("sim_text" if key == "gold" else "card"), anchor="mm")


def scene_def_web(u, n, t):
    num = n["DEF"]
    alerts = config.section("alerts")
    c = base("Same check-up on the web app: DEF")
    browser(c, "habitat-hub:8501")
    if u < 1.6:
        login_card(c, "DEF", u * 1.4)
        return c
    v = u - 1.6
    c.card((130, 250, 1230, 800))
    c.text((160, 270), "Strayed from your own baseline", 34, "bold")
    for x, label in ((160, "Indicator"), (590, "Baseline"), (790, "Now"), (960, "Change")):
        c.text((x, 328), label, 24, "bold", fill=color("muted"))
    rows = (
        ("Resting heart rate", f"{num['hr_base']} BPM", f"{num['hr_now']} BPM", f"+{num['hr_now'] - num['hr_base']}", "AMBER"),
        ("Skin surface temp", f"{num['skin_base']} C", f"{num['skin_now']} C", f"+{num['skin_now'] - num['skin_base']:.1f}", "AMBER"),
        ("Sleep last night", f"{num['sleep_base']} h", f"{num['sleep_now']} h", f"{num['sleep_now'] - num['sleep_base']:+.1f} h", "AMBER"),
        ("White cells (x1000/uL)", f"{num['wbc_base']}", f"{num['wbc_now']}", "-25%", "AMBER"),
        ("Platelets (x1000/uL)", f"{num['plt_base']}", f"{num['plt_now']}", "-25%", "AMBER"),
    )
    for i, (label, base_v, now_v, ch, status) in enumerate(rows):
        if v < 0.4 + i * 0.9:
            break
        y = 372 + i * 76
        c.line([(160, y - 8), (1200, y - 8)], color("line"), 2)
        c.text((160, y + 8), label, 30, max_w=410)
        c.text((590, y + 8), base_v, 30, fill=color("muted"))
        c.text((790, y + 8), now_v, 30, "bold")
        c.text((960, y + 8), ch, 30, "bold", fill=color("red"))
        chip(c, 1080, y + 4, status, "gold", 120)
    if v > 5.0:
        c.card((1260, 250, 1800, 800), outline=color("red"))
        c.text((1290, 272), "What to do", 34, "bold")
        c.text((1290, 326), "Quick help", 24, "bold", fill=color("muted"))
        y = 360
        for key in ("resting_hr", "sleep"):
            for line in textwrap.wrap(alerts[key]["quick_help"], 34):
                c.text((1290, y), line, 24, max_w=480)
                y += 30
            y += 10
        c.rect((1290, 520, 1770, 660), outline=color("red"), radius=22, width=4)
        c.text((1530, 553), "White cells and platelets", 28, "bold", anchor="mm", max_w=450)
        c.text((1530, 588), "both falling:", 28, "bold", anchor="mm")
        c.text((1530, 626), "contact the flight surgeon", 28, anchor="mm", fill=color("red"), max_w=450)
        c.text((1290, 685), "Exposure indicator only, many", 24, fill=color("muted"))
        c.text((1290, 717), "possible causes. Not a radiation dose.", 24, fill=color("muted"))
    if v > 6.5:
        c.card((130, 830, 1230, 990), fill=color("card_alt"))
        c.text((160, 850), "Sent to Earth", 28, "bold", fill=color("muted"))
        c.text((160, 896), "Summary on the delayed link, mood only if abnormal", 30, max_w=1040)
        c.rect((1260, 830, 1800, 990), fill=color("accent"), radius=28)
        c.text((1290, 846), "SCOREBOARD (example)", 22, "bold", fill=color("on_accent_muted"))
        for i, (name, pts) in enumerate(EXAMPLE_SCOREBOARD):
            c.text((1290, 884 + i * 50), f"{i + 1}  {name}   {pts}", 36, "bold", fill=color("on_accent"))
    return c


def scene_end(u, n):
    c = base("What the demo showed")
    for i, (text, bold) in enumerate(
        (
            ("A quick check-up, a normal reading, the same number on the web app.", False),
            ("A drift from the person's own baseline, flagged with advice.", False),
            ("Points reward taking check-ups, never health values.", True),
            ("All data is simulated. Logic demo only, not medical advice.", True),
        )
    ):
        y = 340 + i * 120
        c.circle((212, y + 22), 7, fill=color("accent"))
        c.text((236, y), text, 40, "bold" if bold else "regular", max_w=1550)
    return c


BUILD = {"title": scene_title, "abc_check": scene_abc_check, "abc_web": scene_abc_web, "def_run": scene_def_run, "def_web": scene_def_web, "end": scene_end}


def frame_at(t, numbers=None):
    n = numbers or demo_numbers()
    for name, a, b in SCENES:
        if a <= t < b:
            fn = BUILD[name]
            return fn(t - a, n) if name in ("title", "end") else fn(t - a, n, t)
    raise ValueError(f"time {t} is outside the demo")


def duration():
    return SCENES[-1][2]


def render(out_dir=None, fps=FPS, size=OUT_SIZE, numbers=None):
    n = numbers or demo_numbers()
    frames = []
    count = int(duration() * fps)
    for i in range(count):
        frames.append(frame_at(i / fps, n).to_image(size))
    sample = Image.new("RGB", (size[0], size[1] * 6))
    for k, i in enumerate(range(0, count, max(1, count // 6))[:6]):
        sample.paste(frames[i], (0, k * size[1]))
    palette = sample.quantize(colors=64, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    paletted = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]
    out = Path(out_dir) if out_dir else config.ROOT / "assets"
    out.mkdir(parents=True, exist_ok=True)
    path = out / OUT_NAME
    paletted[0].save(path, save_all=True, append_images=paletted[1:], duration=int(1000 / fps), loop=0, optimize=True, disposal=1)
    return path, count


def main():
    p = argparse.ArgumentParser(description="Draw the SIMULATED demo animation for the deck.")
    p.add_argument("--out", default=None)
    a = p.parse_args()
    path, count = render(a.out)
    print(f"{path}  {count} frames, {duration():.1f} s, {path.stat().st_size / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
