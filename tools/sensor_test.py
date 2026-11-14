import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from healthsim import config

PINS = config.section("hardware")["pi_sensors"]


def read_dht11():
    for dev in sorted(Path("/sys/bus/iio/devices").glob("iio:device*")):
        try:
            if (dev / "name").read_text().strip() != PINS["dht11_sysfs_name"]:
                continue
        except OSError:
            continue
        for _ in range(PINS["retries"]):
            try:
                t = int((dev / "in_temp_input").read_text()) / 1000.0
                h = int((dev / "in_humidityrelative_input").read_text()) / 1000.0
                return t, h
            except (OSError, ValueError):
                time.sleep(1.0)
        return None
    return "overlay_missing"


class Pressure:
    def __init__(self):
        self.bus = None
        self.addr = None
        try:
            try:
                from smbus2 import SMBus
            except ImportError:
                from smbus import SMBus
            self.bus = SMBus(PINS["pressure_i2c_bus"])
        except Exception:
            return
        for text in PINS["pressure_i2c_addresses"]:
            a = int(text, 16)
            try:
                self.chip = self.bus.read_byte_data(a, 0xD0)
            except OSError:
                continue
            self.addr = a
            self.load_calibration()
            return

    def load_calibration(self):
        raw = self.bus.read_i2c_block_data(self.addr, 0x88, 24)
        u = lambda i: raw[i] | (raw[i + 1] << 8)
        s = lambda i: u(i) - 65536 if u(i) > 32767 else u(i)
        self.t1, self.t2, self.t3 = u(0), s(2), s(4)
        self.p1 = u(6)
        self.p2, self.p3, self.p4, self.p5, self.p6, self.p7, self.p8, self.p9 = (s(8 + 2 * i) for i in range(8))

    def read(self):
        if self.bus is None:
            return "i2c_missing"
        if self.addr is None:
            return "not_found"
        self.bus.write_byte_data(self.addr, 0xF4, 0x25)
        time.sleep(0.05)
        d = self.bus.read_i2c_block_data(self.addr, 0xF7, 6)
        adc_p = (d[0] << 12) | (d[1] << 4) | (d[2] >> 4)
        adc_t = (d[3] << 12) | (d[4] << 4) | (d[5] >> 4)
        v1 = (adc_t / 16384.0 - self.t1 / 1024.0) * self.t2
        v2 = ((adc_t / 131072.0 - self.t1 / 8192.0) ** 2) * self.t3
        t_fine = v1 + v2
        temp = t_fine / 5120.0
        v1 = t_fine / 2.0 - 64000.0
        v2 = v1 * v1 * self.p6 / 32768.0
        v2 = v2 + v1 * self.p5 * 2.0
        v2 = v2 / 4.0 + self.p4 * 65536.0
        v1 = (self.p3 * v1 * v1 / 524288.0 + self.p2 * v1) / 524288.0
        v1 = (1.0 + v1 / 32768.0) * self.p1
        if v1 == 0:
            return None
        p = 1048576.0 - adc_p
        p = (p - v2 / 4096.0) * 6250.0 / v1
        v1 = self.p9 * p * p / 2147483648.0
        v2 = p * self.p8 / 32768.0
        p = p + (v1 + v2 + self.p7) / 16.0
        return temp, p / 100.0


def make_pir():
    try:
        from gpiozero import MotionSensor

        return MotionSensor(PINS["pir_gpio"])
    except Exception as e:
        return str(e)


def dht_text():
    dht = read_dht11()
    if dht == "overlay_missing":
        return "DHT11: no reading (add dtoverlay=dht11,gpiopin=%d to /boot/firmware/config.txt and reboot)" % PINS["dht11_gpio"]
    if dht is None:
        return "DHT11: no reading (check wiring: 3.3 V, GND and data on GPIO %d)" % PINS["dht11_gpio"]
    return f"DHT11: {dht[0]:.0f} C  {dht[1]:.0f} % RH"


def pir_text(pir):
    if isinstance(pir, str):
        return f"PIR: no reading ({pir})"
    return "PIR: MOTION" if pir.motion_detected else "PIR: still"


def pressure_text(pressure):
    try:
        pr = pressure.read()
    except OSError:
        pr = None
    if isinstance(pr, tuple):
        return f"PRESSURE: {pr[1]:.1f} hPa  {pr[0]:.1f} C"
    return f"PRESSURE: no reading ({pr if pr else 'check wiring'})"


def main():
    p = argparse.ArgumentParser(description="Print one line per interval from each real sensor on the Pi.")
    p.add_argument("--only", nargs="+", choices=["dht11", "pir", "pressure"], default=["dht11", "pir", "pressure"], help="test only these sensors, for example --only dht11")
    p.add_argument("--count", type=int, default=0, help="stop after this many lines, 0 runs until Ctrl+C")
    a = p.parse_args()
    pir = make_pir() if "pir" in a.only else None
    pressure = Pressure() if "pressure" in a.only else None
    labels = {"dht11": PINS["dht11_label"], "pir": PINS["pir_label"], "pressure": PINS["pressure_label"]}
    print(f"REAL sensor readings, not {config.SOURCE}. Testing: " + "; ".join(labels[k] for k in a.only) + ".")
    if pressure is not None:
        print(f"pressure chip id: {hex(pressure.chip) if pressure.addr is not None else 'none'}  (0x58 = BMP280, 0x60 = BME280)")
    n = 0
    while True:
        parts = []
        if "dht11" in a.only:
            parts.append(dht_text())
        if "pir" in a.only:
            parts.append(pir_text(pir))
        if "pressure" in a.only:
            parts.append(pressure_text(pressure))
        print(f"{time.strftime('%H:%M:%S')}  " + " | ".join(parts), flush=True)
        n += 1
        if a.count and n >= a.count:
            break
        time.sleep(PINS["read_interval_s"])


if __name__ == "__main__":
    main()
