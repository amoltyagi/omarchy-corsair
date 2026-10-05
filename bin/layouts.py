#!/usr/bin/python3
"""Read and switch English/German layouts on actual Hyprland keyboards."""
import argparse
import json
import re
import subprocess
import sys

LABELS = {"us": "EN", "de": "DE"}


def hyprctl(*args):
    result = subprocess.run(["hyprctl", *args], capture_output=True, text=True, timeout=3, check=True)
    return result.stdout


def typed_keyboards(devices):
    excluded = re.compile(r"power-button|video-bus|consumer-control|system-control|hotkeys", re.I)
    return [keyboard for keyboard in devices.get("keyboards", [])
            if keyboard.get("name") and not excluded.search(keyboard["name"])]


def keyboard_code(keyboard):
    layouts = keyboard.get("layout", "").split(",")
    index = keyboard.get("active_layout_index")
    if type(index) is int and 0 <= index < len(layouts):
        return layouts[index]
    keymap = keyboard.get("active_keymap", "").lower()
    if "german" in keymap:
        return "de"
    if "english" in keymap:
        return "us"
    return layouts[0] if layouts else ""


def summarize(devices):
    keyboards = typed_keyboards(devices)
    preferred = next((k for k in keyboards if "k65-plus" in k["name"]), None)
    preferred = preferred or next((k for k in keyboards if k.get("main")), None)
    preferred = preferred or (keyboards[0] if keyboards else {})
    active = keyboard_code(preferred)
    available = [code for code in LABELS if code in preferred.get("layout", "").split(",")]
    return {"active": active, "label": LABELS.get(active, active.upper()),
            "name": preferred.get("active_keymap", "No keyboard detected"),
            "available": available, "keyboard": preferred.get("name", ""), "count": len(keyboards)}


def switch_plan(devices, code):
    if code not in LABELS:
        raise ValueError("choose us (English) or de (German)")
    plan = []
    for keyboard in typed_keyboards(devices):
        layouts = keyboard.get("layout", "").split(",")
        if code in layouts:
            plan.append((keyboard["name"], str(layouts.index(code))))
    if not plan:
        raise ValueError(f"{code} is not configured; set kb_layout = \"us,de\" in ~/.config/hypr/input.lua")
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["status", "set", "toggle"])
    parser.add_argument("layout", nargs="?")
    args = parser.parse_args()
    devices = json.loads(hyprctl("devices", "-j"))
    if args.action != "status":
        code = args.layout if args.action == "set" else ("de" if summarize(devices)["active"] == "us" else "us")
        for name, index in switch_plan(devices, code):
            response = hyprctl("switchxkblayout", name, index)
            if response.strip() != "ok":
                raise RuntimeError(response.strip() or "layout switch failed")
        devices = json.loads(hyprctl("devices", "-j"))
        if summarize(devices)["active"] != code:
            raise RuntimeError("keyboard did not confirm the requested layout")
    print(json.dumps(summarize(devices)))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"[omacorsair] {error}", file=sys.stderr)
        sys.exit(1)
