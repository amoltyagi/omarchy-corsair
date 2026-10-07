# Omacorsair marketplace listing draft

Status: text complete. Screenshots and demo are NOT captured yet (see "Screenshot shot-list").

## Submission form fields
(Template: omacom/omarchy-plugin-marketplace, `submit-plugin.yml`)

| Field | Value |
| --- | --- |
| Repository URL (required) | https://github.com/amoltyagi/omarchy-corsair |
| Category (required, one of Appearance / Desktop / Developer Tools / Hardware / Kids / Productivity / System / Widgets / Other) | **Hardware** |
| Tags (required, 1–3 from the fixed list) | **Hyprland**, **Bar**, **Quickshell** |
| Suggest a missing tag (optional) | `Keyboard` (or `RGB`); no existing tag covers keyboard lighting |
| Maintainer notes | See below |

Alternate tag set if reviewers prefer: Bar, Hyprland, System.

### Maintainer notes (paste into the form)

Omacorsair is a bar widget plus background service for the wired Corsair K65 Plus Wireless, USB ID `1b1c:2b11` only. Tested on Omarchy 4.0.4 with keyboard firmware 5.26.154. Other Corsair models and wireless connections are not supported.

- Dependencies: Python 3 (standard library only), `hyprctl`, the Omarchy shell. No network requests, OpenRGB, ckb-next, or third-party packages.
- Optional one-time step: `install-device-access.sh` installs a udev rule (`/etc/udev/rules.d/70-omacorsair.rules`) for the active local user on USB interface 01. It asks for desktop authentication, is run by the user explicitly, and is not run by `omarchy plugin add`. The removal command is in the README.
- Uses volatile software lighting only. It never writes keyboard assignments, onboard profiles, or firmware, and returns to built-in lighting when stopped.
- Does not edit Hyprland configuration. EN/DE switching needs the user to add `us,de` to `~/.config/hypr/input.lua` themselves, as documented in the README.
- Settings are stored in `~/.config/omarchy/omacorsair.json`.
- The Corsair protocol is adapted from OpenLinkHub (see NOTICE). License: GPL-3.0-only.
- Unit tests run in GitHub Actions without hardware. Live tests are opt-in.

### Checklist boxes
All five can be ticked truthfully, with these points to confirm first:
- Public repo with install and removal instructions: yes (README).
- License and dependencies documented: yes.
- Permission for preview assets: yes if the screenshots are the owner's own captures.
- No overwriting of user configuration: yes. Hyprland changes are manual and documented.
- Listing is not a security review: acknowledge.

## Listing copy

**Name:** Omacorsair
**Plugin ID:** `case.omacorsair`
**Version:** 1.2.0 (match manifest.json at submit time)
**Author:** amoltyagi
**License:** GPL-3.0-only

**Tagline (≤ 80):**
Your wired Corsair K65 Plus, wearing your Omarchy theme or 28 lighting looks.
(77 characters)

**Short description (≤ 200):**
Control the wired Corsair K65 Plus from the Omarchy bar: sync lighting to your theme or pick from 28 looks, 9 animated, with a live key preview, EN/DE layout switching, and the volume dial intact.
(about 196 characters)

**Long description:**
Omacorsair puts a keyboard icon in the Omarchy bar for the wired Corsair K65 Plus Wireless (USB `1b1c:2b11`). By default it follows your active theme's `keyboard.rgb`. When you want something else, scroll the mouse wheel over the icon or the miniature keyboard preview to flip through 28 lighting looks. The preview shows the selected look's actual per-key colors before you commit.

There are palettes such as Synthwave, Embers, Glacier and Sakura, plus nine animations: Aurora, Nebula, Matrix rain, Hearth fire, Prism tide, Comet, Breathing room, Silk waves and Fireflies. Animated looks have a speed slider with Dreamy, Flow and Energetic presets. Four of the animations use your own base and accent colors. You can also set a solid color, WASD + arrows highlighting, or any hex color, and adjust brightness. Lights off and built-in hardware lighting are one click away.

The same popup switches between English and German layouts (EN/DE), with an optional Ctrl+Alt+Space shortcut. The keyboard's volume dial keeps working while software lighting is active.

Lighting is sent as volatile software commands. The plugin never writes onboard profiles, key assignments or firmware, and it hands control back to the keyboard's built-in lighting when stopped. It needs Python 3 (standard library only) and makes no network requests. It supports only the wired K65 Plus Wireless, USB ID `1b1c:2b11`. It was tested on Omarchy 4.0.4 with firmware 5.26.154.

## Feature bullets
- 28 lighting looks: 14 palettes, 9 animations, theme sync, solid color, WASD + arrows, lights off, built-in lighting.
- Wheel-driven gallery with a miniature keyboard that shows the real per-key colors.
- "Browse all 28 looks" expanded picker, filtered by Palettes, Motion and Custom.
- Surprise me button for a random creative look.
- Animation speed slider with Dreamy / Flow / Energetic presets.
- Custom base and accent colors via hex input, with 10 quick presets.
- Brightness slider with 25/50/75/100% presets.
- Theme sync from `keyboard.rgb`, with optional vivid LED boost or exact RGB.
- EN/DE keyboard layout switching: click, middle-click the bar icon, or use an optional shortcut.
- The volume dial keeps working while software lighting is active.
- Volatile lighting only: no firmware or onboard profile writes.
- Re-applies after unplug/replug and after sleep.
- Pure Python standard library, no network access, no OpenRGB or ckb-next.

## Tags and category
- Category: Hardware
- Tags: Hyprland, Bar, Quickshell
- Suggested new tag: Keyboard

## Compatibility
- Keyboard: Corsair K65 Plus Wireless, wired over USB, `1b1c:2b11`, firmware `5.26.154`. Nothing else is tested or claimed.
- Not supported: other Corsair models, and the K65 Plus over wireless or Bluetooth.
- Desktop: Omarchy 4 (tested on 4.0.4), Quickshell, Hyprland with Lua configuration.
- Per-key layout uses the K65 Plus US LED row map. Other physical layouts were not tested.
- Requires: Python 3 (standard library), `hyprctl`, the Omarchy shell.
- Setup: one-time udev device-access step; `us,de` in Hyprland input config for EN/DE switching.
- Install: `omarchy plugin add https://github.com/amoltyagi/omarchy-corsair --enable`

## Screenshot shot-list
The marketplace guide says only that a preview is optional and "optimized automatically". It gives no size or format limits. Capture the popup only, never the desktop.

| # | File | View | Caption |
| --- | --- | --- | --- |
| 1 | `assets/01-gallery.png` | Default popup with gallery | Scroll over the keyboard preview to flip through 28 looks. |
| 2 | `assets/02-browse-all.png` | "Browse all looks" expanded | Browse every palette, animation and custom look in one place. |
| 3 | `assets/03-animated-speed.png` | Animated look (e.g. Aurora) with speed controls | Nine animations, with a speed slider and Dreamy / Flow / Energetic presets. |
| 4 | `assets/04-custom-colors.png` | Custom colors (e.g. Comet or WASD + arrows) | Set a base and accent color with a hex code or a quick preset. |
| 5 (optional) | `assets/demo.webm` | Animation in the preview, ≤ 10 s | Live preview of an animated look. |

Do not claim the bar button or desktop appear in these shots unless they actually do.
