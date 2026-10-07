# Architecture

Omacorsair is an Omarchy 4 shell plugin (Quickshell/QML) plus two stdlib-only Python helpers. Nothing runs as root; the udev rule grants the active desktop user access to the HID nodes.

## Components

| File | Role |
|---|---|
| `manifest.json` | Plugin metadata. Entry points: `service` = `Service.qml`, `barWidget` = `Panel.qml`. |
| `Service.qml` | Background service. Starts and supervises the lighting daemon. |
| `Panel.qml` | Bar button and popup. Never talks to the keyboard; it only runs helper commands. |
| `bin/omacorsair.py` | Lighting backend, volume-dial listener, config/status handling, CLI. |
| `bin/layouts.py` | EN/DE layout status and switching through `hyprctl`. Independent of the keyboard hardware. |
| `70-omacorsair.rules` | udev rule: `uaccess` on hidraw interfaces 01 and 02 of `1b1c:2b11`. |
| `install.sh`, `install-device-access.sh` | Dev install (symlink + enable) and udev rule install. |

## Data flow

```
Panel.qml ──"omacorsair.py set {json}"──▶ ~/.config/omarchy/omacorsair.json
                                                  │  (re-read every loop)
theme/keyboard.rgb ───────────────────────────────┤
                                                  ▼
Service.qml ──spawns──▶ omacorsair.py daemon ──HID reports──▶ keyboard (iface 01)
                              │      ▲
                              │      └──read-only── dial events (iface 02) ──▶ omarchy-audio-output-volume
                              ▼
          ~/.local/state/omarchy/omacorsair/status.json
                              │
Panel.qml ──"omacorsair.py status"──▶ config + status.json + preview + CATALOG (JSON on stdout)
```

1. **Panel to config.** A click or IPC call runs `omacorsair.py set '<json>'`. It merges the update into the current config, validates it (`validate_config`), and writes it atomically (`atomic_json`: temp file in the same directory, then `os.replace`). Concurrent updates in the panel are merged in `pendingUpdate` and sent after the running one finishes.
2. **Config to daemon.** There is no signal or socket. The daemon calls `read_config()` on every loop iteration and renders a 371-byte frame with `render_frame()`. In `theme` mode it also reads `~/.local/state/omarchy/current/theme/keyboard.rgb` (`read_color`, at most 64 bytes, one `RRGGBB` value).
3. **Daemon to device.** If the frame differs from the last applied one, `Keyboard.apply()` sends it (see `PROTOCOL.md`). Animated looks produce a new frame each iteration.
4. **Daemon to panel.** The daemon writes `status.json` only when the status dict changes. Animation frames do not change it (`started` is fixed per mode), so there is no per-frame disk write or log line.
5. **Panel reads state.** `omacorsair.py status` prints one JSON object: `config`, `device` (the contents of `status.json`), `catalog` (`CATALOG`) and `preview` (rows of `#rrggbb`, rendered in the status process from the same `render_frame()` with elapsed time since `started`).
6. **Layouts.** `Panel.qml` runs `bin/layouts.py status|set|toggle`, which calls `hyprctl devices -j` and `hyprctl switchxkblayout`. It shares no state with the lighting daemon.

`CATALOG` in `omacorsair.py` is the single source of looks: the daemon (`MODES`, `ANIMATED_MODES`), the CLI validation, and the popup gallery (via `status`) all derive from it. Only the quick-color list is defined in `Panel.qml` (`colors`).

## Process model and restart behaviour

- `Service.qml` runs `/usr/bin/python3 -I bin/omacorsair.py daemon`, plus `--raw` when the plugin setting `rawColor` is `true` in `shell.json`. The process starts as soon as the service loads.
- The daemon's stderr is forwarded line by line to the shell's console/journal (each line cut to 1024 characters). Daemon log lines start with `[omacorsair]`.
- If the daemon exits while the service is not stopping, the service logs `helper exited (<code>), retrying in 5 seconds` and restarts it after 5 s (`retry` timer). This applies to any exit code, including a clean exit after `SIGTERM`.
- When the service is destroyed (plugin disabled or shell stops), it sets `stopping`, cancels the retry, and sends `SIGTERM`.
- The daemon handles `SIGTERM` and `SIGINT` by setting `STOP`. The loop ends, and `Keyboard.close()` sends the hardware-mode command before closing the device, so the keyboard returns to its built-in lighting.
- Device or I/O errors (`OSError`, `ValueError`, `UnicodeError`) inside a loop iteration do not end the process. The daemon closes the dial and keyboard, writes an error status, logs the message once per distinct text, and retries on the next iteration (re-discovering the device). This handles unplug/replug.
- Each `Panel.qml` query (`status`, `set`, layout calls) is a short-lived `python3 -I` process.
- To restart the daemon after editing code: `pkill -TERM -f '[o]macorsair.py daemon'`. The service respawns it after 5 s.
- `Keyboard` takes an exclusive non-blocking `flock` on interface 01. A second daemon (or another RGB tool holding that lock) fails with an error until the first exits.

## File locations

| Path | Purpose |
|---|---|
| `~/.config/omarchy/omacorsair.json` | Saved settings (`mode`, `color`, `accent`, `brightness`, `vivid`, `speed`). |
| `~/.local/state/omarchy/omacorsair/status.json` | Live daemon status. |
| `~/.local/state/omarchy/current/theme/keyboard.rgb` | Theme color input for `theme` mode. Missing file: lighting is left alone. |
| `~/.config/omarchy/plugins/case.omacorsair` | Plugin install location (symlink to this checkout for development). |
| `~/.config/omarchy/shell.json` | Plugin entry; optional `"rawColor": true`. |
| `/etc/udev/rules.d/70-omacorsair.rules` | Installed by `install-device-access.sh`. |
| `/sys/class/hidraw/hidraw*` | Device discovery (`candidates()`), then `/dev/hidrawN`. |

`status.json` keys: on success `connected`, `applied`, `mode`, `settings`, `started`, `dial`, `error` (empty string). On a loop error only `connected: false`, `applied: false`, `error`.

Config limits: file read capped at 4097 characters; unknown keys are rejected; `color`/`accent` are six hex digits (an optional `#` is stripped); `brightness` is an int 0..100; `vivid` is a bool; `speed` is an int 10..100.

## Polling and timing

| Where | Interval | Notes |
|---|---|---|
| `run_daemon` loop | 0.25 s | Idle delay. Config and theme file are re-read each pass. |
| `run_daemon` loop, animated | 0.08 s | When the active mode is in `ANIMATED_MODES` and a keyboard is open. About 12 frames/s at most, since render and transfer time add to the delay. |
| Keepalive | 10 s | `next_keepalive` is pushed forward after each frame write, so keepalives are only sent when the lighting is idle. |
| Dial search retry | 5 s | `next_dial_attempt` after a failed open of interface 02. The error is logged once per distinct message. |
| Dial wait | up to the loop delay | `Dial.wait()` replaces `time.sleep`; it wakes on dial events. While steps are pending it polls in 0.03 s slices to flush merged turns. |
| HID write / reply timeouts | 1.0 s / 1.5 s | In `Keyboard.transfer`. |
| After `ACTIVATE_LEDS` | 0.5 s sleep | Once per entry into software mode. |
| `Service.qml` retry | 5 s | Restart delay for the daemon. |
| `Panel.qml` status poll | 700 ms (animated look selected) / 1500 ms | Only while the popup is open (`Timer` in `Panel.qml`). |
| `Panel.qml` layout poll | 10 s | Plus an 80 ms debounced refresh on Hyprland `activelayout` and `configreloaded` events. |

## Hardware and software mode

- The keyboard normally runs its own (hardware) lighting, driven by its lighting hotkeys.
- On the first frame the daemon sends `SOFTWARE_MODE` and `ACTIVATE_LEDS`, waits 0.5 s, then streams the color buffer. `Keyboard.software_mode` records this so the sequence is sent once per connection.
- Lighting is volatile. The keyboard reverts when the daemon stops sending keepalives or the keyboard is power-cycled. Nothing is written to onboard flash, profiles or firmware.
- `hardware` mode ("Built-in lighting"): the daemon closes the dial and the keyboard (which sends `HARDWARE_MODE`) and idles. It still reports `connected` by checking that the device exists.
- `theme` mode with no `keyboard.rgb`: `render_frame` returns `None`; the daemon does not touch the lighting but still sends keepalives if software mode is already active.
- The daemon sends `HARDWARE_MODE` on normal stop (`Keyboard.close()`) and when the device is released after an error, so a normal shutdown always restores built-in lighting. A crash or `SIGKILL` cannot.
- **Volume dial.** In software mode the firmware stops sending the dial as media keys on interface 00 and reports it on interface 02. While the keyboard is in software mode the daemon opens interface 02 read-only (`Dial`), maps reports with `dial_action()` and runs `omarchy-audio-output-volume` (found via `PATH`, then `/usr/share/omarchy/bin`), falling back to `wpctl`. Turns that arrive while a command is still running are summed into one command. Mute fires once per press. The dial is closed in `hardware` mode and on errors. `status.json` reports `dial: true/false`.

## Tests

`tests/test_backend.py` and `tests/test_layouts.py` run without hardware (they import the helpers with `importlib` and mock I/O). `tests/hardware_smoke.py` and `tests/menu_smoke.py` are live tests; see `AGENTS.md`.
