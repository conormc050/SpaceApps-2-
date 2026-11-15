import argparse
import math
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import config

ASSETS = config.ROOT / "assets"
FILES = {"system_flow": "slide3_system_flow.png", "two_checks": "slide3_two_checks.png"}


def brand():
    return config.section("brand")


def color(name):
    return brand()["palette"][name]


@lru_cache(maxsize=None)
def load_font(kind, size):
    for path in brand()["fonts"][kind]:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


class Canvas:
    def __init__(self, supersample=None):
        pic = brand()["picture"]
        self.w, self.h, self.s = pic["width"], pic["height"], supersample or pic["supersample"]
        self.img = Image.new("RGB", (self.w * self.s, self.h * self.s), color("background"))
        self.d = ImageDraw.Draw(self.img)
        self.texts = []

    def px(self, v):
        return int(round(v * self.s))

    def pts(self, points):
        return [(self.px(x), self.px(y)) for x, y in points]

    def rect(self, box, fill=None, outline=None, radius=24, width=2):
        self.d.rounded_rectangle([self.px(v) for v in box], radius=self.px(radius), fill=fill, outline=outline, width=self.px(width))

    def circle(self, c, r, fill=None, outline=None, width=2):
        x, y = c
        self.d.ellipse([self.px(x - r), self.px(y - r), self.px(x + r), self.px(y + r)], fill=fill, outline=outline, width=self.px(width))

    def poly(self, points, fill):
        self.d.polygon(self.pts(points), fill=fill)

    def line(self, points, fill, width=4):
        self.d.line(self.pts(points), fill=fill, width=self.px(width), joint="curve")

    def text_width(self, s, size, kind="regular"):
        return load_font(kind, self.px(size)).getlength(s) / self.s

    def text(self, xy, s, size, kind="regular", fill=None, anchor="la", max_w=None):
        if max_w is not None and self.text_width(s, size, kind) > max_w:
            raise ValueError(f"text too wide ({self.text_width(s, size, kind):.0f} > {max_w}): {s}")
        self.d.text((self.px(xy[0]), self.px(xy[1])), s, font=load_font(kind, self.px(size)), fill=fill or color("text"), anchor=anchor)
        self.texts.append(s)

    def card(self, box, fill=None, outline=None):
        self.rect(box, fill=fill or color("card"), outline=outline or color("line"), radius=28, width=2)

    def arrow(self, p1, p2, fill=None, width=7, head=26):
        fill = fill or color("accent")
        ang = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
        end = (p2[0] - head * 0.6 * math.cos(ang), p2[1] - head * 0.6 * math.sin(ang))
        self.line([p1, end], fill, width)
        left = (p2[0] - head * math.cos(ang - 0.45), p2[1] - head * math.sin(ang - 0.45))
        right = (p2[0] - head * math.cos(ang + 0.45), p2[1] - head * math.sin(ang + 0.45))
        self.poly([p2, left, right], fill)

    def chip(self, x, y, label, kind):
        pad = 14
        w = self.text_width(label, 20, "bold") + 2 * pad
        key = "real" if kind == "real" else "sim"
        self.rect((x, y, x + w, y + 32), fill=color(key), radius=16)
        self.text((x + w / 2, y + 16), label, 20, "bold", fill=color(key + "_text"), anchor="mm")
        return w

    def banner(self):
        label = config.BANNER
        w = self.text_width(label, 28, "bold") + 56
        x1 = self.w - 70
        self.rect((x1 - w, 46, x1, 100), fill=color("sim"), radius=27)
        self.text((x1 - w / 2, 73), label, 28, "bold", fill=color("sim_text"), anchor="mm")

    def header(self, title, subtitle):
        self.text((70, 40), title, 60, "bold", max_w=1300)
        self.text((70, 116), subtitle, 28, "regular", fill=color("muted"), max_w=1500)
        self.banner()

    def footer(self):
        x = 70
        x += self.chip(x, 1026, "REAL", "real") + 10
        self.text((x, 1028), "measured on our kit", 22, fill=color("muted"))
        x += self.text_width("measured on our kit", 22) + 40
        x += self.chip(x, 1026, "SIM", "sim") + 10
        self.text((x, 1028), "simulated", 22, fill=color("muted"))
        self.text((self.w - 70, 1042), "Demo values, not clinical limits. Not medical advice.", 22, fill=color("muted"), anchor="rm")

    def dot_bullet(self, x, y, s, size=28, max_w=None):
        self.circle((x, y + size * 0.55), 6, fill=color("accent"))
        self.text((x + 24, y), s, size, max_w=max_w)

    def icon_heart(self, cx, cy, r, fill):
        self.circle((cx - r * 0.5, cy - r * 0.3), r * 0.56, fill)
        self.circle((cx + r * 0.5, cy - r * 0.3), r * 0.56, fill)
        self.poly([(cx - r * 1.04, cy - r * 0.08), (cx + r * 1.04, cy - r * 0.08), (cx, cy + r * 1.0)], fill)

    def icon_wearable(self, cx, cy, r):
        self.rect((cx - r * 0.75, cy - r, cx + r * 0.75, cy + r), fill=color("card_alt"), outline=color("accent"), radius=r * 0.28, width=3)
        self.rect((cx - r * 0.5, cy - r * 0.6, cx + r * 0.5, cy - r * 0.05), fill=color("text"), radius=r * 0.1)
        for i, name in enumerate(("red", "amber", "green")):
            self.circle((cx + (i - 1) * r * 0.36, cy + r * 0.5), r * 0.11, fill=color(name))

    def icon_patch(self, cx, cy, r):
        self.rect((cx - r, cy - r, cx + r, cy + r), fill=color("card_alt"), outline=color("red"), radius=r * 0.3, width=3)
        for i in range(3):
            for j in range(3):
                self.circle((cx + (i - 1) * r * 0.5, cy + (j - 1) * r * 0.5), r * 0.1, fill=color("red"))

    def icon_hub(self, cx, cy, r):
        self.rect((cx - r, cy - r * 0.7, cx + r, cy + r * 0.7), fill=color("card_alt"), outline=color("accent"), radius=r * 0.2, width=3)
        for i in range(4):
            x = cx - r * 0.65 + i * r * 0.43
            self.rect((x, cy + r * 0.05, x + r * 0.28, cy + r * 0.45), fill=color("accent"), radius=3)
        self.circle((cx - r * 0.65, cy - r * 0.35), r * 0.09, fill=color("green"))

    def icon_monitor(self, cx, cy, r):
        self.rect((cx - r, cy - r * 0.75, cx + r, cy + r * 0.45), fill=color("card_alt"), outline=color("accent"), radius=r * 0.15, width=3)
        self.line([(cx - r * 0.7, cy + r * 0.2), (cx - r * 0.3, cy - r * 0.1), (cx, cy + r * 0.1), (cx + r * 0.35, cy - r * 0.35), (cx + r * 0.7, cy - r * 0.05)], color("green"), 4)
        self.line([(cx, cy + r * 0.45), (cx, cy + r * 0.8)], color("accent"), 4)
        self.line([(cx - r * 0.4, cy + r * 0.8), (cx + r * 0.4, cy + r * 0.8)], color("accent"), 5)

    def icon_earth(self, cx, cy, r):
        self.circle((cx, cy), r, fill=color("card_alt"), outline=color("accent"), width=3)
        self.d.ellipse([self.px(cx - r * 0.45), self.px(cy - r), self.px(cx + r * 0.45), self.px(cy + r)], outline=color("accent"), width=self.px(2))
        self.line([(cx - r, cy), (cx + r, cy)], color("accent"), 2)
        self.line([(cx - r * 0.85, cy - r * 0.5), (cx + r * 0.85, cy - r * 0.5)], color("accent"), 2)
        self.line([(cx - r * 0.85, cy + r * 0.5), (cx + r * 0.85, cy + r * 0.5)], color("accent"), 2)

    def traffic_dots(self, x, y, r=11, gap=30):
        for i, name in enumerate(("red", "amber", "green")):
            self.circle((x + i * gap, y), r, fill=color(name))

    def to_image(self, size=None):
        return self.img.resize(size or (self.w, self.h), Image.LANCZOS)

    def save(self, path):
        out = self.img.resize((self.w, self.h), Image.LANCZOS)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        out.save(path, optimize=True)


def link_text():
    p = config.section("link")["profiles"]
    iss, mars = p["iss"], p["mars"]
    return f"Delayed link: ISS {iss['one_way_delay_s_min']}-{iss['one_way_delay_s_max']} s, Mars {mars['one_way_delay_s_min'] // 60}-{mars['one_way_delay_s_max'] // 60} min"


def system_flow():
    c = Canvas()
    c.header("How it works on the ISS", "Check-ups on the wrist, decisions in the habitat, summaries to Earth")
    for x, label in ((70, "CREW"), (680, "HABITAT"), (1320, "SOFTWARE AND EARTH")):
        c.text((x, 172), label, 24, "bold", fill=color("muted"))

    c.card((70, 205, 540, 545))
    c.icon_wearable(135, 275, 40)
    c.text((200, 238), "Quick check-up", 34, "bold", max_w=250)
    c.text((200, 286), "wearable, LCD and light", 24, fill=color("muted"), max_w=250)
    c.traffic_dots(485, 253, 10, 26)
    for i, (label, kind) in enumerate((("Pulse", "real"), ("Blood pressure", "sim"), ("Movement", "real"), ("Tag login", "real"))):
        y = 352 + i * 46
        c.dot_bullet(100, y, label, 28, max_w=260)
        c.chip(390, y + 2, kind.upper(), kind)

    c.card((70, 585, 540, 860))
    c.icon_patch(135, 660, 36)
    c.text((200, 625), "Microneedle patch", 34, "bold", max_w=320)
    c.text((200, 673), "blood panel every 2 days", 24, fill=color("muted"), max_w=320)
    c.dot_bullet(100, 724, "White cells, platelets,", 28, max_w=400)
    c.dot_bullet(100, 764, "red cells", 28, max_w=400)
    c.chip(100, 806, "SIM", "sim")
    c.text((170, 808), "planned sensor", 24, fill=color("muted"))

    c.card((680, 205, 1180, 690), fill=color("card_alt"), outline=color("accent"))
    c.icon_hub(755, 285, 46)
    c.text((830, 248), "Habitat hub", 38, "bold", max_w=320)
    c.text((830, 300), "Raspberry Pi 5", 24, fill=color("muted"), max_w=320)
    for i, line in enumerate(("Stores every reading", "Compares you to your baseline", "Green, amber or red + advice", "Keeps score and scoreboard")):
        c.dot_bullet(710, 400 + i * 66, line, 28, max_w=440)

    c.card((680, 730, 1180, 990))
    c.text((710, 748), "Cabin environment", 32, "bold", max_w=440)
    env = (("Temperature", "real"), ("Humidity", "real"), ("Pressure", "real"), ("Air quality", "sim"), ("Noise", "sim"), ("Light", "sim"))
    for i, (label, kind) in enumerate(env):
        col, row = divmod(i, 3)
        x = 710 + col * 235
        y = 812 + row * 56
        c.text((x, y), label, 24, max_w=140)
        c.chip(x + 145, y, kind.upper(), kind)

    c.card((1320, 205, 1850, 545))
    c.icon_monitor(1390, 280, 42)
    c.text((1455, 238), "Crew software", 34, "bold", max_w=370)
    c.text((1455, 286), "on the ISS network", 24, fill=color("muted"), max_w=370)
    for i, line in enumerate(("Check-up and mood form", "Score and scoreboard", "Status and advice")):
        c.dot_bullet(1350, 360 + i * 52, line, 28, max_w=470)

    c.card((1320, 585, 1850, 990))
    c.icon_earth(1390, 660, 38)
    c.text((1455, 624), "Earth", 34, "bold", max_w=370)
    c.text((1455, 672), "flight surgeon dashboard", 24, fill=color("muted"), max_w=370)
    for i, line in enumerate(("Status per astronaut", "Amber and red flags", "Mood only if abnormal")):
        c.dot_bullet(1350, 740 + i * 52, line, 28, max_w=470)
    c.line([(1350, 896), (1820, 896)], color("line"), 2)
    c.text((1350, 908), link_text(), 24, fill=color("accent"), max_w=470)
    c.text((1350, 942), "sent in batches, store and forward", 22, fill=color("muted"), max_w=470)

    for p1, p2, label, lx in (
        ((540, 375), (680, 375), "Bluetooth", 610),
        ((540, 640), (680, 640), "blood panel", 610),
        ((1180, 375), (1320, 375), "network", 1250),
        ((1180, 640), (1320, 640), "Earth link", 1250),
    ):
        c.arrow(p1, p2)
        c.text((lx, p1[1] - 40), label, 20, fill=color("muted"), anchor="mm", max_w=135)
    c.arrow((930, 730), (930, 692))
    c.footer()
    return c


def two_checks():
    sc = config.section("scoring")
    sched = config.section("schedule")
    c = Canvas()
    c.header("Two ways we check in", f"A quick check-up twice a day, a blood panel every {sched['blood_panel_every_days']} days")

    c.card((70, 190, 940, 755))
    c.icon_wearable(140, 265, 42)
    c.text((210, 224), "Quick check-up", 42, "bold", max_w=500)
    c.text((210, 282), "wearable, twice a day", 26, fill=color("muted"), max_w=500)
    for i, (label, kind) in enumerate((("Pulse (BPM)", "real"), ("Blood pressure", "sim"), ("Movement", "real"), ("Tag login", "real"))):
        y = 345 + i * 56
        c.dot_bullet(105, y, label, 30, max_w=380)
        c.chip(520, y + 3, kind.upper(), kind)
    c.line([(105, 590), (905, 590)], color("line"), 2)
    c.text((105, 606), "Traffic light on the wrist", 28, "bold", max_w=700)
    for x, name, label in ((125, "green", "Normal"), (385, "amber", "Check again"), (650, "red", "Contact surgeon")):
        c.circle((x, 695), 30, fill=color(name))
        c.text((x + 46, 695), label, 26, anchor="lm", max_w=230)

    c.card((980, 190, 1850, 755))
    c.icon_patch(1050, 265, 40)
    c.text((1120, 224), "Blood panel", 42, "bold", max_w=600)
    c.text((1120, 282), "microneedle patch, planned sensor", 26, fill=color("muted"), max_w=700)
    for i, label in enumerate(("White cells", "Platelets", "Red cells")):
        y = 345 + i * 56
        c.dot_bullet(1015, y, label, 30, max_w=380)
        c.chip(1330, y + 3, "SIM", "sim")
    c.line([(1015, 520), (1815, 520)], color("line"), 2)
    c.text((1015, 536), "Trend against your own baseline", 28, "bold", max_w=780)
    c.rect((1015, 590, 1815, 690), outline=color("red"), radius=22, width=3)
    c.text((1415, 618), "White cells and platelets both falling", 28, "bold", anchor="mm", max_w=760)
    c.text((1415, 660), "contact the flight surgeon straight away", 28, anchor="mm", fill=color("red"), max_w=760)
    c.text((1015, 715), "Exposure indicator only, many possible causes. Not a radiation dose.", 24, fill=color("muted"), max_w=800)

    c.rect((70, 780, 1850, 1008), fill=color("accent"), radius=28)
    c.text((105, 796), "SCORE", 36, "bold", fill=color("gold"))
    x = 105
    for label in (f"+{sc['checkup_points']} check-up", f"+{sc['sleep_scan_points']} sleep scan", f"+{sc['on_time_bonus']} on time"):
        w = c.text_width(label, 28, "bold") + 44
        c.rect((x, 850, x + w, 900), outline=color("gold"), radius=25, width=3)
        c.text((x + w / 2, 875), label, 28, "bold", fill=color("on_accent"), anchor="mm")
        x += w + 18
    mult = f"Multiplier x{sc['multiplier_start']:.1f} to x{sc['multiplier_cap']:.1f}, +{sc['multiplier_step']:.2f} for each on-time check-up in a row"
    c.text((105, 914), mult, 24, fill=color("on_accent_muted"), max_w=1200)
    c.text((105, 954), "Points reward taking check-ups, never health values.", 28, "bold", fill=color("on_accent"), max_w=1200)
    c.line([(1400, 805), (1400, 985)], color("gold"), 2)
    c.text((1435, 800), "SCOREBOARD (example)", 22, "bold", fill=color("on_accent_muted"))
    c.text((1435, 840), "ABC   14000", 38, "bold", fill=color("on_accent"), max_w=380)
    c.text((1435, 900), "DEF   12490", 38, "bold", fill=color("on_accent"), max_w=380)
    c.footer()
    return c


BUILDERS = {"system_flow": system_flow, "two_checks": two_checks}


def render(out_dir=None):
    out = Path(out_dir) if out_dir else ASSETS
    paths = {}
    for key, build in BUILDERS.items():
        canvas = build()
        path = out / FILES[key]
        canvas.save(path)
        paths[key] = (path, canvas.texts)
    return paths


def main():
    p = argparse.ArgumentParser(description="Draw the SIMULATED system pictures for the deck.")
    p.add_argument("--out", default=None, help="folder for the pictures, default assets/")
    a = p.parse_args()
    for key, (path, _) in render(a.out).items():
        print(f"{key}: {path}")


if __name__ == "__main__":
    main()
