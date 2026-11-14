import hashlib
import json
import secrets

from . import config


def normalise(uid):
    return "".join(ch for ch in str(uid).upper() if ch.isalnum() or ch == "-")


def hash_tag(uid, salt):
    return hashlib.sha256(f"{salt}:{normalise(uid)}".encode("utf-8")).hexdigest()


def _load(path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def tag_files():
    return [t for t in (_load(config.TAGS_PATH), _load(config.TAGS_LOCAL_PATH)) if t]


def lookup(uid):
    for t in tag_files():
        crew_id = t.get("tags", {}).get(hash_tag(uid, t["salt"]))
        if crew_id in config.crew_ids():
            return crew_id
    return None


def simulated_uid(crew_id):
    return _load(config.TAGS_PATH)["simulated_uids"][crew_id]


def enrol(uid, crew_id):
    if crew_id not in config.crew_ids():
        raise ValueError(f"unknown crew profile {crew_id}")
    local = _load(config.TAGS_LOCAL_PATH) or {"salt": secrets.token_hex(16), "tags": {}}
    local["tags"][hash_tag(uid, local["salt"])] = crew_id
    config.TAGS_LOCAL_PATH.write_text(json.dumps(local, indent=2), encoding="utf-8")
    return crew_id
