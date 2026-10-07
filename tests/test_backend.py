import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location("omacorsair", Path(__file__).resolve().parents[1] / "bin/omacorsair.py")
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


class ProtocolTests(unittest.TestCase):
    def test_reports_match_vendor_protocol(self):
        packet = backend.report(backend.SOFTWARE_MODE)
        self.assertEqual(len(packet), 65)
        self.assertEqual(packet[:6], bytes.fromhex("00 08 01 03 00 02"))
        with self.assertRaises(ValueError):
            backend.report(b"\x06\x00", bytes(62))

    def test_color_stream_headers_and_reserved_slot(self):
        packets = list(backend.color_packets("abcdef"))
        self.assertEqual(len(packets), 7)
        self.assertEqual(packets[0][0], b"\x06\x00")
        self.assertTrue(all(endpoint == b"\x07\x00" for endpoint, _ in packets[1:]))
        stream = b"".join(data for _, data in packets)
        self.assertEqual(len(stream), 377)
        self.assertEqual(stream[:6], bytes.fromhex("75 01 00 00 12 00"))
        self.assertEqual(stream[6:12], bytes.fromhex("ab cd ef 00 00 00"))
        self.assertEqual(stream[12:-2], bytes.fromhex("abcdef") * 121)
        self.assertTrue(all(len(backend.report(endpoint, data)) == 65 for endpoint, data in packets))

    def test_software_mode_initialized_only_once(self):
        keyboard = backend.Keyboard.__new__(backend.Keyboard)
        keyboard.software_mode = False
        calls = []
        keyboard.transfer = lambda endpoint, payload=b"": calls.append((endpoint, payload))
        with patch.object(backend.time, "sleep"):
            keyboard.apply("123456")
            keyboard.apply("654321")
        self.assertEqual(calls[0][0], backend.SOFTWARE_MODE)
        self.assertEqual(calls[1][0], backend.ACTIVATE_LEDS)
        self.assertEqual(sum(endpoint == backend.SOFTWARE_MODE for endpoint, _ in calls), 1)
        self.assertEqual(len(calls), 16)

    def test_hardware_mode_restored_on_close(self):
        keyboard = backend.Keyboard.__new__(backend.Keyboard)
        keyboard.software_mode = True
        keyboard.fd = 123
        with patch.object(keyboard, "transfer", create=True) as transfer, patch.object(backend.os, "close") as close:
            keyboard.close()
        transfer.assert_called_once_with(backend.HARDWARE_MODE)
        close.assert_called_once_with(123)

    def test_reads_current_theme_after_symlink_switch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / "first", root / "second"
            first.mkdir()
            second.mkdir()
            (first / "keyboard.rgb").write_text("#123456\n")
            (second / "keyboard.rgb").write_text("ABCDEF\n")
            current = root / "current"
            current.symlink_to(first)
            self.assertEqual(backend.read_color(current / "keyboard.rgb"), "123456")
            current.unlink()
            current.symlink_to(second)
            self.assertEqual(backend.read_color(current / "keyboard.rgb"), "abcdef")

    def test_invalid_theme_files_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "keyboard.rgb"
            self.assertIsNone(backend.read_color(path))
            for text in ["#12345", "abcxyz", "123456\n654321", "a" * 65]:
                path.write_text(text)
                with self.assertRaises(ValueError):
                    backend.read_color(path)

    def test_grays_are_preserved_and_jade_is_vivid(self):
        self.assertEqual(backend.vivid("888888"), "888888")
        self.assertEqual(backend.vivid("000000"), "000000")
        self.assertEqual(backend.vivid("7fbbb3"), "19ff41")

    def test_config_validation_and_normalization(self):
        config = backend.validate_config({"mode": "gaming", "color": "#ABCDEF", "brightness": 25})
        self.assertEqual(config["color"], "abcdef")
        for value in [{"mode": "unknown"}, {"color": "garbage"}, {"brightness": -1},
                      {"brightness": 101}, {"brightness": True}, {"vivid": "true"}, {"unknown": 1}]:
            with self.assertRaises(ValueError):
                backend.validate_config(value)

    def test_manual_color_does_not_follow_theme(self):
        config = backend.validate_config({"mode": "solid", "color": "abcdef"})
        self.assertEqual(backend.render_frame(config, "123456"), backend.render_frame(config, "654321"))
        self.assertEqual(backend.render_frame(config)[:3], bytes.fromhex("abcdef"))

    def test_gaming_offsets_and_brightness(self):
        config = backend.validate_config({"mode": "gaming", "color": "0000ff", "accent": "ff0000", "brightness": 50})
        frame = backend.render_frame(config)
        self.assertEqual(frame[78:81], b"\x80\x00\x00")  # W
        self.assertEqual(frame[246:249], b"\x80\x00\x00")  # Up arrow
        self.assertEqual(frame[24:27], b"\x00\x00\x80")  # E, not highlighted
        self.assertEqual(frame[3:6], bytes(3))

    def test_row_palettes_follow_physical_key_rows(self):
        config = backend.validate_config({"mode": "rainbow"})
        frame = backend.render_frame(config)
        self.assertEqual(frame[123:126], bytes.fromhex("ff0000"))  # Escape
        self.assertEqual(frame[78:81], bytes.fromhex("ffff00"))  # W
        self.assertEqual(frame[12:15], bytes.fromhex("00ff00"))  # A
        self.assertEqual(frame[240:243], bytes.fromhex("aa00ff"))  # Left arrow
        for mode in backend.MODES:
            config = backend.validate_config({"mode": mode})
            frame = backend.render_frame(config, "7fbbb3")
            if mode == "hardware":
                self.assertIsNone(frame)
            else:
                self.assertEqual(len(frame), 371)
                self.assertEqual(len(list(backend.color_packets(frame))), 7)

    def test_theme_adjustment_off_and_missing_theme(self):
        config = backend.validate_config({"mode": "theme"})
        self.assertEqual(backend.render_frame(config, "7fbbb3")[:3], bytes.fromhex("19ff41"))
        self.assertEqual(backend.render_frame(config, "7fbbb3", raw=True)[:3], bytes.fromhex("7fbbb3"))
        self.assertIsNone(backend.render_frame(config))
        self.assertEqual(backend.render_frame(backend.validate_config({"mode": "off"})), bytes(371))

    def test_config_atomic_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "subfolder" / "settings.json"
            config = backend.validate_config({"mode": "sunset", "brightness": 75})
            backend.atomic_json(path, config)
            self.assertEqual(backend.read_json(path, {}), config)
            self.assertEqual(list(path.parent.glob(".omacorsair-*")), [])

    def test_catalog_and_animation_frames(self):
        self.assertEqual(len(backend.CATALOG), 28)
        self.assertEqual(len(set(backend.MODES)), 28)
        self.assertEqual(len(backend.ANIMATED_MODES), 9)
        for mode in backend.ANIMATED_MODES:
            config = backend.validate_config({"mode": mode})
            first = backend.render_frame(config, elapsed=0)
            later = backend.render_frame(config, elapsed=2)
            self.assertNotEqual(first, later, mode)
            for elapsed in (0, 0.1, 1, 2, 30, 10000):
                frame = backend.render_frame(config, elapsed=elapsed)
                self.assertEqual(len(frame), 371)
                self.assertEqual(frame[3:6], bytes(3))
                self.assertEqual(frame[-2:], bytes(2))
                self.assertTrue(all(0 <= channel <= 255 for channel in frame))

    def test_animation_speed_and_zero_brightness(self):
        normal = backend.validate_config({"mode": "duotone", "speed": 50})
        slow = backend.validate_config({"mode": "duotone", "speed": 20})
        self.assertEqual(backend.render_frame(normal, elapsed=1), backend.render_frame(slow, elapsed=1 / 0.52))
        self.assertNotEqual(backend.render_frame(normal, elapsed=1), backend.render_frame(slow, elapsed=1))
        for mode in backend.ANIMATED_MODES:
            dark = backend.validate_config({"mode": mode, "brightness": 0})
            self.assertEqual(backend.render_frame(dark, elapsed=3), bytes(371))
        for speed in (0, 9, 101, True, "50"):
            with self.assertRaises(ValueError):
                backend.validate_config({"speed": speed})

    def test_animated_daemon_does_not_log_or_write_status_per_frame(self):
        config = backend.validate_config({"mode": "aurora"})
        keyboard = Mock()
        keyboard.firmware.return_value = "5.26.154"
        sleeps = []
        clock = iter(1000 + i * 0.1 for i in range(100))

        def tick(duration):
            sleeps.append(duration)
            if len(sleeps) == 3:
                backend.STOP = True

        with patch.object(backend, "STOP", False), patch.object(backend, "read_config", return_value=config), \
                patch.object(backend, "candidates", side_effect=lambda: iter([Path("/dev/hidraw2")])), \
                patch.object(backend, "Keyboard", return_value=keyboard), \
                patch.object(backend, "open_dial", side_effect=OSError("no dial")), \
                patch.object(backend, "atomic_json") as write_status, patch.object(backend, "log") as log, \
                patch.object(backend.signal, "signal"), patch.object(backend.time, "monotonic", side_effect=lambda: next(clock)), \
                patch.object(backend.time, "sleep", side_effect=tick):
            backend.run_daemon()
        self.assertEqual(keyboard.apply.call_count, 3)
        self.assertEqual(log.call_count, 3)  # connect + selected mode + dial unavailable, not every frame
        self.assertEqual(write_status.call_count, 1)
        self.assertEqual(sleeps, [0.08] * 3)
        keyboard.close.assert_called_once()

    def test_daemon_switches_manual_modes_and_restores_hardware(self):
        configs = [backend.validate_config({"mode": mode}) for mode in ("solid", "gaming", "hardware")]
        keyboard = Mock()
        keyboard.firmware.return_value = "5.26.154"
        sleeps = []

        def tick(_duration):
            sleeps.append(1)
            if len(sleeps) == 3:
                backend.STOP = True

        with patch.object(backend, "STOP", False), patch.object(backend, "read_config", side_effect=configs), \
                patch.object(backend, "read_color") as read_theme, \
                patch.object(backend, "candidates", side_effect=lambda: iter([Path("/dev/hidraw2")])), \
                patch.object(backend, "Keyboard", return_value=keyboard), \
                patch.object(backend, "open_dial", side_effect=OSError("no dial")), \
                patch.object(backend, "atomic_json"), patch.object(backend, "log"), \
                patch.object(backend.signal, "signal"), patch.object(backend.time, "sleep", side_effect=tick):
            backend.run_daemon()
        read_theme.assert_not_called()
        self.assertEqual([call.args[0] for call in keyboard.apply.call_args_list],
                         [backend.render_frame(configs[0]), backend.render_frame(configs[1])])
        keyboard.close.assert_called_once()

    def test_dial_reports_map_to_volume_actions(self):
        turn = lambda value: bytes([0, 0x05, 0, 0, value]) + bytes(59)
        press = lambda down: bytes([0, 0x02]) + bytes(17) + bytes([0x02 if down else 0]) + bytes(44)
        self.assertEqual(backend.dial_action(turn(1), False), ("raise", False))
        self.assertEqual(backend.dial_action(turn(255), False), ("lower", False))
        self.assertEqual(backend.dial_action(press(True), False), ("mute-toggle", True))
        self.assertEqual(backend.dial_action(press(True), True), (None, True))  # held, no repeat
        self.assertEqual(backend.dial_action(press(False), True), (None, False))
        self.assertEqual(backend.dial_action(bytes([0, 0x01, 0x0f]) + bytes(61), False), (None, False))

    def test_dial_coalesces_steps_while_command_runs(self):
        dial = backend.Dial.__new__(backend.Dial)
        dial.pressed, dial.pending, dial.child = False, 0, None
        commands = []
        child = Mock()
        child.poll.return_value = None
        dial.run = lambda action: (commands.append(action), setattr(dial, "child", child))
        turn = lambda value: bytes([0, 0x05, 0, 0, value]) + bytes(59)
        for value in (1, 1, 1, 255):
            dial.handle(turn(value))
        self.assertEqual(commands, ["+5"])
        child.poll.return_value = 0
        dial.flush()
        self.assertEqual(commands, ["+5", "+5"])

    def test_volume_command_falls_back_to_wpctl(self):
        with patch.object(backend.shutil, "which", return_value=None):
            self.assertEqual(backend.volume_command("-10")[-1], "10%-")
            self.assertIn("toggle", backend.volume_command("mute-toggle"))

    def test_discovery_excludes_input_interface_and_other_products(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, product, interface in [(0, "2B11", "00"), (1, "2B11", "01"), (2, "2B10", "01")]:
                device = root / f"usb{index}" / "hid"
                device.mkdir(parents=True)
                (device / "uevent").write_text(f"HID_ID=0003:00001B1C:0000{product}\n")
                (device.parent / "bInterfaceNumber").write_text(interface)
                node = root / f"hidraw{index}"
                node.mkdir()
                (node / "device").symlink_to(device)
            with patch.object(backend, "HID_ROOT", root):
                self.assertEqual(list(backend.candidates()), [Path("/dev/hidraw1")])


if __name__ == "__main__":
    unittest.main()
