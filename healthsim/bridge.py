import argparse
import json
import random
import sqlite3
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import config, protocol, tags

TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
READING_COLUMNS = ["id", "timestamp", "data_source", "crew", "name", "value", "unit", "quality"]
EVENT_COLUMNS = ["id", "timestamp", "data_source", "kind", "crew", "detail"]


def now_utc():
    return datetime.now(timezone.utc).strftime(TIME_FORMAT)


def live():
    return config.section("live")


class Store:
    def __init__(self, path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.lock = threading.Lock()
        with self.lock:
            self.db.execute(
                "create table if not exists readings (id integer primary key autoincrement, timestamp text not null, "
                "data_source text not null, crew text, name text not null, value real not null, unit text, quality text not null)"
            )
            self.db.execute(
                "create table if not exists events (id integer primary key autoincrement, timestamp text not null, "
                "data_source text not null, kind text not null, crew text, detail text)"
            )
            self.db.commit()

    def add_reading(self, source, crew, name, value, unit, quality):
        with self.lock:
            cur = self.db.execute(
                "insert into readings (timestamp, data_source, crew, name, value, unit, quality) values (?, ?, ?, ?, ?, ?, ?)",
                (now_utc(), source, crew, name, value, unit, quality),
            )
            self.db.commit()
            return cur.lastrowid

    def add_event(self, source, kind, crew=None, detail=None):
        with self.lock:
            cur = self.db.execute(
                "insert into events (timestamp, data_source, kind, crew, detail) values (?, ?, ?, ?, ?)",
                (now_utc(), source, kind, crew, detail),
            )
            self.db.commit()
            return cur.lastrowid

    def query(self, sql, args, columns):
        with self.lock:
            rows = self.db.execute(sql, args).fetchall()
        return [dict(zip(columns, r)) for r in rows]

    def readings(self, since=0, limit=None, name=None):
        limit = limit or live()["default_limit"]
        if name:
            return self.query("select * from readings where id > ? and name = ? order by id limit ?", (since, name, limit), READING_COLUMNS)
        return self.query("select * from readings where id > ? order by id limit ?", (since, limit), READING_COLUMNS)

    def events(self, since=0, limit=None):
        limit = limit or live()["default_limit"]
        return self.query("select * from events where id > ? order by id limit ?", (since, limit), EVENT_COLUMNS)

    def latest(self):
        rows = self.query(
            "select * from readings where id in (select max(id) from readings group by name) order by name", (), READING_COLUMNS
        )
        return {r["name"]: r for r in rows}

    def dump_text(self):
        with self.lock:
            return "\n".join(self.db.iterdump())


def parse_packet(text):
    if "," not in text or "=" not in text:
        return None
    fields = {}
    for part in text.split(","):
        if "=" not in part:
            return None
        key, value = part.split("=", 1)
        fields[key.strip()] = value.strip()
    return fields


class Bridge:
    def __init__(self, store, source="REAL"):
        self.store = store
        self.source = source
        self.active_crew = None
        self.ignored = 0
        self.last_status = None

    def add_value(self, name, value):
        spec = live()["values"].get(name)
        if spec is None:
            quality, unit = "unknown_name", None
        else:
            lo, hi = spec["range"]
            quality = "ok" if lo <= value <= hi else "out_of_range"
            unit = spec["unit"]
        self.store.add_reading(self.source, self.active_crew, name, value, unit, quality)

    def handle_tag(self, uid):
        crew = tags.lookup(uid)
        if crew:
            self.active_crew = crew
            self.store.add_event(self.source, "login", crew=crew)
        else:
            self.store.add_event(self.source, "unknown_tag")
        return "tag"

    def handle_packet(self, packet):
        names = live()["wearable_names"]
        handled = False
        for key, text in packet.items():
            if key in names:
                try:
                    self.add_value(names[key], float(text))
                except ValueError:
                    continue
                handled = True
            elif key.lower() == "status":
                if text != self.last_status:
                    self.last_status = text
                    self.store.add_event(self.source, "wearable_status", crew=self.active_crew, detail=text)
                handled = True
        if not handled:
            self.ignored += 1
            return None
        return "packet"

    def handle(self, raw):
        text = raw.decode("ascii", "replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
        text = text.strip()
        if text.startswith("UID=") and "," not in text:
            uid = text[4:]
            if uid.upper() in ("", "NONE"):
                self.ignored += 1
                return None
            return self.handle_tag(uid)
        if text.startswith("{"):
            try:
                obj = json.loads(text)
            except ValueError:
                self.ignored += 1
                return None
            if not isinstance(obj, dict):
                self.ignored += 1
                return None
            if obj.get("event") == "SCAN":
                uid = str(obj.get("uid", ""))
                if uid.upper() in ("", "NONE"):
                    self.ignored += 1
                    return None
                return self.handle_tag(uid)
            return self.handle_packet({k: str(v) for k, v in obj.items()})
        packet = parse_packet(text)
        if packet is not None:
            return self.handle_packet(packet)
        msg = protocol.parse_device_line(text)
        kind = msg["type"]
        if kind == "ready":
            self.store.add_event(self.source, "ready", detail=f"{msg['cols']}x{msg['rows']}")
        elif kind == "tag":
            return self.handle_tag(msg["uid"])
        elif kind == "button":
            self.store.add_event(self.source, "button", crew=self.active_crew, detail=str(msg["n"]))
        elif kind == "value":
            self.add_value(msg["name"], msg["value"])
        else:
            self.ignored += 1
            return None
        return kind


def payload(extra):
    return {**config.manifest_header(), **extra}


def make_handler(store, bridge):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send_json(self, code, body):
            data = json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            url = urlparse(self.path)
            q = parse_qs(url.query)
            try:
                since = int(q.get("since", ["0"])[0])
                limit = int(q["limit"][0]) if "limit" in q else None
            except ValueError:
                self.send_json(400, {"error": "since and limit must be whole numbers"})
                return
            name = q.get("name", [None])[0]
            if url.path == "/api/health":
                self.send_json(200, payload({"status": "ok", "bridge_data_source": bridge.source, "time": now_utc(), "active_crew": bridge.active_crew}))
            elif url.path == "/api/latest":
                self.send_json(200, payload({"active_crew": bridge.active_crew, "latest": store.latest()}))
            elif url.path == "/api/readings":
                rows = store.readings(since, limit, name)
                self.send_json(200, payload({"readings": rows, "last_id": rows[-1]["id"] if rows else since}))
            elif url.path == "/api/events":
                rows = store.events(since, limit)
                self.send_json(200, payload({"events": rows, "last_id": rows[-1]["id"] if rows else since}))
            else:
                self.send_json(404, {"error": "unknown path", "paths": ["/api/health", "/api/latest", "/api/readings", "/api/events"]})

    return Handler


def make_server(store, bridge, host, port):
    return ThreadingHTTPServer((host, port), make_handler(store, bridge))


def read_serial(port, baud, bridge, reconnect_s):
    import serial

    while True:
        try:
            with serial.Serial(port, baud, timeout=1) as link:
                print(f"connected to {port}", flush=True)
                while True:
                    line = link.readline()
                    if line:
                        bridge.handle(line)
        except (serial.SerialException, OSError) as e:
            print(f"serial link lost ({e}); retrying in {reconnect_s} s", flush=True)
            time.sleep(reconnect_s)


def feed_lines(link, bridge, max_line=256):
    buf = b""
    while True:
        chunk = link.recv(max_line)
        if not chunk:
            raise ConnectionError("the wearable closed the link")
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            if line.strip():
                bridge.handle(line)
        if len(buf) > max_line:
            buf = b""


def read_bluetooth(address, channel, bridge, reconnect_s, silence_s):
    import socket

    while True:
        try:
            with socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM) as link:
                link.settimeout(silence_s)
                link.connect((address, channel))
                print(f"connected to {address} on channel {channel}", flush=True)
                feed_lines(link, bridge)
        except OSError as e:
            print(f"bluetooth link lost ({e}); retrying in {reconnect_s} s", flush=True)
            time.sleep(reconnect_s)


def simulate(bridge, count=None, interval_s=None):
    sim = live()["simulate"]
    interval = sim["interval_s"] if interval_s is None else interval_s
    rng = random.Random(config.section("simulation")["seed"])
    cols, rows = config.lcd_size()
    bridge.handle(f"READY {cols} {rows}\n")
    bridge.handle(f"T{tags.simulated_uid(sim['crew'])}\n")
    n = 0
    while count is None or n < count:
        bridge.handle(f"Vhr={round(rng.gauss(sim['hr_mean'], sim['hr_sd']))}\n")
        n += 1
        if interval:
            time.sleep(interval)


def main():
    cfg = live()
    p = argparse.ArgumentParser(description="Receive wearable readings over Bluetooth serial, store them on the Pi and serve them over HTTP.")
    p.add_argument("--port", default=cfg["bluetooth_port"], help="serial port of the paired HC-05, for example /dev/rfcomm0")
    p.add_argument("--bt-address", default=None, help="connect straight to the paired Bluetooth module, for example AA:BB:CC:DD:EE:FF; no rfcomm needed")
    p.add_argument("--simulate", action="store_true", help="feed SIMULATED readings instead of reading the wearable")
    p.add_argument("--http-port", type=int, default=cfg["http_port"])
    p.add_argument("--db", default=str(config.ROOT / cfg["db_path"]))
    a = p.parse_args()
    store = Store(a.db)
    bridge = Bridge(store, "SIMULATED" if a.simulate else "REAL")
    server = make_server(store, bridge, cfg["http_host"], a.http_port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"serving http://{cfg['http_host']}:{a.http_port}/api/latest  data_source={bridge.source}  database={a.db}", flush=True)
    try:
        if a.simulate:
            simulate(bridge)
        elif a.bt_address:
            read_bluetooth(a.bt_address, cfg["bluetooth_channel"], bridge, cfg["reconnect_s"], cfg["silence_timeout_s"])
        else:
            read_serial(a.port, config.section("serial")["baud"], bridge, cfg["reconnect_s"])
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
