# AGENTS.md

Omacorsair: Omarchy 4 shell plugin (Quickshell/QML + stdlib-only Python) for the wired Corsair K65 Plus (`1b1c:2b11`): per-key lighting, volume dial in software mode, EN/DE layout switching.

## Repo map

| Path | What |
|---|---|
| `manifest.json` | Plugin manifest (service + bar widget). |
| `Service.qml` | Runs and restarts the daemon (5 s retry). |
| `Panel.qml` | Bar button, popup, quick colors, IPC handlers. |
| `bin/omacorsair.py` | Backend: `CATALOG`, rendering, HID protocol, `Dial`, daemon, CLI. |
| `bin/layouts.py` | EN/DE switching via `hyprctl`. |
| `70-omacorsair.rules` | udev `uaccess` for interfaces 01 and 02. |
| `install.sh`, `install-device-access.sh` | Dev install; udev rule install. |
| `tests/test_backend.py`, `tests/test_layouts.py` | Hardware-free unit tests. |
| `tests/hardware_smoke.py`, `tests/menu_smoke.py` | Optional live tests. |
| `docs/` | `ARCHITECTURE.md`, `PROTOCOL.md`, `EXTENDING.md`. |
| `NOTICE`, `LICENSE` | GPL-3.0-only; OpenLinkHub attribution. |

## Conventions

- Python standard library only. No third-party packages. Helpers run as `/usr/bin/python3 -I`.
- Never write onboard flash, profiles, key assignments or firmware. Lighting is volatile (software mode); the dial listener is read-only.
- One `CATALOG` in `bin/omacorsair.py` defines all looks. Do not duplicate mode lists in QML.
- Keep the daemon quiet per frame: no logging, status writes or disk I/O for every animation frame.
- Do not edit `PUBLISHING.md` unless asked.

## Required checks before finishing

```sh
python3 -m unittest discover -s tests -v
omarchy plugin validate .
bash -n install.sh install-device-access.sh
```

## Live tests (only when asked)

`python3 tests/hardware_smoke.py` and `python3 tests/menu_smoke.py` need the plugin enabled and a connected keyboard. They change the lighting (and the menu test the keyboard layout), then restore the original settings. Do not run them otherwise.

## Restarting the helper after code changes

```sh
pkill -TERM -f '[o]macorsair.py daemon'
```

The service respawns it after 5 s.

## Docs

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/PROTOCOL.md](docs/PROTOCOL.md)
- [docs/EXTENDING.md](docs/EXTENDING.md)
- [README.md](README.md) (user-facing)
