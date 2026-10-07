#!/usr/bin/python3
"""Theme lighting for the wired Corsair K65 Plus (1b1c:2b11).

Protocol reference: OpenLinkHub src/devices/k65plusWU/k65plusWU.go,
https://github.com/jurkovic-nikola/OpenLinkHub (GPL-3.0).
Uses only Python's standard library and the vendor HID interface, never grabs
the keyboard input interface or writes onboard profiles/key assignments.
"""

import argparse
import colorsys
import errno
import fcntl
import json
import math
import os
from pathlib import Path
import re
import select
import shutil
import signal
import stat
import struct
import subprocess
import sys
import tempfile
import time

THEME_COLOR = Path.home() / ".local/state/omarchy/current/theme/keyboard.rgb"
HID_ROOT = Path("/sys/class/hidraw")
DEVICE_ID = "HID_ID=0003:00001B1C:00002B11"
SOFTWARE_MODE = bytes.fromhex("01 03 00 02")
HARDWARE_MODE = bytes.fromhex("01 03 00 01")
ACTIVATE_LEDS = bytes.fromhex("0d 00 22")
FIRMWARE = bytes.fromhex("02 13")
KEEPALIVE = bytes.fromhex("12")
# In software mode the firmware reports the volume dial on vendor interface 02
# instead of as media keys on interface 00 (OpenLinkHub backendListener).
DIAL_INTERFACE = "02"
DIAL_STEP = 5
VOLUME_COMMAND = "omarchy-audio-output-volume"
# A failed transfer is usually a one-off (a missed reply, a busy bus) and must not
# bounce the lighting through hardware mode. Errors that mean the device is gone
# tear the connection down at once; anything else only after this many failed loop
# passes in a row. A failing transfer blocks for 1.0 to 1.5 s and the loop adds
# 0.08 to 0.25 s, so three in a row is at least ~3 s of a silent device, long
# enough to rule out a blip and short enough to start recovering quickly.
MAX_CONSECUTIVE_FAILURES = 3
DEVICE_GONE_ERRNOS = frozenset({errno.ENODEV, errno.EIO, errno.EPIPE, errno.ENOENT, errno.ENXIO})
STOP = False
CONFIG_PATH = Path.home() / ".config/omarchy/omacorsair.json"
STATUS_PATH = Path.home() / ".local/state/omarchy/omacorsair/status.json"
DEFAULT_CONFIG = {"mode": "theme", "color": "00aaff", "accent": "ff4080", "brightness": 100, "vivid": True, "speed": 50}
PALETTES = {
    "ocean": ("00ffcc", "00ddee", "00aaff", "0077ff", "3344ff", "6633ff"),
    "sunset": ("ffb000", "ff7000", "ff3050", "ff0088", "bb22dd", "6633ff"),
    "rainbow": ("ff0000", "ff8800", "ffff00", "00ff00", "0088ff", "aa00ff"),
    "synthwave": ("ff0077", "ee00bb", "aa00ff", "6622ff", "0066ff", "00ffff"),
    "mint": ("f0fff0", "baffdf", "70ffc9", "22eebb", "00bb99", "007766"),
    "embers": ("260400", "550600", "990d00", "ee2800", "ff6600", "ffbb22"),
    "moonlight": ("ffffff", "d0ddff", "99bbff", "6688dd", "445599", "222b55"),
    "sakura": ("fff0df", "ffcbd9", "ff99be", "ee6699", "bb4477", "773355"),
    "copper": ("ffe0aa", "ffbb77", "dd8844", "aa5522", "773311", "441c0d"),
    "glacier": ("ffffff", "ccffff", "77eeff", "33bbff", "1177cc", "113366"),
    "toxic": ("bbff00", "77ff00", "22dd00", "229944", "6622aa", "aa00ff"),
    "royal": ("ffcc44", "cc8822", "9955cc", "7733bb", "552299", "331166"),
    "cottoncandy": ("ff99dd", "ddaaff", "bbbbee", "99ccff", "aaffdd", "ffeeaa"),
    "forest": ("ddcc44", "99bb33", "55aa33", "228844", "116633", "084422"),
}
# A single catalog drives the CLI and popup; no duplicate UI mode definitions.
CATALOG = [
    {"id": "theme", "name": "Theme sync", "category": "Custom", "hint": "Your Omarchy theme, translated into light."},
    {"id": "solid", "name": "Solid color", "category": "Custom", "custom": True, "hint": "One perfect color. Yours."},
    {"id": "gaming", "name": "WASD + arrows", "category": "Custom", "custom": True, "hint": "Movement keys in your accent, everything else in your base."},
]
for mode, name, hint in (
    ("ocean", "Ocean", "Cyan shallows fading into violet depths."),
    ("sunset", "Sunset", "Amber skies, hot pink clouds, violet twilight."),
    ("rainbow", "Rainbow rows", "Six bold stripes of the full spectrum."),
    ("synthwave", "Synthwave", "Neon magenta and electric cyan. Midnight, 1987."),
    ("mint", "Mint condition", "Cool cream and fresh sea-glass greens."),
    ("embers", "Embers", "Coal-black reds with a warm golden glow."),
    ("moonlight", "Moonlight", "Silver-white fading into deep midnight blue."),
    ("sakura", "Sakura", "Peach blossoms, rose pink, and dusky plum."),
    ("copper", "Copper & candlelight", "Warm brass, burnished copper, dark espresso."),
    ("glacier", "Glacier", "Polar white, ice cyan, and arctic blue."),
    ("toxic", "Toxic orchid", "Acid-lime green colliding with ultraviolet."),
    ("royal", "Royal velvet", "Gold accents over a rich purple staircase."),
    ("cottoncandy", "Cotton candy", "Soft pink, lilac, sky blue, mint, and custard."),
    ("forest", "Forest floor", "Sunlit moss settling into deep emerald shade."),
):
    CATALOG.append({"id": mode, "name": name, "hint": hint, "category": "Palettes"})
for mode, name, hint, custom in (
    ("aurora", "Aurora", "Slow emerald and violet ribbons wandering across the keys.", False),
    ("nebula", "Nebula", "Indigo, plum, and pink clouds with tiny starlit glints.", False),
    ("matrix", "Matrix rain", "Green light trails falling through a dark keyboard.", False),
    ("fire", "Hearth fire", "Golden heat rises from below into red, flickering embers.", False),
    ("comet", "Comet", "A bright accent-color head with a soft tail sweeping across your base.", True),
    ("rainbowwave", "Prism tide", "A diagonal spectrum rolls across the whole keyboard.", False),
    ("breathe", "Breathing room", "Your base color slowly inhales and exhales.", True),
    ("duotone", "Silk waves", "Your two custom colors weave into a traveling wave.", True),
    ("twinkle", "Fireflies", "Accent-colored glints come and go over a dim base color.", True),
):
    CATALOG.append({"id": mode, "name": name, "hint": hint, "category": "Motion", "animated": True, "custom": custom})
CATALOG.extend([
    {"id": "off", "name": "Lights off", "category": "System", "hint": "A little darkness. All LEDs off."},
    {"id": "hardware", "name": "Built-in lighting", "category": "System", "hint": "Hand control back to your keyboard's lighting hotkeys."},
])
MODES = tuple(item["id"] for item in CATALOG)
ANIMATED_MODES = frozenset(item["id"] for item in CATALOG if item.get("animated"))
# Physical rows -> byte offsets in the K65 Plus color endpoint. From
# OpenLinkHub database/keyboard/k65plus.json (US; shared letter/arrow offsets).
ROW_OFFSETS = (
    (123, 174, 177, 180, 183, 186, 189, 192, 195, 198, 201, 204, 207, 228),
    (159, 90, 93, 96, 99, 102, 105, 108, 111, 114, 117, 135, 138, 126, 222),
    (129, 60, 78, 24, 63, 69, 84, 72, 36, 54, 57, 141, 144, 147, 225),
    (171, 12, 66, 21, 27, 30, 33, 39, 42, 45, 153, 156, 120, 234),
    (318, 87, 81, 18, 75, 15, 51, 48, 162, 165, 168, 330, 246),
    (315, 324, 321, 0, 132, 333, 366, 327, 240, 243, 237),
)
GAMING_OFFSETS = (78, 12, 66, 21, 246, 240, 243, 237)


def read_json(path, fallback):
    try:
        with path.open() as stream:
            value = json.loads(stream.read(4097))
    except FileNotFoundError:
        return fallback.copy()
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return value


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".omacorsair-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def validate_config(value):
    unknown = set(value) - set(DEFAULT_CONFIG)
    if unknown:
        raise ValueError(f"unknown setting: {sorted(unknown)[0]}")
    config = dict(DEFAULT_CONFIG, **value)
    if config["mode"] not in MODES:
        raise ValueError("unsupported lighting mode")
    for key in ("color", "accent"):
        if not isinstance(config[key], str) or not re.fullmatch(r"#?[0-9a-fA-F]{6}", config[key]):
            raise ValueError(f"{key} must be six hex digits")
        config[key] = config[key].lstrip("#").lower()
    if type(config["brightness"]) is not int or not 0 <= config["brightness"] <= 100:
        raise ValueError("brightness must be an integer from 0 to 100")
    if type(config["vivid"]) is not bool:
        raise ValueError("vivid must be true or false")
    if type(config["speed"]) is not int or not 10 <= config["speed"] <= 100:
        raise ValueError("speed must be an integer from 10 to 100")
    return config


def read_config():
    return validate_config(read_json(CONFIG_PATH, DEFAULT_CONFIG))


def rgb(hexcolor):
    return tuple(channel / 255 for channel in bytes.fromhex(hexcolor))


def mix(a, b, amount):
    return tuple(x * (1 - amount) + y * amount for x, y in zip(a, b))


def palette_sample(palette, amount):
    position = max(0, min(1, amount)) * (len(palette) - 1)
    index = min(len(palette) - 2, int(position))
    return mix(rgb(palette[index]), rgb(palette[index + 1]), position - index)


def animated_rgb(mode, x, y, seed, t, base, accent):
    """Deterministic, smooth per-key effects. No input monitoring or flash writes."""
    if mode == "rainbowwave":
        return colorsys.hsv_to_rgb((x * 0.7 + y * 0.18 - t * 0.12) % 1, 1, 1)
    if mode == "breathe":
        return tuple(channel * (0.12 + 0.88 * (0.5 - 0.5 * math.cos(t * 1.3))) for channel in base)
    if mode == "duotone":
        return mix(base, accent, 0.5 + 0.5 * math.sin(x * 5 + y * 2 - t))
    if mode == "aurora":
        ribbon = 0.5 + 0.5 * math.sin(x * 5 + math.sin(y * 3 + t * 0.3) * 1.5 + t * 0.35)
        glow = 0.4 + 0.6 * (0.5 + 0.5 * math.sin(y * 4 - x * 3 + t * 0.6))
        return tuple(channel * glow for channel in palette_sample(("004433", "00ff99", "00bbcc", "6622ff"), ribbon))
    if mode == "nebula":
        cloud = 0.5 + 0.25 * math.sin(x * 8 + t * 0.4) + 0.25 * math.sin(y * 5 - t * 0.3)
        star = max(0, math.sin(t * 0.9 + seed * 2.399)) ** 28 * 0.65
        return mix(palette_sample(("060c44", "441177", "bb2277", "ff7799"), cloud), (1, 0.9, 1), star)
    if mode == "matrix":
        head = (t * 0.45 + round(x * 14) * 0.731) % 1
        distance = (head - y) % 1
        glow = math.exp(-distance * 9)
        return (glow * 0.65 if distance < 0.06 else 0, max(0.01, glow), glow * 0.35)
    if mode == "fire":
        heat = y * 0.75 + 0.15 * math.sin(x * 17 + t * 3) + 0.15 * math.sin(x * 7 - t * 1.8)
        return palette_sample(("100000", "550000", "dd1800", "ff7700", "ffdd44"), heat)
    if mode == "comet":
        distance = ((t * 0.2) % 1 - x + y * 0.1) % 1
        tail = math.exp(-distance * 14)
        light = mix(accent, (1, 1, 1), max(0, 1 - distance * 25))
        return tuple(b * 0.025 + c * tail for b, c in zip(base, light))
    if mode == "twinkle":
        glow = max(0, math.sin(t * 0.8 + seed * 2.399)) ** 18
        return tuple(b * 0.035 + a * glow for b, a in zip(base, accent))
    raise ValueError("unknown animated effect")


def speed_factor(speed):
    """Animation clock rate (phase units per second) for a 10..100 speed setting."""
    return 0.2 + speed * 0.016


def restart_animation(now, speed):
    """A fresh animation clock: phase 0 at `now`, running at `speed`."""
    return {"started": now, "phase0": 0.0, "speed": speed}


def retime_animation(origin, now, speed):
    """Change speed without a jump: bank the phase reached so far as the new origin."""
    return {"started": now, "phase0": animation_phase(origin, now), "speed": speed}


def animation_phase(origin, now):
    return origin["phase0"] + max(0.0, now - origin["started"]) * speed_factor(origin["speed"])


def status_phase(device, config, now):
    """The daemon's current animation phase, rebuilt from status.json for the preview.

    Status files from older versions have no phase0/speed; they mean phase 0 and the
    configured speed, which is what the old formula computed.
    """
    def number(key, default):
        value = device.get(key)
        return float(value) if type(value) in (int, float) and math.isfinite(value) else default

    if device.get("mode", config["mode"]) != config["mode"]:
        return 0.0  # the daemon has not picked up the new mode yet; it restarts at phase 0
    speed = device.get("speed")
    if type(speed) is not int or not 10 <= speed <= 100:
        speed = config["speed"]
    origin = {"started": number("started", now), "phase0": number("phase0", 0.0), "speed": speed}
    return animation_phase(origin, now)


def render_frame(config, theme_color=None, raw=False, elapsed=0, phase=None):
    mode = config["mode"]
    if mode == "hardware" or (mode == "theme" and theme_color is None):
        return None
    color = config["color"]
    if mode == "theme":
        color = vivid(theme_color) if config["vivid"] and not raw else theme_color
    if mode == "off":
        color = "000000"
    data = bytearray(bytes.fromhex(color) * 123 + b"\x00\x00")
    if mode == "gaming":
        for offset in GAMING_OFFSETS:
            data[offset:offset + 3] = bytes.fromhex(config["accent"])
    elif mode in PALETTES:
        for offsets, row_color in zip(ROW_OFFSETS, PALETTES[mode]):
            for offset in offsets:
                data[offset:offset + 3] = bytes.fromhex(row_color)
    elif mode in ANIMATED_MODES:
        data = bytearray(371)
        t = phase if phase is not None else elapsed * speed_factor(config["speed"])
        base, accent = rgb(config["color"]), rgb(config["accent"])
        for row, offsets in enumerate(ROW_OFFSETS):
            for column, offset in enumerate(offsets):
                channels = animated_rgb(mode, column / (len(offsets) - 1), row / 5, offset // 3, t, base, accent)
                data[offset:offset + 3] = bytes(round(max(0, min(1, c)) * 255) for c in channels)
    brightness = config["brightness"] / 100
    data = bytearray(round(channel * brightness) for channel in data)
    data[3:6] = b"\x00\x00\x00"
    return bytes(data)


def log(message):
    print(f"[omacorsair] {message}", file=sys.stderr, flush=True)


def read_color(path=THEME_COLOR):
    """Read a bounded single hex color; themes without keyboard.rgb are skipped."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
    except FileNotFoundError:
        return None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 64:
            raise ValueError("keyboard.rgb must be a small regular file")
        text = os.read(fd, 65).decode("ascii").strip()
    finally:
        os.close(fd)
    if not re.fullmatch(r"#?[0-9a-fA-F]{6}", text):
        raise ValueError("keyboard.rgb must contain one RRGGBB color")
    return text.lstrip("#").lower()


def vivid(color):
    """LED-friendly saturation/value adjustment, matching Omakeychron's intent."""
    rgb = tuple(int(color[i:i + 2], 16) / 255 for i in (0, 2, 4))
    h, s, v = colorsys.rgb_to_hsv(*rgb)
    if s >= 0.15:
        s, v = max(s, 0.9), 1.0
        degrees = h * 360
        if 120 < degrees < 180:
            h = (120 + (degrees - 120) * 0.2) / 360
    return "".join(f"{int(c * 255):02x}" for c in colorsys.hsv_to_rgb(h, s, v))


def candidates(number="01"):
    """Only one USB interface (default 01, lighting) of the exact K65 Plus model."""
    for node in sorted(HID_ROOT.glob("hidraw*")):
        try:
            device = (node / "device").resolve()
            if DEVICE_ID not in (device / "uevent").read_text().splitlines():
                continue
            interface = device.parent / "bInterfaceNumber"
            if interface.read_text().strip() != number:
                continue
            yield Path("/dev") / node.name
        except (OSError, ValueError):
            continue


def report(endpoint, payload=b""):
    data = b"\x00\x08" + endpoint + payload
    if len(data) > 65:
        raise ValueError("HID report exceeds 65 bytes")
    return data.ljust(65, b"\x00")


def color_packets(color):
    # K65 Plus color endpoint holds 371 bytes. Slot 1 is reserved (OpenLinkHub
    # explicitly clears bytes 3..5). Fill every other slot with the same RGB.
    data = bytearray(bytes.fromhex(color) * 123 + b"\x00\x00") if isinstance(color, str) else bytearray(color)
    if len(data) != 371:
        raise ValueError("color frame must contain 371 bytes")
    data[3:6] = b"\x00\x00\x00"
    buffer = struct.pack("<H", len(data) + 2) + b"\x00\x00\x12\x00" + data
    for offset in range(0, len(buffer), 61):
        endpoint = b"\x06\x00" if offset == 0 else b"\x07\x00"
        yield endpoint, buffer[offset:offset + 61]


def device_gone(error):
    """True for errors that mean the keyboard was unplugged, not that one transfer failed."""
    return isinstance(error, OSError) and error.errno in DEVICE_GONE_ERRNOS


class Keyboard:
    leds_active = False  # SOFTWARE_MODE + ACTIVATE_LEDS completed on this connection

    def __init__(self, path):
        self.path = path
        self.fd = os.open(path, os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW)
        self.software_mode = False
        try:
            if not stat.S_ISCHR(os.fstat(self.fd).st_mode):
                raise OSError("not a character device")
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # HIDIOCGRAWINFO: validate the opened device, not just sysfs discovery.
            info = bytearray(8)
            fcntl.ioctl(self.fd, 0x80084803, info, True)
            bus, vendor, product = struct.unpack("IHH", info)
            if (bus, vendor, product) != (3, 0x1B1C, 0x2B11):
                raise OSError("unexpected HID device")
        except BaseException:
            os.close(self.fd)
            raise

    def transfer(self, endpoint, payload=b""):
        # Discard stale vendor replies. Input events are on other interfaces.
        for _ in range(16):
            if not select.select([self.fd], [], [], 0)[0]:
                break
            os.read(self.fd, 64)
        packet = report(endpoint, payload)
        if not select.select([], [self.fd], [], 1.0)[1]:
            raise TimeoutError("keyboard write timed out")
        if os.write(self.fd, packet) != len(packet):
            raise OSError("short HID write")
        deadline = time.monotonic() + 1.5
        replies = []
        while time.monotonic() < deadline:
            if not select.select([self.fd], [], [], max(0, deadline - time.monotonic()))[0]:
                break
            response = os.read(self.fd, 64)
            replies.append(response.hex())
            if len(response) >= 3 and response[0] == 0x00 and response[1] == endpoint[0]:
                if response[2] != 0:
                    raise OSError(f"command {endpoint.hex()} returned status {response[2]:02x}")
                return response
        raise TimeoutError(f"no matching reply to command {endpoint.hex()}: {replies[:3]}")

    def firmware(self):
        data = self.transfer(FIRMWARE)
        if len(data) < 7:
            raise OSError("short firmware reply")
        return f"{data[3]}.{data[4]}.{int.from_bytes(data[5:7], 'little')}"

    def apply(self, color):
        if not self.leds_active:
            # Each step is recorded as soon as it succeeded, so a retry after a failed
            # transfer neither repeats SOFTWARE_MODE nor skips ACTIVATE_LEDS.
            if not self.software_mode:
                self.transfer(SOFTWARE_MODE)
                self.software_mode = True
            self.transfer(ACTIVATE_LEDS)
            time.sleep(0.5)
            self.leds_active = True
        for endpoint, payload in color_packets(color):
            self.transfer(endpoint, payload)

    def close(self):
        try:
            if self.software_mode:
                self.transfer(HARDWARE_MODE)
        finally:
            os.close(self.fd)


def dial_action(data, pressed):
    """Map an interface-02 report to (volume action or None, dial pressed state)."""
    if len(data) > 4 and data[1] == 0x05:
        return {1: "raise", 255: "lower"}.get(data[4]), pressed
    if len(data) > 19 and data[1] == 0x02:
        now = data[19] == 0x02
        return ("mute-toggle" if now and not pressed else None), now
    return None, pressed


def volume_command(action):
    command = shutil.which(VOLUME_COMMAND) or shutil.which(VOLUME_COMMAND, path="/usr/share/omarchy/bin")
    if command:
        return [command, action]
    if action == "mute-toggle":
        return ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"]
    return ["wpctl", "set-volume", "-l", "1.0", "@DEFAULT_AUDIO_SINK@", f"{abs(int(action))}%{'+' if int(action) > 0 else '-'}"]


class Dial:
    """Read-only volume dial listener. Never writes to the device."""

    def __init__(self, path):
        self.fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            if not stat.S_ISCHR(os.fstat(self.fd).st_mode):
                raise OSError("not a character device")
            info = bytearray(8)
            fcntl.ioctl(self.fd, 0x80084803, info, True)
            if struct.unpack("IHH", info) != (3, 0x1B1C, 0x2B11):
                raise OSError("unexpected HID device")
        except BaseException:
            os.close(self.fd)
            raise
        self.pressed = False
        self.pending = 0  # coalesced volume steps while a command is running
        self.child = None

    def run(self, action):
        try:
            self.child = subprocess.Popen(volume_command(action), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                          stderr=subprocess.DEVNULL, start_new_session=True)
        except OSError as error:
            log(f"volume command failed: {error}")

    def flush(self):
        if self.child is not None and self.child.poll() is None:
            return
        self.child = None
        if self.pending:
            step, self.pending = self.pending, 0
            self.run(f"{step:+d}")

    def handle(self, data):
        action, self.pressed = dial_action(data, self.pressed)
        if action == "mute-toggle":
            self.run(action)
        elif action:
            self.pending += DIAL_STEP if action == "raise" else -DIAL_STEP
        self.flush()

    def wait(self, timeout):
        """Sleep up to timeout, reacting to dial events immediately."""
        deadline = time.monotonic() + timeout
        while (remaining := deadline - time.monotonic()) > 0:
            if select.select([self.fd], [], [], min(remaining, 0.03) if self.pending else remaining)[0]:
                self.handle(os.read(self.fd, 64))
            else:
                self.flush()

    def close(self):
        os.close(self.fd)


def open_dial():
    path = next(candidates(DIAL_INTERFACE), None)
    if path is None:
        raise OSError("volume dial interface 02 not found")
    return Dial(path)


def stop(_signal, _frame):
    global STOP
    STOP = True


def run_daemon(raw=False):
    keyboard = None
    applied = None
    next_keepalive = 0
    last_error = None
    last_status = None
    last_config = None
    active_mode = None
    dial = None
    next_dial_attempt = 0
    dial_error = None
    animation = restart_animation(time.monotonic(), DEFAULT_CONFIG["speed"])
    failures = 0
    known_config = None  # last config that validated; error statuses keep reporting it
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while not STOP:
            try:
                config = known_config = read_config()
                now = time.monotonic()
                if config["mode"] != active_mode:
                    active_mode = config["mode"]
                    animation = restart_animation(now, config["speed"])
                elif config["speed"] != animation["speed"]:
                    animation = retime_animation(animation, now, config["speed"])
                color = read_color() if config["mode"] == "theme" else None
                target = render_frame(config, color, raw, phase=animation_phase(animation, now))
                if config["mode"] == "hardware":
                    if dial:
                        closing, dial = dial, None
                        closing.close()
                    if keyboard:
                        # Drop the reference first: close() always releases the fd, even
                        # when HARDWARE_MODE fails, so it must not be closed twice.
                        closing, keyboard, applied = keyboard, None, None
                        closing.close()
                elif target is None:
                    # A theme without a keyboard color leaves current lighting alone.
                    if keyboard and keyboard.software_mode and time.monotonic() >= next_keepalive:
                        keyboard.transfer(KEEPALIVE)
                        next_keepalive = time.monotonic() + 10
                else:
                    if keyboard is None:
                        path = next(candidates(), None)
                        if path is not None:
                            candidate = Keyboard(path)
                            try:
                                firmware = candidate.firmware()
                            except BaseException:
                                candidate.close()
                                raise
                            keyboard = candidate
                            log(f"connected {path}, firmware {firmware}")
                            applied = None
                    if keyboard:
                        if target != applied:
                            keyboard.apply(target)
                            if config != last_config or applied is None:
                                log(f"applied {config['mode']}, brightness {config['brightness']}%")
                                last_config = config.copy()
                            applied = target
                            next_keepalive = time.monotonic() + 10
                        if time.monotonic() >= next_keepalive:
                            keyboard.transfer(KEEPALIVE)
                            next_keepalive = time.monotonic() + 10
                # Software mode silences the dial's media keys; take over while active.
                if keyboard and keyboard.software_mode and dial is None and time.monotonic() >= next_dial_attempt:
                    try:
                        dial = open_dial()
                        dial_error = None
                        log("volume dial active")
                    except OSError as error:
                        next_dial_attempt = time.monotonic() + 5
                        if str(error) != dial_error:
                            dial_error = str(error)
                            hint = "; re-run install-device-access.sh" if isinstance(error, PermissionError) else ""
                            log(f"volume dial unavailable: {error}{hint}")
                last_error = None
                failures = 0
                status = {"connected": keyboard is not None if config["mode"] != "hardware" else next(candidates(), None) is not None,
                          "applied": applied is not None, "mode": config["mode"], "settings": config,
                          **animation, "dial": dial is not None, "error": ""}
            except (OSError, ValueError, UnicodeError) as error:
                message = str(error)
                if message != last_error:
                    log(message)
                last_error = message
                failures += 1
                # The failed pass may have stopped halfway through a frame (or never
                # reached the device), so whatever comes next must be sent in full.
                applied = None
                if device_gone(error) or failures >= MAX_CONSECUTIVE_FAILURES:
                    if not device_gone(error) and keyboard:
                        log(f"{failures} errors in a row, reconnecting")
                    failures = 0
                    if dial:
                        dial.close()
                        dial = None
                    if keyboard:
                        try:
                            keyboard.close()
                        except OSError:
                            pass
                        keyboard = None
                # Keep what the panel needs to stay useful (look, settings, preview clock, dial)
                # alongside the error; only the connection fields change.
                status = {"connected": False, "applied": False, "error": message, "dial": dial is not None}
                if known_config is not None:
                    status.update(mode=known_config["mode"], settings=known_config, **animation)
            if status != last_status:
                atomic_json(STATUS_PATH, status)
                last_status = status
            delay = 0.08 if active_mode in ANIMATED_MODES and keyboard is not None else 0.25
            if dial:
                try:
                    dial.wait(delay)
                except OSError as error:
                    log(f"volume dial disconnected: {error}")
                    dial.close()
                    dial = None
            else:
                time.sleep(delay)
    finally:
        if dial:
            dial.close()
        if keyboard:
            try:
                keyboard.close()
            except OSError as error:
                log(f"disconnect: {error}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["probe", "daemon", "preview", "test", "set", "status"])
    parser.add_argument("value", nargs="?", help="JSON settings object for set")
    parser.add_argument("--raw", action="store_true", help="use exact theme RGB without LED adjustment")
    args = parser.parse_args()
    if args.action == "set":
        if not args.value:
            raise ValueError("set requires a JSON settings object")
        update = json.loads(args.value)
        if not isinstance(update, dict):
            raise ValueError("settings must be an object")
        config = validate_config(dict(read_config(), **update))
        atomic_json(CONFIG_PATH, config)
        print(json.dumps({"config": config}))
    elif args.action == "status":
        config = read_config()
        device = read_json(STATUS_PATH, {"connected": False, "error": "Waiting for keyboard"})
        theme = read_color() if config["mode"] == "theme" else None
        frame = render_frame(config, theme, args.raw, phase=status_phase(device, config, time.monotonic()))
        preview = [["#" + frame[offset:offset + 3].hex() for offset in offsets] for offsets in ROW_OFFSETS] if frame else []
        print(json.dumps({"config": config, "device": device, "catalog": CATALOG, "preview": preview}))
    elif args.action == "daemon":
        run_daemon(args.raw)
    elif args.action == "preview":
        color = read_color()
        print(json.dumps({"theme": color, "led": color if args.raw or color is None else vivid(color)}))
    else:
        path = next(candidates(), None)
        if path is None:
            raise OSError("wired K65 Plus (1b1c:2b11), interface 01, not found")
        keyboard = Keyboard(path)
        try:
            print(json.dumps({"device": str(path), "firmware": keyboard.firmware()}), flush=True)
            if args.action == "test":
                color = read_color()
                if color is None:
                    raise ValueError("this theme has no keyboard.rgb")
                keyboard.apply(color if args.raw else vivid(color))
                log("theme color applied for 8 seconds; restoring hardware lighting afterwards")
                time.sleep(8)
        finally:
            keyboard.close()


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, UnicodeError) as error:
        log(error)
        sys.exit(1)
