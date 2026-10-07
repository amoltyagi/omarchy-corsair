import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("layouts", Path(__file__).resolve().parents[1] / "bin/layouts.py")
layouts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layouts)


def keyboard(layout, active=0, keymap="", variant="", name="corsair-corsair-k65-plus-wireless-keyboard"):
    result = {"name": name, "layout": layout, "variant": variant, "active_layout_index": active, "active_keymap": keymap}
    return result


def devices_with(*keyboards):
    return {"keyboards": list(keyboards)}


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.devices = {"keyboards": [
            {"name": "power-button", "main": True, "layout": "us,de", "active_layout_index": 1, "active_keymap": "German"},
            {"name": "receiver-keyboard", "layout": "de,us", "active_layout_index": 0, "active_keymap": "German"},
            {"name": "corsair-corsair-k65-plus-wireless-keyboard", "layout": "us,de", "active_layout_index": 0, "active_keymap": "English (US)"},
            {"name": "headset-consumer-control", "layout": "us,de"},
        ]}

    def test_status_prefers_corsair_and_ignores_pseudo_keyboards(self):
        status = layouts.summarize(self.devices)
        self.assertEqual(status["active"], "us")
        self.assertEqual(status["label"], "EN")
        self.assertEqual(status["name"], "English (US)")
        self.assertEqual(status["count"], 2)
        self.assertEqual(status["available"], ["us", "de"])
        self.assertEqual(status["layouts"], [{"code": "us", "label": "EN", "name": "English (US)"},
                                             {"code": "de", "label": "DE", "name": "German"}])

    def test_each_keyboard_uses_its_own_layout_index(self):
        self.assertEqual(layouts.switch_plan(self.devices, "de"), [
            ("receiver-keyboard", "0"), ("corsair-corsair-k65-plus-wireless-keyboard", "1")])
        self.assertEqual(layouts.switch_plan(self.devices, "us"), [
            ("receiver-keyboard", "1"), ("corsair-corsair-k65-plus-wireless-keyboard", "0")])

    def test_missing_layout_and_invalid_target_are_rejected(self):
        with self.assertRaises(ValueError):
            layouts.switch_plan(self.devices, "fr")
        with self.assertRaises(ValueError):
            layouts.switch_plan({"keyboards": [{"name": "keyboard", "layout": "us"}]}, "de")

    def test_name_fallback_for_older_hyprland(self):
        self.assertEqual(layouts.keyboard_code({"layout": "us,de", "active_keymap": "German"}), "de")
        self.assertEqual(layouts.keyboard_code({"layout": "us,de", "active_keymap": "English (US)"}), "us")
        self.assertEqual(layouts.keyboard_code({"layout": "us,gb", "active_keymap": "English (UK)"}), "gb")
        self.assertEqual(layouts.keyboard_code({"layout": "us,fr", "active_keymap": "Klingon"}), "us")
        self.assertEqual(layouts.keyboard_code({}), "")

    def test_no_keyboard(self):
        status = layouts.summarize({"keyboards": [{"name": "power-button", "layout": "us"}]})
        self.assertEqual((status["active"], status["label"], status["available"], status["layouts"]), ("", "", [], []))
        self.assertEqual(status["name"], "No keyboard detected")
        with self.assertRaises(ValueError):
            layouts.switch_plan({"keyboards": []}, "us")


class ConfiguredLayoutTests(unittest.TestCase):
    def test_one_layout(self):
        devices = devices_with(keyboard("us", keymap="English (US)"))
        status = layouts.summarize(devices)
        self.assertEqual((status["available"], status["active"], status["label"]), (["us"], "us", "EN"))
        self.assertEqual(len(status["layouts"]), 1)
        self.assertEqual(layouts.switch_plan(devices, "us"), [("corsair-corsair-k65-plus-wireless-keyboard", "0")])
        with self.assertRaisesRegex(ValueError, "only one keyboard layout.*kb_layout"):
            layouts.next_layout(devices)

    def test_two_layouts_toggle_both_ways(self):
        for active, expected in ((0, "de"), (1, "us")):
            devices = devices_with(keyboard("us,de", active))
            self.assertEqual(layouts.next_layout(devices)["key"], expected)

    def test_three_layouts_in_kb_layout_order_and_cycle(self):
        devices = devices_with(keyboard("us,gb,fr", 0, "English (US)"))
        status = layouts.summarize(devices)
        self.assertEqual(status["available"], ["us", "gb", "fr"])
        self.assertEqual([l["label"] for l in status["layouts"]], ["EN", "UK", "FR"])
        self.assertEqual([l["name"] for l in status["layouts"]], ["English (US)", "English (UK)", "French"])
        order = []
        for active in (0, 1, 2):
            order.append(layouts.next_layout(devices_with(keyboard("us,gb,fr", active)))["key"])
        self.assertEqual(order, ["gb", "fr", "us"])  # wraps around

    def test_labels_and_names(self):
        devices = devices_with(keyboard("us,gb,de,fr,dk,xx", 3, "French"))
        status = layouts.summarize(devices)
        labels = {l["code"]: l["label"] for l in status["layouts"]}
        self.assertEqual(labels, {"us": "EN", "gb": "UK", "de": "DE", "fr": "FR", "dk": "DK", "xx": "XX"})
        names = {l["code"]: l["name"] for l in status["layouts"]}
        self.assertEqual(names["fr"], "French")  # Hyprland's name for the active layout
        self.assertEqual(names["de"], "German")  # built-in map
        self.assertEqual(names["xx"], "xx")  # unknown code: the code itself
        self.assertEqual((status["label"], status["name"]), ("FR", "French"))

    def test_active_layout_uses_hyprlands_keymap_name(self):
        devices = devices_with(keyboard("us,de", 1, "German (no dead keys)", variant=",nodeadkeys"))
        status = layouts.summarize(devices)
        self.assertEqual(status["name"], "German (no dead keys)")
        self.assertEqual(status["layouts"][0]["name"], "English (US)")

    def test_set_accepts_any_configured_layout_and_rejects_others(self):
        devices = devices_with(keyboard("us,gb,fr", 0))
        for code, index in (("us", "0"), ("gb", "1"), ("fr", "2"), ("FR", "2")):
            self.assertEqual(layouts.switch_plan(devices, code), [("corsair-corsair-k65-plus-wireless-keyboard", index)])
        for code in ("de", "", "us,gb", "xx", None):
            with self.assertRaises(ValueError):
                layouts.switch_plan(devices, code)
        with self.assertRaisesRegex(ValueError, "choose one of: us, gb, fr"):
            layouts.switch_plan(devices, "de")

    def test_variants_are_positional_and_shown_in_built_in_names(self):
        devices = devices_with(keyboard("us,de", 0, "English (US)", variant=",nodeadkeys"))
        status = layouts.summarize(devices)
        self.assertEqual(status["available"], ["us", "de"])  # variants do not change the codes
        self.assertEqual(status["layouts"][1]["name"], "German (nodeadkeys)")
        self.assertEqual(layouts.switch_plan(devices, "de"), [("corsair-corsair-k65-plus-wireless-keyboard", "1")])
        # A short kb_variant leaves the remaining layouts without a variant.
        short = devices_with(keyboard("de,us,fr", 0, variant="nodeadkeys"))
        self.assertEqual([l["name"] for l in layouts.summarize(short)["layouts"]][1:], ["English (US)", "French"])

    def test_same_layout_twice_with_different_variants(self):
        devices = devices_with(keyboard("us,us,de", 1, "English (US, intl., with dead keys)", variant=",intl,"))
        status = layouts.summarize(devices)
        self.assertEqual(status["available"], ["us", "us(intl)", "de"])
        self.assertEqual(status["active"], "us(intl)")
        self.assertEqual([l["label"] for l in status["layouts"]], ["EN", "EN-INTL", "DE"])
        self.assertEqual(layouts.switch_plan(devices, "us(intl)"), [("corsair-corsair-k65-plus-wireless-keyboard", "1")])
        self.assertEqual(layouts.switch_plan(devices, "us"), [("corsair-corsair-k65-plus-wireless-keyboard", "0")])
        self.assertEqual(layouts.next_layout(devices)["key"], "de")

    def test_identical_repeated_entries_collapse(self):
        devices = devices_with(keyboard("us,us,de", 1))
        status = layouts.summarize(devices)
        self.assertEqual(status["available"], ["us", "de"])
        self.assertEqual(status["active"], "us")  # slot 1 is the same layout as slot 0

    def test_variant_matching_across_keyboards_with_different_order(self):
        devices = devices_with(
            keyboard("us,us,de", 0, variant=",intl,"),
            keyboard("de,us", 0, name="receiver-keyboard", variant=",intl"),
            keyboard("us", 0, name="plain-keyboard"))
        self.assertEqual(layouts.switch_plan(devices, "us(intl)"), [
            ("corsair-corsair-k65-plus-wireless-keyboard", "1"), ("receiver-keyboard", "1")])
        self.assertEqual(layouts.switch_plan(devices, "de"), [
            ("corsair-corsair-k65-plus-wireless-keyboard", "2"), ("receiver-keyboard", "0")])

    def test_empty_slots_keep_their_indexes(self):
        devices = devices_with(keyboard("us,,de", 2))
        status = layouts.summarize(devices)
        self.assertEqual((status["available"], status["active"]), (["us", "de"], "de"))
        self.assertEqual(layouts.switch_plan(devices, "de")[0][1], "2")


class FakeHyprland:
    """A tiny hyprctl: switchxkblayout moves the active index of the named keyboard."""

    def __init__(self, devices, confirm=True):
        self.devices = copy.deepcopy(devices)
        self.confirm = confirm
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        if args == ("devices", "-j"):
            return json.dumps(self.devices)
        _, name, index = args
        if self.confirm:
            next(k for k in self.devices["keyboards"] if k["name"] == name)["active_layout_index"] = int(index)
        return "ok\n"


class CommandTests(unittest.TestCase):
    def run_main(self, hypr, *argv):
        out = io.StringIO()
        with patch.object(layouts, "hyprctl", hypr), patch.object(sys, "argv", ["layouts.py", *argv]), contextlib.redirect_stdout(out):
            layouts.main()
        return json.loads(out.getvalue())

    def test_toggle_cycles_through_three_layouts_on_every_keyboard(self):
        hypr = FakeHyprland(devices_with(keyboard("us,gb,fr", 0), keyboard("fr,us,gb", 1, name="receiver-keyboard")))
        seen = [self.run_main(hypr, "toggle")["active"] for _ in range(4)]
        self.assertEqual(seen, ["gb", "fr", "us", "gb"])
        by_name = {k["name"]: k["active_layout_index"] for k in hypr.devices["keyboards"]}
        self.assertEqual(by_name["receiver-keyboard"], 2)  # gb in fr,us,gb

    def test_set_switches_and_reports_the_new_status(self):
        hypr = FakeHyprland(devices_with(keyboard("us,de", 0)))
        status = self.run_main(hypr, "set", "de")
        self.assertEqual((status["active"], status["label"]), ("de", "DE"))
        self.assertIn(("switchxkblayout", "corsair-corsair-k65-plus-wireless-keyboard", "1"), hypr.calls)

    def test_status_does_not_switch(self):
        hypr = FakeHyprland(devices_with(keyboard("us,de", 0)))
        self.run_main(hypr, "status")
        self.assertEqual(hypr.calls, [("devices", "-j")])

    def test_errors(self):
        hypr = FakeHyprland(devices_with(keyboard("us", 0)))
        for argv in (("toggle",), ("set", "de"), ("set",)):
            with self.assertRaises(ValueError):
                self.run_main(hypr, *argv)
        self.assertEqual([call for call in hypr.calls if call[0] == "switchxkblayout"], [])
        stuck = FakeHyprland(devices_with(keyboard("us,de", 0)), confirm=False)
        with self.assertRaisesRegex(RuntimeError, "did not confirm"):
            self.run_main(stuck, "set", "de")


if __name__ == "__main__":
    unittest.main()
