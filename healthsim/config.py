import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
SETTINGS_PATH = CONFIG_DIR / "settings.json"
TAGS_PATH = CONFIG_DIR / "tags.json"
TAGS_LOCAL_PATH = CONFIG_DIR / "tags.local.json"


@lru_cache(maxsize=None)
def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def settings(path=None):
    return _read(str(path or SETTINGS_PATH))


def section(name):
    return settings()[name]


SOURCE = settings()["meta"]["data_source"]
PREFIX = settings()["meta"]["file_prefix"]
BANNER = settings()["meta"]["banner"]


def crew_ids():
    return list(section("crew"))


def crew(crew_id):
    return section("crew")[crew_id]


def scenario(crew_id):
    return section("scenarios")[crew(crew_id)["scenario"]]


def alert(key):
    return section("alerts")[key]


def lcd_size():
    lcd = section("lcd")
    return lcd["cols"], lcd["rows"]


def data_dir(crew_id):
    return ROOT / "data" / crew_id


def total_days():
    sim = section("simulation")
    return sim["calibration_days"] + sim["scenario_days"]


def manifest_header():
    meta = section("meta")
    return {
        "data_source": meta["data_source"],
        "disclaimer": meta["disclaimer"],
        "ai_acknowledgement": meta["ai_acknowledgement"],
        "threshold_note": meta["threshold_note"],
        "scenario_label": meta["scenario_label"],
    }
