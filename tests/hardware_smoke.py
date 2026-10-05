"""Explicit live test: briefly exercise each mode, then restore saved settings."""
import json
from pathlib import Path
import subprocess
import time

HELPER = Path(__file__).resolve().parents[1] / "bin/omacorsair.py"


def helper(*args):
    return json.loads(subprocess.check_output(["/usr/bin/python3", "-I", str(HELPER), *args], text=True))


def wait_applied(mode):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        status = helper("status")
        config, device = status["config"], status["device"]
        if (config["mode"] == mode and device.get("settings") == config
                and device.get("connected") and not device.get("error")
                and (mode == "hardware" or device.get("applied"))):
            return
        time.sleep(0.25)
    raise RuntimeError(f"Mode {mode} did not apply: {status}")


original = helper("status")["config"]
try:
    subprocess.run(["omarchy-shell", "case.omacorsair", "setColor", "00aaff"], check=True)
    wait_applied("solid")
    print("PASS: menu action → manual blue", flush=True)
    helper("set", '{"brightness":50,"accent":"ff4080"}')
    wait_applied("solid")
    print("PASS: 50% brightness", flush=True)
    catalog = helper("status")["catalog"]
    for look in catalog:
        mode = look["id"]
        subprocess.run(["omarchy-shell", "case.omacorsair", "setMode", mode], check=True)
        wait_applied(mode)
        if look.get("animated"):
            time.sleep(2)
            wait_applied(mode)  # ensure continuous writes remain healthy
        print(f"PASS: menu action → {mode}", flush=True)
finally:
    helper("set", json.dumps(original))
    wait_applied(original["mode"])
    print("Restored original settings", flush=True)
