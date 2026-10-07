#!/usr/bin/python3
"""Read and switch the keyboard layouts configured in Hyprland (kb_layout), e.g. us,de."""
import argparse
import json
import re
import subprocess
import sys

# Short code shown on the bar. Anything not listed is the upper-cased layout code.
LABELS = {"us": "EN", "de": "DE", "gb": "UK"}
# Human names for layouts Hyprland cannot name: it reports only the active keymap.
# They follow xkb's wording, which is also what Hyprland shows for the active layout.
NAMES = {
    "us": "English (US)", "gb": "English (UK)", "de": "German", "fr": "French", "es": "Spanish",
    "it": "Italian", "pt": "Portuguese", "br": "Portuguese (Brazil)", "nl": "Dutch", "be": "Belgian",
    "ch": "German (Switzerland)", "at": "German (Austria)", "se": "Swedish", "no": "Norwegian",
    "dk": "Danish", "fi": "Finnish", "pl": "Polish", "cz": "Czech", "ru": "Russian",
    "ua": "Ukrainian", "tr": "Turkish", "jp": "Japanese", "kr": "Korean", "ca": "Canadian",
}
ADD_HINT = 'add layouts, for example kb_layout = "us,de", in ~/.config/hypr/input.lua'


def hyprctl(*args):
    result = subprocess.run(["hyprctl", *args], capture_output=True, text=True, timeout=3, check=True)
    return result.stdout


def typed_keyboards(devices):
    excluded = re.compile(r"power-button|video-bus|consumer-control|system-control|hotkeys", re.I)
    return [keyboard for keyboard in devices.get("keyboards", [])
            if keyboard.get("name") and not excluded.search(keyboard["name"])]


def configured(keyboard):
    """Layouts of one keyboard in kb_layout order, as dicts with index, code, variant and key.

    `index` is the (first) position Hyprland's switchxkblayout expects. `key` names the entry for the
    panel and the CLI: the code, or code(variant) when the same code is configured twice with
    different variants (kb_layout "us,us" with kb_variant ",intl"). Variants are positional,
    like kb_variant itself.
    """
    codes = [code.strip() for code in keyboard.get("layout", "").split(",")]
    variants = [variant.strip() for variant in keyboard.get("variant", "").split(",")]
    variants += [""] * (len(codes) - len(variants))
    entries = []
    for index, (code, variant) in enumerate(zip(codes, variants)):
        if not code:
            continue
        same = next((e for e in entries if e["code"] == code and e["variant"] == variant), None)
        if same:
            same["indexes"].append(index)  # a repeated layout is one entry; any of its slots is active
        else:
            entries.append({"index": index, "indexes": [index], "code": code, "variant": variant})
    for entry in entries:
        clash = sum(other["code"] == entry["code"] for other in entries) > 1
        entry["key"] = f"{entry['code']}({entry['variant']})" if clash and entry["variant"] else entry["code"]
    return entries


def label_for(entry):
    label = LABELS.get(entry["code"], entry["code"].upper())
    # The same code twice (us and us(intl)): tell them apart on the bar too.
    return f"{label}-{entry['variant'].upper()}" if entry["key"] != entry["code"] else label


def name_for(entry):
    name = NAMES.get(entry["code"], entry["code"])
    return f"{name} ({entry['variant']})" if entry["variant"] else name


def resolve(entries, requested):
    """Find a configured layout by key or, failing that, by bare code. None when unknown."""
    requested = (requested or "").strip().lower()
    for field in ("key", "code"):
        for entry in entries:
            if entry[field].lower() == requested:
                return entry
    return None


def active_entry(keyboard, entries=None):
    entries = configured(keyboard) if entries is None else entries
    index = keyboard.get("active_layout_index")
    if type(index) is int:
        return next((entry for entry in entries if index in entry["indexes"]), None)
    # Older Hyprland reports no index: recognize the active keymap name instead.
    keymap = keyboard.get("active_keymap", "").lower()
    matches = [entry for entry in entries if keymap.startswith(name_for(entry).lower().split(" (")[0])]
    exact = [entry for entry in matches if name_for(entry).lower() in keymap]
    return (exact or matches or entries or [None])[0]


def keyboard_code(keyboard):
    entry = active_entry(keyboard)
    return entry["key"] if entry else ""


def preferred_keyboard(devices):
    keyboards = typed_keyboards(devices)
    preferred = next((k for k in keyboards if "k65-plus" in k["name"]), None)
    preferred = preferred or next((k for k in keyboards if k.get("main")), None)
    return preferred or (keyboards[0] if keyboards else {})


def summarize(devices):
    preferred = preferred_keyboard(devices)
    entries = configured(preferred)
    active = active_entry(preferred, entries)
    keymap = preferred.get("active_keymap", "")
    layouts = [{"code": entry["key"], "label": label_for(entry),
                # Hyprland names the active layout itself; the others come from NAMES.
                "name": keymap if entry is active and keymap else name_for(entry)} for entry in entries]
    current = next((layout for layout in layouts if active and layout["code"] == active["key"]), None)
    return {"active": active["key"] if active else "",
            "label": current["label"] if current else "",
            "name": current["name"] if current else keymap or "No keyboard detected",
            "available": [entry["key"] for entry in entries], "layouts": layouts,
            "keyboard": preferred.get("name", ""), "count": len(typed_keyboards(devices))}


def target_layout(devices, requested):
    """The layout configured on the preferred keyboard that `requested` names."""
    entries = configured(preferred_keyboard(devices))
    if not entries:
        raise ValueError("no keyboard layouts detected")
    entry = resolve(entries, requested)
    if entry is None:
        raise ValueError(f"{requested!r} is not configured; choose one of: {', '.join(e['key'] for e in entries)}")
    return entry


def next_layout(devices):
    """The layout after the active one, wrapping around (toggle)."""
    preferred = preferred_keyboard(devices)
    entries = configured(preferred)
    if len(entries) < 2:
        raise ValueError(f"only one keyboard layout is configured; {ADD_HINT}")
    active = active_entry(preferred, entries)
    position = entries.index(active) if active in entries else -1
    return entries[(position + 1) % len(entries)]


def switch_plan(devices, code):
    """(keyboard name, layout index) for every typed keyboard that has the requested layout."""
    target = target_layout(devices, code)
    plan = []
    for keyboard in typed_keyboards(devices):
        # Each keyboard has its own layout order, so match by code and variant, not by index.
        match = next((e for e in configured(keyboard)
                      if (e["code"], e["variant"]) == (target["code"], target["variant"])), None)
        if match:
            plan.append((keyboard["name"], str(match["index"])))
    if not plan:
        raise ValueError(f"{target['key']} is not configured on any keyboard; {ADD_HINT}")
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["status", "set", "toggle"])
    parser.add_argument("layout", nargs="?", help="layout code for set, e.g. us or de")
    args = parser.parse_args()
    devices = json.loads(hyprctl("devices", "-j"))
    if args.action != "status":
        if args.action == "set" and not args.layout:
            raise ValueError("set needs a layout code, e.g. us or de")
        target = target_layout(devices, args.layout) if args.action == "set" else next_layout(devices)
        for name, index in switch_plan(devices, target["key"]):
            response = hyprctl("switchxkblayout", name, index)
            if response.strip() != "ok":
                raise RuntimeError(response.strip() or "layout switch failed")
        devices = json.loads(hyprctl("devices", "-j"))
        if summarize(devices)["active"] != target["key"]:
            raise RuntimeError("keyboard did not confirm the requested layout")
    print(json.dumps(summarize(devices)))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"[omacorsair] {error}", file=sys.stderr)
        sys.exit(1)
