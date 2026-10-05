import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("layouts", Path(__file__).resolve().parents[1] / "bin/layouts.py")
layouts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layouts)


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
        self.assertEqual(status["count"], 2)
        self.assertEqual(status["available"], ["us", "de"])

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


if __name__ == "__main__":
    unittest.main()
