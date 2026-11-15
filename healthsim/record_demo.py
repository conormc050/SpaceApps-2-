import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import tomllib
import urllib.request
from pathlib import Path

from . import config
from .demo_video import EXAMPLE_MISSIONS, demo_numbers

PORT = 8611
OUT_NAME = "slide4_demo_screencast.mp4"
LEADERBOARD_NAMES = {"ABC": "slide4_leaderboard_north.png", "DEF": "slide4_leaderboard_south.png"}
HEADER = "user_id,date,active_minutes,exercise_minutes,posture_change,back_hip_aches,mental_health_score,last_checkin\n"

OVERLAY = """
(() => {
  const BANNER = %BANNER%;
  function setup() {
    if (document.getElementById('demo-banner')) return;
    const style = document.createElement('style');
    style.textContent = `
      #demo-banner{position:fixed;right:24px;bottom:24px;z-index:2147483647;background:#DCA137;color:#141517;pointer-events:none;
        font:700 22px 'Source Sans Pro',Segoe UI,sans-serif;padding:10px 26px;border-radius:30px;letter-spacing:.5px}
      #demo-caption{position:fixed;left:50%;top:14px;transform:translateX(-50%);z-index:2147483647;max-width:62%;background:rgba(15,23,42,.94);
        color:#F2F6FC;border:2px solid #4ADE80;font:600 30px 'Source Sans Pro',Segoe UI,sans-serif;padding:12px 26px;
        border-radius:16px;opacity:0;transition:opacity .4s;pointer-events:none;text-align:center}
      #demo-cursor{position:fixed;left:0;top:0;width:26px;height:26px;margin:-13px 0 0 -13px;z-index:2147483647;
        border-radius:50%;background:rgba(255,255,255,.85);border:3px solid #141517;pointer-events:none;
        box-shadow:0 0 0 2px rgba(255,255,255,.7)}
      .demo-ripple{position:fixed;z-index:2147483646;width:20px;height:20px;margin:-10px 0 0 -10px;border-radius:50%;
        border:4px solid #4ADE80;pointer-events:none;animation:demo-rip .6s ease-out forwards}
      @keyframes demo-rip{to{transform:scale(4);opacity:0}}`;
    document.head.appendChild(style);
    const banner = document.createElement('div'); banner.id = 'demo-banner'; banner.textContent = BANNER;
    const cap = document.createElement('div'); cap.id = 'demo-caption';
    const cur = document.createElement('div'); cur.id = 'demo-cursor';
    document.body.append(banner, cap, cur);
    document.addEventListener('mousemove', e => { cur.style.left = e.clientX + 'px'; cur.style.top = e.clientY + 'px'; }, true);
    document.addEventListener('mousedown', e => {
      const r = document.createElement('div'); r.className = 'demo-ripple';
      r.style.left = e.clientX + 'px'; r.style.top = e.clientY + 'px'; document.body.appendChild(r);
      setTimeout(() => r.remove(), 700);
    }, true);
  }
  window.__setCaption = t => {
    const c = document.getElementById('demo-caption'); if (!c) return;
    if (!t) { c.style.opacity = 0; return; }
    c.textContent = t; c.style.opacity = 1;
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', setup); else setup();
})();
"""


def export_state(worktree, numbers):
    alerts = config.section("alerts")
    sc = config.section("scoring")
    state = {
        "banner": config.BANNER,
        "crews": numbers,
        "rules": {
            "hr": alerts["resting_hr"]["min_change"],
            "skin": alerts["skin_temp"]["min_change"],
            "sleep": alerts["sleep"]["min_change"],
            "blood": alerts["blood_counts"]["min_drop_fraction"],
        },
        "quick_help": {"resting_hr": alerts["resting_hr"]["quick_help"], "sleep": alerts["sleep"]["quick_help"]},
        "cabin": config.section("cabin")["baseline"],
        "score": {"points": sc["checkup_points"] + sc["on_time_bonus"], "multiplier": sc["multiplier_start"] + sc["multiplier_step"]},
        "missions": [{"name": m["name"], "crew": [{"Crew": c, "Points": p} for c, p in m["crew"]]} for m in EXAMPLE_MISSIONS],
    }
    path = Path(worktree) / "data" / "demo" / "demo_state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    pages = Path(worktree) / "healthsim" / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    shutil.copy(Path(__file__).with_name("vitals_page.py"), pages / "1_Live_Vitals.py")
    summary = Path(worktree) / "data" / "ABC" / "Activity_Summary.csv"
    summary.parent.mkdir(parents=True, exist_ok=True)
    summary.write_text(HEADER, encoding="utf-8")
    return state


def theme_flags(worktree):
    cfg = tomllib.loads((Path(worktree) / "healthsim" / ".streamlit" / "config.toml").read_text(encoding="utf-8"))["theme"]
    flags = []
    for key, value in cfg.items():
        flags += [f"--theme.{key}", str(value)]
    return flags


def start_app(worktree):
    try:
        urllib.request.urlopen(f"http://localhost:{PORT}/_stcore/health", timeout=2)
        raise RuntimeError(f"port {PORT} is already in use by another app; stop it or change PORT")
    except OSError:
        pass
    cmd = [
        sys.executable, "-m", "streamlit", "run", "healthsim/app.py", "--server.port", str(PORT), "--server.headless", "true",
        "--browser.gatherUsageStats", "false", "--server.fileWatcherType", "none",
    ] + theme_flags(worktree)
    proc = subprocess.Popen(cmd, cwd=worktree, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://localhost:{PORT}/_stcore/health", timeout=2)
            return proc
        except OSError:
            time.sleep(1)
    proc.kill()
    raise RuntimeError("the Streamlit app did not start")


class Driver:
    def __init__(self, page, speed):
        self.page = page
        self.speed = speed
        self.pos = (960.0, 540.0)

    def pause(self, seconds):
        self.page.wait_for_timeout(int(seconds * 1000 * self.speed))

    def say(self, text):
        self.page.evaluate("t => window.__setCaption && window.__setCaption(t)", text)

    def glide(self, locator, steps=26):
        locator.scroll_into_view_if_needed()
        box = locator.bounding_box()
        tx, ty = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        sx, sy = self.pos
        for i in range(1, steps + 1):
            f = i / steps
            f = f * f * (3 - 2 * f)
            self.page.mouse.move(sx + (tx - sx) * f, sy + (ty - sy) * f)
            self.page.wait_for_timeout(max(1, int(14 * self.speed)))
        self.pos = (tx, ty)

    def focus_slider(self, locator, value, low=1):
        self.glide(locator)
        locator.focus()
        self.page.keyboard.press("Home")
        self.pause(0.6)
        for _ in range(value - low):
            self.page.keyboard.press("ArrowRight")
            self.pause(0.45)

    def click(self, locator):
        self.glide(locator)
        self.pause(0.25)
        self.page.mouse.down()
        self.page.mouse.up()

    def type(self, locator, text, delay=130):
        self.click(locator)
        self.page.keyboard.press("Control+A")
        self.page.keyboard.type(text, delay=delay * self.speed)
        self.page.keyboard.press("Enter")

    def scroll_to(self, locator, hold):
        locator.scroll_into_view_if_needed()
        self.glide(locator, steps=18)
        self.pause(hold)

    def nav(self, name):
        self.click(self.page.get_by_role("link", name=name).first)
        self.pause(2.5)


def checkin(d, crew, active, exercise, posture, aches, mood):
    page = d.page
    d.type(page.get_by_label("User ID (e.g., user_123)"), crew)
    d.type(page.get_by_label("Active Minutes today"), str(active))
    d.type(page.get_by_label("Exercise Minutes today"), str(exercise))
    if posture == "Yes":
        d.click(page.get_by_text("Yes", exact=True).first)
        d.pause(0.8)
        d.click(page.get_by_text(aches, exact=True).nth(1))
    d.focus_slider(page.get_by_role("slider").first, mood)
    d.pause(0.8)
    d.click(page.get_by_role("button", name="Submit Questionnaire"))
    d.pause(1.5)
    saved = page.get_by_text(re.compile("saved successfully")).first
    saved.scroll_into_view_if_needed()
    d.pause(3.0)


def run_script(d, n):
    page = d.page
    abc, dfn = n["ABC"], n["DEF"]
    page.goto(f"http://localhost:{PORT}")
    page.wait_for_selector("text=Health Activity & Telemetry Hub", timeout=30000)
    page.mouse.move(960, 500)
    d.say("Crew software on the habitat network")
    d.pause(7)

    d.say("ABC taps their tag on the wearable and logs in")
    d.nav("Live Vitals")
    d.click(page.get_by_role("button", name="Log in with tag"))
    d.pause(3)
    d.say(f"Check-up done: the same {abc['hr_now']} BPM shown on the wrist")
    d.scroll_to(page.get_by_text("Same number as the wrist display"), 9)
    d.say("Compared with ABC's own baseline: all green")
    d.scroll_to(page.get_by_text("Compared with your own baseline"), 10)
    d.scroll_to(page.get_by_text("No action needed"), 6)
    d.say("Cabin conditions, then the score for this check-up")
    d.scroll_to(page.get_by_text("Cabin environment"), 6)
    d.scroll_to(page.get_by_text("Points reward taking check-ups"), 10)

    d.say("ABC also answers the daily check-in")
    d.nav("app")
    checkin(d, "ABC", abc["movement_min"], 120, "No", "No", 4)
    d.say("The check-in is saved to the summary")
    d.click(page.get_by_role("button", name=re.compile("Refresh Data")))
    d.scroll_to(page.get_by_text("Live Activity & Summary"), 9)

    d.say("DEF logs in after the scheduled run and a rest")
    d.nav("Live Vitals")
    d.click(page.get_by_text("DEF", exact=True).first)
    d.pause(0.8)
    d.click(page.get_by_role("button", name="Log in with tag"))
    d.pause(3)
    d.say(f"{dfn['hr_now']} BPM at rest: above DEF's own baseline of {dfn['hr_base']}")
    d.scroll_to(page.get_by_text("Same number as the wrist display"), 9)
    d.say("Other indicators have drifted from baseline too: amber")
    d.scroll_to(page.get_by_text("Compared with your own baseline"), 12)
    d.say("Quick help, and when to contact the flight surgeon")
    d.scroll_to(page.get_by_text("What to do"), 14)
    d.scroll_to(page.get_by_text("Summary queued for Earth"), 6)
    d.say("Score for this check-up. Points never depend on health values")
    d.scroll_to(page.get_by_text("Points reward taking check-ups"), 10)

    d.say("DEF answers the daily check-in")
    d.nav("app")
    checkin(d, "DEF", dfn["movement_min"], 120, "No", "No", 3)
    d.say("Both check-ins are saved and shown in the summary")
    d.click(page.get_by_role("button", name=re.compile("Refresh Data")))
    d.scroll_to(page.get_by_text("Live Activity & Summary"), 10)
    d.say("All data is simulated. Not medical advice.")
    d.pause(5)


def to_mp4(webm, mp4):
    import imageio_ffmpeg

    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-i", str(webm), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "24", "-r", "30", "-movflags", "+faststart", str(mp4)], check=True, capture_output=True)


def record(worktree, out_dir, speed=1.0, keep_webm=False):
    from playwright.sync_api import sync_playwright

    n = demo_numbers()
    export_state(worktree, n)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    raw = out / "raw_video"
    shutil.rmtree(raw, ignore_errors=True)
    app = start_app(worktree)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 1920, "height": 1080}, record_video_dir=str(raw), record_video_size={"width": 1920, "height": 1080})
            context.add_init_script(OVERLAY.replace("%BANNER%", json.dumps(config.BANNER)))
            page = context.new_page()
            page.set_default_timeout(20000)
            try:
                run_script(Driver(page, speed), n)
            except Exception:
                page.screenshot(path=str(out / "error.png"))
                raise
            context.close()
            webm = Path(page.video.path())
            browser.close()
    finally:
        app.terminate()
    mp4 = out / OUT_NAME
    to_mp4(webm, mp4)
    if not keep_webm:
        shutil.rmtree(raw, ignore_errors=True)
    return mp4


def screenshot_leaderboard(worktree, out_dir):
    from playwright.sync_api import sync_playwright

    n = demo_numbers()
    export_state(worktree, n)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    app = start_app(worktree)
    paths = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 1920, "height": 1080})
            context.add_init_script(OVERLAY.replace("%BANNER%", json.dumps(config.BANNER)))
            page = context.new_page()
            page.set_default_timeout(20000)
            page.goto(f"http://localhost:{PORT}")
            page.wait_for_selector("text=Health Activity & Telemetry Hub")
            page.get_by_role("link", name="Live Vitals").first.click()
            for crew_id, name in LEADERBOARD_NAMES.items():
                page.get_by_text(crew_id, exact=True).first.click()
                page.get_by_role("button", name="Log in with tag").click()
                page.wait_for_selector(f"text=Welcome, {crew_id}")
                page.get_by_text("Points reward taking check-ups").scroll_into_view_if_needed()
                page.mouse.move(40, 1040)
                page.wait_for_timeout(2000)
                top = page.get_by_role("heading", name="Score", exact=True).bounding_box()["y"] - 30
                path = out / name
                page.screenshot(path=str(path), clip={"x": 300, "y": max(0, top), "width": 1620, "height": 1080 - max(0, top)})
                paths.append(path)
            browser.close()
    finally:
        app.terminate()
    return paths


def main():
    p = argparse.ArgumentParser(description="Record a SIMULATED screencast of the team's Streamlit app.")
    p.add_argument("--leaderboard", action="store_true", help="only take the leaderboard screenshot")
    p.add_argument("--worktree", required=True, help="folder holding the team's app (its own checkout of the web app branch)")
    p.add_argument("--out", default=str(config.ROOT / "assets"))
    p.add_argument("--speed", type=float, default=0.85, help="scales every pause: 1.0 is the slowest pacing, 0.2 is a fast dry run")
    a = p.parse_args()
    if a.leaderboard:
        for path in screenshot_leaderboard(a.worktree, a.out):
            print(path)
        return
    mp4 = record(a.worktree, a.out, a.speed)
    print(f"{mp4}  {mp4.stat().st_size / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
