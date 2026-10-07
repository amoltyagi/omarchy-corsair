# Architecture

Omacorsair is an Omarchy 4 shell plugin (Quickshell/QML) plus two stdlib-only Python helpers. Nothing runs as root; the udev rule grants the active desktop user access to the HID nodes.

## Components

| File | Role |
|---|---|
| `manifest.json` | Plugin metadata. Entry points: `service` = `Service.qml`, `barWidget` = `Panel.qml`. |
| `Service.qml` | Background service. Starts and supervises the lighting daemon. |
| `Panel.qml` | Bar button and popup. Never talks to the keyboard; it only runs helper commands. |
| `bin/omacorsair.py` | Lighting backend, volume-dial listener, config/status handling, CLI. |
| `bin/layouts.py` | Keyboard layout status and switching (every layout in Hyprland's `kb_layout`) through `hyprctl`. Independent of the keyboard hardware. |
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

1. **Panel to config.** A click or IPC call runs `omacorsair.py set '<json>'`. It merges the update into the current config, validates it (`validate_config`), and writes it atomically (`atomic_json`: temp file in the same directory, then `os.replace`). Concurrent updates in the panel are merged in `pendingUpdate` and sent after the running one finishes. Gallery next/previous (wheel, arrows, IPC) send a relative `{"step": n}` that the helper resolves against the saved mode (`apply_update`); coalesced steps add up, and an absolute `mode` resets them. Every bar copy watches `omacorsair.json` (QML `FileView`) and refreshes when it changes, so no copy acts on a stale look after a CLI, script or other-monitor change.
2. **Config to daemon.** There is no signal or socket. The daemon calls `read_config()` on every loop iteration and renders a 371-byte frame with `render_frame()`. In `theme` mode it also reads `~/.local/state/omarchy/current/theme/keyboard.rgb` (`read_color`, at most 64 bytes, one `RRGGBB` value).
3. **Daemon to device.** If the frame differs from the last applied one, `Keyboard.apply()` sends it (see `PROTOCOL.md`). Animated looks produce a new frame each iteration.
4. **Daemon to panel.** The daemon writes `status.json` only when the status dict changes. Animation frames do not change it: the animation clock is stored as an origin (`started`, `phase0`, `speed`) that changes only when the mode or the speed changes, so there is no per-frame disk write or log line.
5. **Panel reads state.** `omacorsair.py status` prints one JSON object: `config`, `device` (the contents of `status.json`), `catalog` (`CATALOG`) and `preview` (rows of `#rrggbb`, rendered in the status process from the same `render_frame()` at the daemon's current animation phase, see below).
6. **Layouts.** `Panel.qml` runs `bin/layouts.py status|set|toggle`, which calls `hyprctl devices -j` and `hyprctl switchxkblayout`. It shares no state with the lighting daemon. See Layouts below.

`CATALOG` in `omacorsair.py` is the single source of looks: the daemon (`MODES`, `ANIMATED_MODES`), the CLI validation, and the popup gallery (via `status`) all derive from it. Only the quick-color list is defined in `Panel.qml` (`colors`).

## Process model and restart behaviour

- `Service.qml` runs `/usr/bin/python3 -I bin/omacorsair.py daemon`, plus `--raw` when the plugin setting `rawColor` is `true` in `shell.json`. The process starts as soon as the service loads.
- The daemon's stderr is forwarded line by line to the shell's console/journal (each line cut to 1024 characters). Daemon log lines start with `[omacorsair]`.
- If the daemon exits while the service is not stopping, the service logs `helper exited (<code>), retrying in 5 seconds` and restarts it after 5 s (`retry` timer). This applies to any exit code, including a clean exit after `SIGTERM`.
- When the service is destroyed (plugin disabled or shell stops), it sets `stopping`, cancels the retry, and sends `SIGTERM`.
- The daemon handles `SIGTERM` and `SIGINT` by setting `STOP`. The loop ends, and `Keyboard.close()` sends the hardware-mode command before closing the device, so the keyboard returns to its built-in lighting.
- Device or I/O errors (`OSError`, `ValueError`, `UnicodeError`) inside a loop iteration do not end the process, and a single failure does not drop the connection. The daemon logs the message once per distinct text, writes an error status, forces the next pass to resend the whole frame (`applied = None`, so a half-sent frame is repainted) and retries with the device still open. The connection is torn down (dial and keyboard closed, which sends `HARDWARE_MODE`, device re-discovered on the next pass) only when
  - the error means the device is gone: `ENODEV`, `EIO`, `EPIPE`, `ENOENT` or `ENXIO` (`device_gone()`), which covers unplug/replug; or
  - `MAX_CONSECUTIVE_FAILURES` (3) loop passes failed in a row. A failing transfer blocks for 1.0 to 1.5 s and the loop adds 0.08 to 0.25 s, so three failures mean at least about three seconds of a silent device, which is no longer a blip but still recovers quickly. Any successful pass resets the count.
  A failed connection handshake (the firmware query right after opening) releases that candidate immediately; nothing has been sent in software mode yet.
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

`status.json` keys:

| Key | Meaning |
|---|---|
| `connected` | Keyboard open (in `hardware` mode: the device exists). `false` on every error status. |
| `applied` | A frame has been sent and is current. `false` on every error status. |
| `mode` | Active look id. |
| `settings` | The validated config the daemon is using. |
| `started`, `phase0`, `speed` | Animation clock origin (see Animation clock). |
| `dial` | Whether the dial listener is open. |
| `error` | Empty string when fine, otherwise the last error message. |

On success all keys are present. On a loop error the status has `connected: false`, `applied: false`, `error` and `dial` (always known), plus `mode`, `settings` and the clock keys from the last config that validated. Those three are missing only if the very first config read has not succeeded yet. `Panel.qml` reads `device.connected`, `device.error` and `device.mode` (and falls back to `config.mode`), so an error status shows the message and the look is not lost.

Config limits: file read capped at 4097 characters; unknown keys are rejected; `color`/`accent` are six hex digits (an optional `#` is stripped); `brightness` is an int 0..100; `vivid` is a bool; `speed` is an int 10..100.

## Layouts

`bin/layouts.py` works on the layouts Hyprland reports for the preferred typing keyboard (the Corsair K65 Plus if listed, else the `main` keyboard, else the first one; pseudo keyboards such as power buttons are ignored).

- `configured()` splits `layout` and `variant` (both comma separated, positional) into entries `{index, code, variant, key}` in `kb_layout` order. An identical repeated `code`+`variant` is one entry. `key` is the code, or `code(variant)` when the same code is configured with different variants.
- `status` prints `active` (key), `label` and `name` of the active layout, `available` (all keys in order), `layouts` (`[{code, label, name}]` for the panel buttons), `keyboard` and `count`.
  - `label`: `us` EN, `de` DE, `gb` UK, otherwise the upper-cased code; a variant disambiguated entry adds `-VARIANT` (`EN-INTL`).
  - `name`: Hyprland's `active_keymap` for the active layout (it names only that one), otherwise the built-in `NAMES` map, otherwise the code. A variant is appended to built-in names.
  - The active entry comes from `active_layout_index`; without it (older Hyprland) the keymap name is matched against the configured entries.
- `toggle` switches to the next entry after the active one, wrapping. With fewer than two layouts it fails with a hint instead of doing nothing silently.
- `set <code>` accepts any configured key or bare code (case-insensitive); anything else fails with the list of configured layouts.
- Switching is applied to every typing keyboard. Each keyboard has its own layout order, so the target is matched per keyboard by code and variant, then `switchxkblayout <name> <index>` is called. The result is re-read and checked.
- `Panel.qml` builds the layout buttons from `layouts`, hides the row when fewer than two are configured (showing how to add more instead) and ignores middle-click in that case. The IPC names `toggleLanguage` and `setLanguage` are unchanged.

## Animation clock

Animated looks are functions of a phase `t`. The phase advances at `speed_factor(speed) = 0.2 + speed * 0.016` per second and is kept as an origin `(started, phase0, speed)`, so `t = phase0 + (now - started) * speed_factor(speed)` (`animation_phase()`).

- A mode change restarts the clock: `started = now`, `phase0 = 0`.
- A speed change rebases it (`retime_animation()`): `phase0` becomes the phase reached so far, `started = now`, and the new speed applies from there. The animation continues where it was instead of jumping.
- The origin is part of `status.json` and is rewritten only when it changes. The `status` command reads it and computes the same phase with `status_phase()` (using the speed the daemon runs at, not the possibly newer configured one), so the panel preview matches the keyboard. `monotonic()` is system-wide on Linux, so both processes share the time base.
- Status files from older versions have only `started`; they are read as `phase0 = 0` at the configured speed. If the configured mode differs from the one in the status file (the daemon has not picked up the change yet), the preview uses phase 0, which is where the daemon will restart.

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
- The daemon sends `HARDWARE_MODE` on normal stop (`Keyboard.close()`) and when the connection is torn down after an error (see above), so a normal shutdown always restores built-in lighting. A crash or `SIGKILL` cannot.
- **Volume dial.** In software mode the firmware stops sending the dial as media keys on interface 00 and reports it on interface 02. While the keyboard is in software mode the daemon opens interface 02 read-only (`Dial`), maps reports with `dial_action()` and runs `omarchy-audio-output-volume` (found via `PATH`, then `/usr/share/omarchy/bin`), falling back to `wpctl`. Turns that arrive while a command is still running are summed into one command. Mute fires once per press. The dial is closed in `hardware` mode and on errors. `status.json` reports `dial: true/false`.

## Tests

`tests/test_backend.py` and `tests/test_layouts.py` run without hardware (they import the helpers with `importlib` and mock I/O). `tests/hardware_smoke.py` and `tests/menu_smoke.py` are live tests; see `AGENTS.md`.
