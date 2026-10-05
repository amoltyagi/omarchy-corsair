"""Explicit live test for rapid gallery cycling and integrated EN/DE actions."""
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def helper(script, *args):
    return json.loads(subprocess.check_output(["/usr/bin/python3", "-I", str(ROOT / "bin" / script), *args], text=True))


def ipc(*args):
    subprocess.run(["omarchy-shell", "case.omacorsair", *args], check=True)


def wait_mode(mode):
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        state = helper("omacorsair.py", "status")
        if (state["config"]["mode"] == mode and state["device"].get("settings") == state["config"]
                and not state["device"].get("error")):
            return
        time.sleep(0.1)
    raise RuntimeError(f"Gallery did not settle on {mode}: {state}")


def wait_language(code):
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        state = helper("layouts.py", "status")
        if state["active"] == code:
            return
        time.sleep(0.1)
    raise RuntimeError(f"Language did not switch to {code}: {state}")


initial = helper("omacorsair.py", "status")
original = initial["config"]
original_language = helper("layouts.py", "status")["active"]
ids = [look["id"] for look in initial["catalog"]]
start = ids.index(original["mode"])
try:
    for _ in range(12):
        ipc("next")
    wait_mode(ids[(start + 12) % len(ids)])
    for _ in range(8):
        ipc("previous")
    wait_mode(ids[(start + 4) % len(ids)])
    print("PASS: rapid gallery cycling preserves every requested step", flush=True)
    ipc("setLanguage", "de")
    wait_language("de")
    ipc("toggleLanguage")
    wait_language("us")
    print("PASS: integrated German selection and English toggle", flush=True)
finally:
    helper("omacorsair.py", "set", json.dumps(original))
    wait_mode(original["mode"])
    helper("layouts.py", "set", original_language)
    print("Restored original lighting and language", flush=True)
