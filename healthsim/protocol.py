from . import config

STATUS_CODES = {"green": "G", "amber": "A", "red": "R", "off": "O"}


def _glyph_base():
    return config.section("serial")["glyph_char_base"]


def _slots():
    return config.section("lcd")["custom_char_slots"]


def _finish(body):
    data = body.encode("latin-1") + config.section("serial")["line_end"].encode("ascii")
    limit = config.section("serial")["line_max_bytes"]
    if len(data) > limit:
        raise ValueError(f"serial line is {len(data)} bytes, limit is {limit}")
    return data


def glyph_char(slot):
    if not 0 <= slot < _slots():
        raise ValueError(f"custom character slot {slot} is out of range")
    return chr(_glyph_base() + slot)


def check_text(text):
    cols, _ = config.lcd_size()
    if len(text) > cols:
        raise ValueError(f"LCD text is {len(text)} characters, screen is {cols} wide")
    base = _glyph_base()
    for ch in text:
        code = ord(ch)
        if not (32 <= code < 127 or base <= code < base + _slots()):
            raise ValueError(f"character code {code} cannot be shown on the LCD")
    return text


def text_line(row, text):
    cols, rows = config.lcd_size()
    if not 0 <= row < rows:
        raise ValueError(f"LCD row {row} is out of range")
    return _finish(f"L{row}{check_text(text).ljust(cols)}")


def frame_lines(lines):
    return [text_line(i, t) for i, t in enumerate(lines)]


def glyph_line(slot, pixel_rows):
    lcd = config.section("lcd")
    if not 0 <= slot < _slots():
        raise ValueError(f"custom character slot {slot} is out of range")
    if len(pixel_rows) != lcd["glyph_height"]:
        raise ValueError("a custom character needs one value per pixel row")
    if any(not 0 <= r < 2 ** lcd["glyph_width"] for r in pixel_rows):
        raise ValueError("custom character row value is out of range")
    return _finish(f"G{slot}" + "".join(f"{r:02X}" for r in pixel_rows))


def clear_line():
    return _finish("C")


def status_line(level):
    return _finish("S" + STATUS_CODES[level])


def beep_line(ms):
    return _finish(f"B{int(ms)}")


def parse_device_line(raw):
    s = raw.decode("ascii", "replace") if isinstance(raw, (bytes, bytearray)) else raw
    s = s.strip()
    if s.startswith("READY"):
        parts = s.split()
        if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
            return {"type": "ready", "cols": int(parts[1]), "rows": int(parts[2])}
    elif s[:1] == "T" and len(s) > 1:
        return {"type": "tag", "uid": s[1:]}
    elif s[:1] == "K" and s[1:].isdigit():
        return {"type": "button", "n": int(s[1:])}
    elif s[:1] == "V" and "=" in s:
        name, value = s[1:].split("=", 1)
        try:
            return {"type": "value", "name": name, "value": float(value)}
        except ValueError:
            pass
    return {"type": "unknown", "raw": s}
