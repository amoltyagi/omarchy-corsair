# Omacorsair

[![Tests](https://github.com/amoltyagi/omarchy-corsair/actions/workflows/test.yml/badge.svg)](https://github.com/amoltyagi/omarchy-corsair/actions/workflows/test.yml)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

Your wired Corsair K65 Plus, wearing your Omarchy theme—or one of 28 lighting looks.

An Omarchy shell plugin inspired by [Omakeychron](https://github.com/paulsp94/omakeychron).
Includes a keyboard bar button for manual colors, combinations and brightness,
plus automatic theme sync using the active theme's `keyboard.rgb`.
Supports the wired **Corsair K65 Plus Wireless, USB ID `1b1c:2b11`**.

## Compatibility

- **Tested keyboard:** Corsair K65 Plus Wireless over USB, `1b1c:2b11`, firmware `5.26.154`.
- **Tested desktop:** Omarchy `4.0.4`, Quickshell, and Hyprland's Lua configuration.
- **Dependencies:** Python 3 (standard library only), `hyprctl`, and the Omarchy shell.
- Per-key palettes use the K65 Plus US LED row map from OpenLinkHub.
- The hardware backend targets that exact USB ID and vendor interface. Other
  Corsair models and wireless connections need separate device support.

## Installation

### Install from GitHub

```sh
omarchy plugin add https://github.com/amoltyagi/omarchy-corsair --enable
bash ~/.config/omarchy/plugins/case.omacorsair/install-device-access.sh
```

The device-access step opens desktop authentication and installs a narrowly
scoped udev rule for the active local user on USB interface 01. The plugin itself
runs as your user. The background helper retries until access is available.

Configure English/German layouts as shown below if you want language switching.
Optionally place the button before your audio widget:

```sh
omarchy bar move case.omacorsair --section right --before omarchy.audio
```

### Install from a development checkout

Clone this repository, then run these commands from its directory:

```sh
bash install-device-access.sh
bash install.sh
```

The development installer links the checkout into
`~/.config/omarchy/plugins/case.omacorsair` and enables it. Keep the checkout in
place while installed. It refuses to overwrite an existing different installation.

### Update a GitHub-managed installation

```sh
omarchy plugin update case.omacorsair
```

Dependencies: Omarchy 4 / Quickshell and Python 3 (standard library only).

## Bar menu

Click the **keyboard icon** on the right side of the bar, just before audio.
Right-click the icon to return immediately to **Theme sync**.

### English / German keyboard layouts

The bar button shows the active **EN** or **DE** layout. At the top of its menu,
choose **EN · English** (US English) or **DE · Deutsch** (German/QWERTZ).
**Middle-click the bar button** to toggle. Add the optional **Ctrl+Alt+Space**
shortcut below if you also want a keyboard shortcut.
The switch is applied to all detected typing keyboards using their own layout
indices; power buttons and media-control devices are excluded.

The available layouts are configured persistently in `~/.config/hypr/input.lua`:

```lua
hl.config({ input = { kb_layout = "us,de", kb_variant = "" } })
```

The optional shortcut in `~/.config/hypr/bindings.lua` is:

```lua
o.bind("CTRL + ALT + SPACE", "Switch English / German keyboard layout", "omarchy-shell case.omacorsair toggleLanguage")
```

After changing Hyprland configuration, run `hyprctl reload` and
`hyprctl configerrors`. Back up your input and binding files before editing.
This layout switching is inspired by
[Keyboard Layout Switcher](https://github.com/jesusarchive/omarchy-keyboard-layout-switcher).

```sh
omarchy-shell case.omacorsair setLanguage de
omarchy-shell case.omacorsair setLanguage us
omarchy-shell case.omacorsair toggleLanguage
```

### Lighting gallery

The compact gallery contains **28 looks**, including **nine animations**:

- **Wheel over the bar button or keyboard preview** to change looks, or use the ‹ / › buttons
  and left/right arrow keys. Rapid wheel changes are coalesced to the latest choice.
- **Browse all 28 looks** expands a category-filtered picker (Palettes, Motion,
  Custom); collapse it again to save space.
- **Surprise me** picks a random creative look.
- The miniature keyboard previews the selected effect's actual per-key colors.
- Animated looks have a speed slider, plus **Dreamy / Flow / Energetic** presets.

### New palettes

Synthwave (neon pink/cyan), Mint condition (cream/sea glass), Embers
(coal/red/gold), Moonlight (silver/midnight), Sakura (peach/rose/plum),
Copper & candlelight (brass/espresso), Glacier (white/ice blue), Toxic orchid
(acid green/ultraviolet), Royal velvet (gold/purple), Cotton candy
(soft pastel rainbow), and Forest floor (moss/emerald).

### Animated looks

**Aurora** sends slow emerald/violet ribbons across the keys; **Nebula** mixes
purple clouds with starlit glints; **Matrix rain** sends green trails downward;
**Hearth fire** flickers red and gold; **Prism tide** rolls a diagonal rainbow.

Four animations use your custom colors: **Comet** sweeps an accent-colored head
and trail across a dim base, **Breathing room** pulses your base color,
**Silk waves** weaves your base and accent, and **Fireflies** twinkles your accent
over a dim base. Enter the colors and click Apply without leaving the effect.

Animation frames are sent at up to roughly 12 frames per second using volatile
lighting commands. Static looks remain idle except for keepalives. Frame updates
do not write onboard flash, disk status, or journal messages on every frame.

### Original controls

- **Theme sync**: follow Omarchy; toggle vivid LEDs versus exact RGB.
- **Solid color**: ten quick presets or any six-digit hex color.
- **WASD + arrows**: base color on the keyboard, accent on movement keys.
  Enter both hex colors and click **Apply both colors**.
- **Ocean / Sunset**: six-row cyan–violet or amber–pink–violet palettes.
- **Rainbow rows**: a static six-color rainbow across the physical rows.
- **Lights off**: all LEDs off.
- **Built-in lighting**: release software control so keyboard lighting hotkeys
  control its onboard effects.
- **Brightness**: slider and 25/50/75/100% presets; disabled for built-in lighting.

Modes and colors are saved in `~/.config/omarchy/omacorsair.json`. Manual
selections persist across theme changes, restarts and reconnects until you
choose Theme sync again. Live device status is in
`~/.local/state/omarchy/omacorsair/status.json`.

Tab navigates the controls; Enter activates a button or applies a hex color;
Escape closes the popup. You can also use these commands:

```sh
omarchy-shell case.omacorsair toggle
omarchy-shell case.omacorsair setColor '#8844ff'
omarchy-shell case.omacorsair setMode gaming
omarchy-shell case.omacorsair setMode theme
omarchy-shell case.omacorsair next
omarchy-shell case.omacorsair previous
omarchy-shell case.omacorsair surprise
```

## Behavior

- Applies the current selection at startup; changes usually apply within a second.
- Detects theme changes by reading `keyboard.rgb`, including changes where the shell accent stays the same.
- Reapplies after unplug/replug, and resumes after sleep.
- In Theme sync, optionally boosts saturation/value and adjusts green-cyan hues
  for more vivid LEDs, like Omakeychron. Manual colors use exact RGB.
- Themes without `keyboard.rgb` leave the current lighting alone.
- Sends a keepalive every ten seconds while software lighting is active.
- Returns to built-in hardware lighting when stopped normally or disabled.

Unlike the Keychron VIA implementation, this uses Corsair **volatile software
lighting**, not saved onboard profiles. The helper must stay running to maintain
the color. It never writes keyboard assignments, onboard profiles, or firmware.
No network requests, OpenRGB, ckb-next, or third-party Python packages are needed.

For exact unadjusted theme RGB, change the plugin entry in
`~/.config/omarchy/shell.json` to:

```json
{"id": "case.omacorsair", "rawColor": true}
```

## Diagnostics

```sh
python3 -I bin/omacorsair.py preview  # theme color and adjusted LED color
python3 -I bin/omacorsair.py probe    # read firmware, without changing lighting
```

Disable the plugin before a standalone test so two helpers do not compete:

```sh
omarchy plugin disable case.omacorsair
python3 -I bin/omacorsair.py test     # apply for 8 seconds, then restore
omarchy plugin enable case.omacorsair
```

Helper diagnostics appear in the Omarchy shell's journal with `[omacorsair]`.
Do not run another RGB controller on this keyboard concurrently.

Tests:

```sh
python3 -m unittest discover -s tests -v
omarchy plugin validate .
```

For an explicit live hardware test with the plugin enabled:

```sh
python3 tests/hardware_smoke.py
python3 tests/menu_smoke.py
```

The hardware test briefly changes the lighting through every mode and checks
sustained animation writes. The menu test checks rapid gallery cycling and
EN/DE actions. Both restore the original selection; the menu test also restores
the original keyboard layout.

## Removal

For a GitHub-managed installation:

```sh
omarchy plugin remove case.omacorsair
```

For a development installation, disable the plugin with
`omarchy plugin disable case.omacorsair`, then remove only its symlink
`~/.config/omarchy/plugins/case.omacorsair`.

Remove the plugin's Ctrl+Alt+Space binding from `~/.config/hypr/bindings.lua`
if uninstalling, then reload Hyprland and check `hyprctl configerrors`.

The optional device-access rule and saved lighting preferences persist after
plugin removal. To remove them too:

```sh
sudo rm /etc/udev/rules.d/70-omacorsair.rules
sudo udevadm control --reload-rules
rm -f ~/.config/omarchy/omacorsair.json
rm -rf ~/.local/state/omarchy/omacorsair
```

Your `us,de` Hyprland configuration remains available to other layout switchers.

## Contributing and publishing

Open an issue with your USB ID, firmware version, Omarchy version, and the relevant
`[omacorsair]` journal messages. The unit tests run without hardware in GitHub
Actions; live tests are opt-in and require a connected supported keyboard.

See [PUBLISHING.md](PUBLISHING.md) for marketplace submission details and
[CHANGELOG.md](CHANGELOG.md) for the feature history.

## Protocol and license

GPL-3.0-only. Corsair protocol adapted from
[OpenLinkHub](https://github.com/jurkovic-nikola/OpenLinkHub),
`src/devices/k65plusWU/k65plusWU.go`, commit
`279513582cd34c546b8dc4b601b7e057cc9c7520`. See [NOTICE](NOTICE) for attribution
and [LICENSE](LICENSE) for the full license text.
