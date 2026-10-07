import contextlib
import errno
import importlib.util
import io
import json
from pathlib import Path
import sys
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

    def test_speed_change_keeps_animation_phase_continuous(self):
        origin = backend.restart_animation(100.0, 50)
        now = 103.137
        before = backend.animation_phase(origin, now)
        retimed = backend.retime_animation(origin, now, 20)
        self.assertAlmostEqual(backend.animation_phase(retimed, now), before)
        # From the change on, time runs at the new speed.
        self.assertAlmostEqual(backend.animation_phase(retimed, now + 2), before + 2 * backend.speed_factor(20))
        for mode in backend.ANIMATED_MODES:
            config = backend.validate_config({"mode": mode})
            frame_before = backend.render_frame(config, phase=before)
            frame_after = backend.render_frame(config, phase=backend.animation_phase(retimed, now + 1e-6))
            self.assertEqual(len(frame_before), 371)
            self.assertLessEqual(max(abs(a - b) for a, b in zip(frame_before, frame_after)), 1, mode)
        # The old behaviour (rescaling the whole elapsed time) jumped.
        config = backend.validate_config({"mode": "rainbowwave"})
        jumped = backend.render_frame(backend.validate_config({"mode": "rainbowwave", "speed": 20}), elapsed=now - 100.0)
        self.assertNotEqual(jumped, backend.render_frame(config, phase=before))

    def test_status_phase_matches_daemon_phase_and_old_status_files(self):
        config = backend.validate_config({"mode": "duotone", "speed": 20})
        origin = backend.retime_animation(backend.restart_animation(100.0, 50), 110.0, 20)
        device = {"mode": "duotone", "settings": config, **origin}
        for now in (110.0, 110.4, 250.0):
            self.assertAlmostEqual(backend.status_phase(device, config, now), backend.animation_phase(origin, now))
        # Old daemons wrote only `started`: phase 0 at that time, configured speed.
        old = {"mode": "duotone", "started": 100.0}
        self.assertAlmostEqual(backend.status_phase(old, config, 104.0), 4.0 * backend.speed_factor(20))
        # A mode the daemon has not picked up yet restarts at phase 0; bad values are ignored.
        self.assertEqual(backend.status_phase({"mode": "aurora", "started": 1.0}, config, 50.0), 0.0)
        junk = {"mode": "duotone", "started": "x", "phase0": float("nan"), "speed": 7}
        self.assertEqual(backend.status_phase(junk, config, 50.0), 0.0)
        self.assertEqual(backend.status_phase({"connected": False, "error": "x"}, config, 50.0), 0.0)

    def test_daemon_keeps_phase_across_speed_change_and_preview_agrees(self):
        configs = [backend.validate_config({"mode": "rainbowwave", "speed": speed}) for speed in (50, 50, 20, 20)]
        clock = [1000.0]
        times, frames, statuses = [], [], []
        keyboard = Mock()
        keyboard.firmware.return_value = "5.26.154"
        keyboard.apply.side_effect = lambda frame: (frames.append(frame), times.append(clock[0]))
        reads = iter(configs)

        def tick(_duration):
            clock[0] += 0.5
            if len(frames) == len(configs):
                backend.STOP = True

        with patch.object(backend, "STOP", False), \
                patch.object(backend, "read_config", side_effect=lambda: next(reads)), \
                patch.object(backend, "candidates", side_effect=lambda: iter([Path("/dev/hidraw2")])), \
                patch.object(backend, "Keyboard", return_value=keyboard), \
                patch.object(backend, "open_dial", side_effect=OSError("no dial")), \
                patch.object(backend, "atomic_json", side_effect=lambda path, value: statuses.append(value)), \
                patch.object(backend, "log"), patch.object(backend.signal, "signal"), \
                patch.object(backend.time, "monotonic", side_effect=lambda: clock[0]), \
                patch.object(backend.time, "sleep", side_effect=tick):
            backend.run_daemon()
        self.assertEqual(len(frames), 4)
        t0, change = times[0], times[2]
        for index, (when, frame) in enumerate(zip(times, frames)):
            phase = (when - t0) * backend.speed_factor(50) if when < change else \
                (change - t0) * backend.speed_factor(50) + (when - change) * backend.speed_factor(20)
            self.assertEqual(frame, backend.render_frame(configs[index], phase=phase), index)
        # Status is rewritten only when the origin or settings change, not per frame.
        self.assertEqual(len(statuses), 2)
        self.assertEqual((statuses[0]["started"], statuses[0]["phase0"], statuses[0]["speed"]), (t0, 0.0, 50))
        self.assertEqual((statuses[1]["started"], statuses[1]["speed"]), (change, 20))
        self.assertAlmostEqual(statuses[1]["phase0"], (change - t0) * backend.speed_factor(50))
        # The `status` command, run later by the panel, previews the device's current frame.
        with tempfile.TemporaryDirectory() as directory:
            config_path, status_path = Path(directory) / "config.json", Path(directory) / "status.json"
            config_path.write_text(json.dumps(configs[-1]))
            status_path.write_text(json.dumps(statuses[-1]))
            for now in (times[-1], times[-1] + 0.3):
                clock[0] = now
                out = io.StringIO()
                with patch.object(backend, "CONFIG_PATH", config_path), patch.object(backend, "STATUS_PATH", status_path), \
                        patch.object(backend.time, "monotonic", side_effect=lambda: clock[0]), \
                        patch.object(sys, "argv", ["omacorsair.py", "status"]), contextlib.redirect_stdout(out):
                    backend.main()
                preview = json.loads(out.getvalue())["preview"]
                device_frame = backend.render_frame(configs[-1], phase=backend.animation_phase(statuses[-1], now))
                expected = [["#" + device_frame[offset:offset + 3].hex() for offset in offsets] for offsets in backend.ROW_OFFSETS]
                self.assertEqual(preview, expected)

    def test_mode_change_restarts_animation(self):
        origin = backend.restart_animation(100.0, 50)
        restarted = backend.restart_animation(130.0, 50)
        self.assertEqual(backend.animation_phase(restarted, 130.0), 0.0)
        config = backend.validate_config({"mode": "aurora"})
        self.assertEqual(backend.render_frame(config, phase=backend.animation_phase(restarted, 130.0)),
                         backend.render_frame(config, elapsed=0))
        self.assertGreater(backend.animation_phase(origin, 130.0), 0)

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


class FakeKeyboard(backend.Keyboard):
    """The real Keyboard protocol logic over a scripted transport.

    `fail` maps the 1-based number of a transfer() call to the exception it raises.
    """

    def __init__(self, fail=None):
        self.software_mode = False
        self.fd = 99
        self.sent = []
        self.fail = fail or {}

    def firmware(self):
        return "5.26.154"

    def transfer(self, endpoint, payload=b""):
        self.sent.append(endpoint)
        if len(self.sent) in self.fail:
            raise self.fail[len(self.sent)]
        return b"\x00" + endpoint[:1] + b"\x00"

    def frames(self):
        """Number of complete color streams sent (first packet of each starts a frame)."""
        return sum(endpoint == b"\x06\x00" for endpoint in self.sent)

    def hardware_mode_sent(self):
        return self.sent.count(backend.HARDWARE_MODE)


def run_daemon_passes(modes, keyboards, dial=None, statuses=None):
    """Run the daemon loop for one iteration per entry of `modes`, one fake keyboard per connection.

    An entry may also be an exception instance, which read_config() then raises. Status dicts
    written by the daemon are appended to `statuses` when given.

    A fake clock advances 0.5 s per sleep, so animated looks produce a new frame every pass.
    Returns the Keyboard factory mock, the log mock and the os.close mock.
    """
    modes = [{"mode": mode} if isinstance(mode, str) else mode for mode in modes]
    configs = iter(modes)
    reads = []
    clock = [1000.0]

    def read_config():
        reads.append(1)
        if len(reads) >= len(modes):
            backend.STOP = True
        entry = next(configs)
        if isinstance(entry, Exception):
            raise entry
        return backend.validate_config(entry)

    def advance(_duration):
        clock[0] += 0.5

    factory = Mock(side_effect=list(keyboards))
    if dial is not None:
        dial.wait.side_effect = advance
    with patch.object(backend, "STOP", False), patch.object(backend, "read_config", side_effect=read_config), \
            patch.object(backend, "candidates", side_effect=lambda: iter([Path("/dev/hidraw2")])), \
            patch.object(backend, "Keyboard", factory), \
            patch.object(backend, "open_dial", **({"return_value": dial} if dial else {"side_effect": OSError("no dial")})), \
            patch.object(backend, "atomic_json", side_effect=lambda path, value: statuses is None or statuses.append(value)), \
            patch.object(backend, "log") as log, \
            patch.object(backend.signal, "signal"), patch.object(backend.os, "close") as close, \
            patch.object(backend.time, "monotonic", side_effect=lambda: clock[0]), \
            patch.object(backend.time, "sleep", side_effect=advance):
        backend.run_daemon()
    return factory, log, close


class ConnectionRecoveryTests(unittest.TestCase):
    def test_transient_timeout_keeps_connection_and_repaints_in_full(self):
        # Transfers: 1 SOFTWARE_MODE, 2 ACTIVATE_LEDS, 3-9 the first frame; #5 times out mid-frame.
        keyboard = FakeKeyboard(fail={5: TimeoutError("no matching reply to command 0700: []")})
        factory, log, close = run_daemon_passes(["aurora"] * 3, [keyboard])
        self.assertEqual(factory.call_count, 1)  # no reconnect
        self.assertEqual(keyboard.sent.count(backend.SOFTWARE_MODE), 1)
        self.assertEqual(keyboard.sent.count(backend.ACTIVATE_LEDS), 1)
        # Frame 1 stopped after 3 packets; frames 2 and 3 are complete (7 packets each).
        self.assertEqual(keyboard.frames(), 3)
        self.assertEqual(len([e for e in keyboard.sent if e in (b"\x06\x00", b"\x07\x00")]), 3 + 7 + 7)
        # HARDWARE_MODE only once, from the normal shutdown, never mid-run.
        self.assertEqual(keyboard.hardware_mode_sent(), 1)
        self.assertEqual(keyboard.sent[-1], backend.HARDWARE_MODE)
        close.assert_called_once_with(99)
        self.assertEqual([call.args[0] for call in log.call_args_list if "no matching reply" in call.args[0]],
                         ["no matching reply to command 0700: []"])

    def test_retry_sends_the_same_frame_when_nothing_changed(self):
        keyboard = FakeKeyboard(fail={3: TimeoutError("write timed out")})
        factory, _, _ = run_daemon_passes(["solid"] * 3, [keyboard])
        self.assertEqual(factory.call_count, 1)
        self.assertEqual(keyboard.frames(), 2)  # the failed attempt and one full retry; then nothing to resend
        self.assertEqual(len([e for e in keyboard.sent if e in (b"\x06\x00", b"\x07\x00")]), 1 + 7)

    def test_failed_activation_is_retried_without_repeating_software_mode(self):
        keyboard = FakeKeyboard(fail={2: TimeoutError("timed out")})  # SOFTWARE_MODE ok, ACTIVATE_LEDS fails
        factory, _, _ = run_daemon_passes(["solid"] * 2, [keyboard])
        self.assertEqual(factory.call_count, 1)
        self.assertEqual(keyboard.sent[:3], [backend.SOFTWARE_MODE, backend.ACTIVATE_LEDS, backend.ACTIVATE_LEDS])
        self.assertEqual(keyboard.sent.count(backend.SOFTWARE_MODE), 1)
        self.assertEqual(keyboard.frames(), 1)

    def test_device_gone_tears_down_and_reconnects(self):
        for number in (errno.ENODEV, errno.EIO, errno.EPIPE, errno.ENOENT):
            first = FakeKeyboard(fail={3: OSError(number, "gone")})
            second = FakeKeyboard()
            factory, _, close = run_daemon_passes(["solid"] * 2, [first, second])
            self.assertEqual(factory.call_count, 2, number)
            self.assertEqual(first.hardware_mode_sent(), 1, number)  # released at once, not after N failures
            self.assertEqual(second.frames(), 1, number)  # repainted after reconnecting
            self.assertEqual(close.call_count, 2, number)

    def test_consecutive_failures_tear_down_the_connection(self):
        timeout = TimeoutError("no matching reply")
        first = FakeKeyboard(fail={i: timeout for i in range(3, 60)})  # every transfer after the handshake
        second = FakeKeyboard()
        passes = backend.MAX_CONSECUTIVE_FAILURES + 1
        factory, _, _ = run_daemon_passes(["aurora"] * passes, [first, second])
        self.assertEqual(factory.call_count, 2)
        # Passes 1..N-1 keep the connection; HARDWARE_MODE appears only after the Nth failure.
        self.assertEqual(first.hardware_mode_sent(), 1)
        hardware_at = first.sent.index(backend.HARDWARE_MODE)
        self.assertEqual(first.sent[:hardware_at].count(b"\x06\x00"), backend.MAX_CONSECUTIVE_FAILURES)
        self.assertEqual(second.frames(), 1)

    def test_one_failure_less_than_the_limit_keeps_the_connection(self):
        timeout = TimeoutError("no matching reply")
        keyboard = FakeKeyboard(fail={i: timeout for i in range(3, 3 + backend.MAX_CONSECUTIVE_FAILURES - 1)})
        factory, _, _ = run_daemon_passes(["aurora"] * backend.MAX_CONSECUTIVE_FAILURES, [keyboard])
        self.assertEqual(factory.call_count, 1)
        self.assertEqual(keyboard.hardware_mode_sent(), 1)  # shutdown only
        self.assertEqual(keyboard.frames(), backend.MAX_CONSECUTIVE_FAILURES)

    def test_non_consecutive_failures_do_not_accumulate(self):
        keyboard = FakeKeyboard()
        failing_passes = {1, 2, 4, 5}
        original = keyboard.transfer
        state = {"pass": 0}

        def transfer(endpoint, payload=b""):
            if endpoint == b"\x06\x00":
                state["pass"] += 1
                if state["pass"] in failing_passes:
                    keyboard.sent.append(endpoint)
                    raise TimeoutError("no matching reply")
            return original(endpoint, payload)

        keyboard.transfer = transfer
        factory, _, _ = run_daemon_passes(["aurora"] * 6, [keyboard])
        self.assertEqual(state["pass"], 6)
        self.assertEqual(factory.call_count, 1)
        self.assertEqual(keyboard.hardware_mode_sent(), 1)  # shutdown only

    def test_handshake_failure_releases_the_candidate_and_retries(self):
        class NoFirmware(FakeKeyboard):
            def firmware(self):
                raise TimeoutError("no matching reply to command 0213: []")

        first, second = NoFirmware(), FakeKeyboard()
        factory, _, close = run_daemon_passes(["solid"] * 2, [first, second])
        self.assertEqual(factory.call_count, 2)
        self.assertEqual(first.sent, [])  # never entered software mode, so nothing to undo
        self.assertEqual(second.frames(), 1)
        self.assertEqual(close.call_count, 2)  # the failed candidate's fd, then the second keyboard at shutdown

    def test_hardware_mode_close_failure_does_not_close_twice(self):
        keyboard = FakeKeyboard()
        original = keyboard.transfer

        def transfer(endpoint, payload=b""):
            if endpoint == backend.HARDWARE_MODE:
                keyboard.sent.append(endpoint)
                raise OSError(errno.ENODEV, "gone")
            return original(endpoint, payload)

        keyboard.transfer = transfer
        _, _, close = run_daemon_passes(["solid", "hardware", "hardware"], [keyboard])
        self.assertEqual(keyboard.hardware_mode_sent(), 1)
        close.assert_called_once_with(99)

    def test_dial_is_closed_with_the_keyboard(self):
        # Transfers 1-9 are pass 1 (handshake and frame); #10 is the first packet of pass 2.
        first = FakeKeyboard(fail={10: OSError(errno.ENODEV, "gone")})
        dial = Mock()
        run_daemon_passes(["aurora"] * 3, [first, FakeKeyboard()], dial=dial)
        # Opened with the first keyboard, closed on its unplug, reopened for the next one, closed at shutdown.
        self.assertEqual(dial.close.call_count, 2)

    def test_dial_stays_open_through_a_transient_error(self):
        keyboard = FakeKeyboard(fail={10: TimeoutError("no matching reply")})
        dial = Mock()
        factory, _, _ = run_daemon_passes(["aurora"] * 3, [keyboard], dial=dial)
        self.assertEqual(factory.call_count, 1)
        dial.close.assert_called_once()  # shutdown only

    def test_error_status_keeps_mode_settings_and_dial(self):
        statuses = []
        dial = Mock()
        keyboard = FakeKeyboard(fail={10: TimeoutError("no matching reply to command 0600: []")})
        run_daemon_passes([{"mode": "aurora", "speed": 30}] * 3, [keyboard], dial=dial, statuses=statuses)
        self.assertEqual(len(statuses), 3)
        good, error, recovered = statuses
        self.assertEqual((good["connected"], good["applied"], good["error"]), (True, True, ""))
        self.assertEqual(error["connected"], False)
        self.assertEqual(error["applied"], False)
        self.assertEqual(error["error"], "no matching reply to command 0600: []")
        self.assertEqual(error["mode"], "aurora")
        self.assertEqual(error["settings"], backend.validate_config({"mode": "aurora", "speed": 30}))
        self.assertEqual(error["dial"], True)  # a transient error leaves the dial open
        # The animation clock is kept too, so the panel preview keeps matching the device.
        self.assertEqual({key: error[key] for key in ("started", "phase0", "speed")},
                         {key: good[key] for key in ("started", "phase0", "speed")})
        self.assertEqual((recovered["connected"], recovered["applied"], recovered["error"]), (True, True, ""))

    def test_error_status_after_teardown_reports_closed_dial(self):
        statuses = []
        first = FakeKeyboard(fail={10: OSError(errno.ENODEV, "No such device")})
        run_daemon_passes(["aurora"] * 3, [first, FakeKeyboard()], dial=Mock(), statuses=statuses)
        error = next(status for status in statuses if status["error"])
        self.assertEqual((error["mode"], error["dial"], error["connected"]), ("aurora", False, False))

    def test_error_before_any_config_has_no_mode_or_settings(self):
        statuses = []
        run_daemon_passes([ValueError("bad config"), "solid"], [FakeKeyboard()], statuses=statuses)
        self.assertEqual(statuses[0], {"connected": False, "applied": False, "error": "bad config", "dial": False})
        self.assertEqual(statuses[1]["mode"], "solid")

    def test_config_error_keeps_last_known_mode_and_settings(self):
        statuses = []
        run_daemon_passes(["gaming", ValueError("bad config"), "gaming"], [FakeKeyboard()], statuses=statuses)
        error = statuses[1]
        self.assertEqual((error["mode"], error["error"], error["connected"]), ("gaming", "bad config", False))
        self.assertEqual(error["settings"], backend.validate_config({"mode": "gaming"}))

    def test_device_gone_classification(self):
        for number in (errno.ENODEV, errno.EIO, errno.EPIPE, errno.ENOENT, errno.ENXIO):
            self.assertTrue(backend.device_gone(OSError(number, "x")), number)
        for error in (TimeoutError("x"), OSError("short HID write"), OSError(errno.EAGAIN, "x"), ValueError("x")):
            self.assertFalse(backend.device_gone(error), error)


if __name__ == "__main__":
    unittest.main()
