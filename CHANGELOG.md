# Changelog

## Unreleased

- Fix: the volume dial works while software lighting is active. The firmware reports it on vendor interface 02 in that mode; the helper now listens there read-only, drives `omarchy-audio-output-volume` (with a `wpctl` fallback), merges fast turns, and toggles mute once per press.
- The udev rule now also grants interface 02. Existing users must re-run `install-device-access.sh` after updating.
- Developer docs: `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/PROTOCOL.md`, `docs/EXTENDING.md`.

## 1.2.0 — 2026-10-05

- 28 lighting looks, including nine animated effects and 11 new static palettes.
- Compact keyboard-preview gallery with wheel/arrow browsing, categories, and Surprise me.
- Coalesced rapid mode changes and animation speed controls.
- Integrated English/German layout selection, active EN/DE bar label, and middle-click toggle.
- Optional Ctrl+Alt+Space language shortcut.
- 22 hardware-independent unit tests, live hardware/menu smoke tests, and GitHub Actions.

## 1.1.0 — 2026-10-05

- Keyboard bar button, manual color presets, and custom base/accent hex colors.
- WASD/arrow highlights, Ocean, Sunset, Rainbow rows, brightness controls, and lights off.
- Persistent lighting preferences and live device status.

## 1.0.0 — 2026-10-05

- Theme synchronization for wired Corsair K65 Plus `1b1c:2b11`.
- Direct HID backend using Python's standard library.
- Software-mode keepalive, reconnect handling, and normal-stop hardware-mode restoration.
- Narrowly scoped, opt-in udev device-access setup.
