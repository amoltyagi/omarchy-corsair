# Protocol notes (Corsair K65 Plus, USB `1b1c:2b11`)

Everything here is taken from `bin/omacorsair.py`. The protocol is adapted from OpenLinkHub (see Credit). Constants are quoted by their names in the code.

## USB interfaces

The device is matched through sysfs (`/sys/class/hidraw/hidraw*`) by `HID_ID=0003:00001B1C:00002B11`, then by `bInterfaceNumber`. After opening, both classes verify with `HIDIOCGRAWINFO` (`0x80084803`) that bus/vendor/product is `3/0x1B1C/0x2B11`.

| Interface | Used for | How the plugin uses it |
|---|---|---|
| 00 | Typing and media keys (normal HID input) | Never opened. In hardware mode the dial arrives here as media keys; in software mode it stops. |
| 01 | Vendor command channel (lighting, mode, firmware, keepalive) | `Keyboard`: opened `O_RDWR`, exclusive `flock`. Default for `candidates()`. |
| 02 | Vendor reports; carries dial events in software mode | `Dial`: opened `O_RDONLY`, never written. |

The udev rule tags interfaces 01 and 02 with `uaccess` (`ENV{ID_USB_INTERFACE_NUM}=="01|02"`). Interface 00 is not granted.

## Report framing

All writes to interface 01 are 65-byte hidraw reports built by `report()`:

| Byte | Value |
|---|---|
| 0 | `0x00` (hidraw report ID) |
| 1 | `0x08` (command class) |
| 2.. | endpoint/command bytes, then payload |
| rest | zero padding to 65 bytes |

`report()` raises `ValueError` if the data exceeds 65 bytes.

`Keyboard.transfer()`:

1. Drains up to 16 stale pending reads (reads are 64 bytes).
2. Waits up to 1.0 s for the fd to be writable and writes the 65 bytes.
3. Reads replies for up to 1.5 s until one has `response[0] == 0x00` and `response[1] == endpoint[0]`. `response[2]` is the status; non-zero raises `OSError`. No match raises `TimeoutError`.

## Commands

All are endpoint bytes passed to `report()`:

| Name | Bytes | Notes |
|---|---|---|
| `SOFTWARE_MODE` | `01 03 00 02` | Enter software (host-controlled) lighting. |
| `HARDWARE_MODE` | `01 03 00 01` | Return to built-in lighting. Sent on `Keyboard.close()` if software mode was entered. |
| `ACTIVATE_LEDS` | `0d 00 22` | Sent right after `SOFTWARE_MODE`; the daemon then sleeps 0.5 s. |
| `FIRMWARE` | `02 13` | Reply bytes: major `data[3]`, minor `data[4]`, patch `data[5:7]` little-endian. Printed as `major.minor.patch`. Needs at least 7 bytes. |
| `KEEPALIVE` | `12` | Sent every 10 s while the lighting is idle. |

`Keyboard.apply()` sequence on first use: `SOFTWARE_MODE`, `ACTIVATE_LEDS`, sleep 0.5 s, then the color stream. Later calls only send the color stream. Each step is remembered once it succeeded (`software_mode` after `SOFTWARE_MODE`, `leds_active` after `ACTIVATE_LEDS` and the sleep), so a retry after a failed transfer neither repeats `SOFTWARE_MODE` nor skips `ACTIVATE_LEDS`. A color stream that failed halfway is always resent from its first chunk.

## Color buffer

`color_packets(color)` takes either a 6-digit hex string (all slots the same color) or a 371-byte frame.

- The buffer is 371 bytes: 123 RGB slots of 3 bytes (369 bytes) plus 2 trailing bytes. A hex string expands as `rgb * 123 + 00 00`.
- Slot 1 (bytes 3..5) is reserved. `color_packets` and `render_frame` clear it to `00 00 00`; OpenLinkHub does the same.
- The buffer is sent as a stream: `<uint16 little-endian: len(data)+2 = 373>` (`75 01`), then `00 00 12 00`, then the 371 bytes. Total 377 bytes.
- The stream is cut into 61-byte chunks (7 chunks; the last is 17 bytes). Each chunk goes into a report with endpoint `06 00` for the first chunk and `07 00` for all others. Each report is therefore `00 08` + 2 endpoint bytes + up to 61 data bytes = 65 bytes.
- Each chunk is acknowledged like any other command (status byte 0).

Brightness is applied in software to every byte of the frame before sending; there is no firmware brightness command in use.

## Key offset maps

Per-key colors are written at byte offsets in the 371-byte buffer; each key uses 3 bytes (R, G, B) starting there.

- `ROW_OFFSETS`: six tuples, one per physical keyboard row, top (function row) to bottom (space row), with 14, 15, 15, 14, 13 and 11 keys. Used by palettes (one color per row), animations (x = column/(n-1), y = row/5, seed = offset//3) and the preview.
- `GAMING_OFFSETS`: `(78, 12, 66, 21, 246, 240, 243, 237)`, the W, A, S, D, ↑, ←, ↓, → keys (in that order) that get the accent color in `gaming` mode. Verified against `packetIndex` in OpenLinkHub `k65plus.json` at the reference commit.
- Source: OpenLinkHub `database/keyboard/k65plus.json`, US layout (the comment in the code says letter and arrow offsets are shared between layouts).
- Offsets are multiples of 3. The maximum used is 366 (bytes 366..368). Not every slot of the 123 is mapped to a key; unmapped slots receive the background color in static modes and stay at zero in animated modes.

## Dial reports (interface 02)

In software mode the firmware reports the dial as vendor reports on interface 02. `dial_action(data, pressed)` returns `(action, pressed_state)`:

| Condition | Meaning |
|---|---|
| `data[1] == 0x05` and `data[4] == 1` | Turn: `raise` |
| `data[1] == 0x05` and `data[4] == 255` | Turn: `lower` |
| `data[1] == 0x02` and `data[19] == 0x02` | Dial pressed. `mute-toggle` fires only on the transition from not pressed. |
| `data[1] == 0x02` and `data[19] != 0x02` | Released: state reset, no action. |
| anything else (or too short) | Ignored. |

Reports must be longer than index 4 (turns) or index 19 (press). Reads are 64 bytes.

`Dial` behaviour:

- Each `raise`/`lower` adds `DIAL_STEP` (5) to `pending`.
- A volume command runs only when no previous one is still running (`child.poll()`); the pending sum is then sent as a single `+N`/`-N` argument. Fast turns merge; opposite turns cancel.
- Command: `omarchy-audio-output-volume <arg>` (`PATH`, then `/usr/share/omarchy/bin`). Fallback: `wpctl set-volume -l 1.0 @DEFAULT_AUDIO_SINK@ N%+/-`, and `wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle` for mute.
- `omarchy-audio-output-volume` officially accepts `raise|lower|mute-toggle|+N|-N` (see its `omarchy:args` header) and shows the Omarchy OSD.
- Commands run with `start_new_session=True` and all stdio on `/dev/null`.

## Credit

The device protocol (mode switching, color stream, offsets and the dial report format) is adapted from OpenLinkHub, Copyright (C) jurkovic-nikola and contributors, GPL-3.0: <https://github.com/jurkovic-nikola/OpenLinkHub>. Reference file `src/devices/k65plusWU/k65plusWU.go` at commit `279513582cd34c546b8dc4b601b7e057cc9c7520`, and `database/keyboard/k65plus.json` for the offsets. See `NOTICE`.
