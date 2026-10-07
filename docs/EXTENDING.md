# Extending Omacorsair

Run the checks from `AGENTS.md` after any change. A look is defined once, in `CATALOG` in `bin/omacorsair.py`; the CLI, daemon, and gallery all read it. Do not add looks anywhere else.

## Add a static palette

A palette maps six colors to the six physical rows (`ROW_OFFSETS`), top to bottom.

1. In `bin/omacorsair.py`, add an entry to `PALETTES`: `"myid": ("rrggbb", ... six values)`. Colors are lowercase hex without `#`. The id must be unique and also be the `CATALOG` id.
2. Add `("myid", "Display name", "One-line hint.")` to the tuple list in the `for mode, name, hint in (...)` loop that builds the `"Palettes"` category.
3. Nothing else is needed. `MODES`, config validation, the preview, the gallery and `setMode myid` pick it up. Brightness and the reserved slot are handled in `render_frame`.
4. Update the count wording ("28 looks") in `README.md`, `manifest.json` description and `CHANGELOG.md` if the total changes. `test_catalog_and_animation_frames` in `tests/test_backend.py` asserts exactly 28 looks (9 animated); update those numbers.
5. Add or extend a test (for example, that rows use your colors, like `test_row_palettes_follow_physical_key_rows`).

## Add an animated look

1. Add a branch to `animated_rgb(mode, x, y, seed, t, base, accent)` in `bin/omacorsair.py`. Inputs: `x` 0..1 across the row, `y` 0..1 top to bottom (row/5), `seed` a per-key number (`offset // 3`), `t` scaled time in seconds (speed-adjusted), `base` and `accent` as 0..1 RGB tuples. Return an RGB tuple with channels 0..1 (values are clamped by `render_frame`). Keep it deterministic and cheap: it runs for every key about 12 times per second.
2. Add `("myid", "Display name", "Hint.", custom)` to the animated tuple list that builds the `"Motion"` category. Set `custom` to `True` if the look uses the user's base/accent colors (the popup then shows the color fields), otherwise `False`.
3. `ANIMATED_MODES` is derived from the `animated` flag, so the loop delay (0.08 s), the speed slider and the 700 ms panel poll apply automatically.
4. Do not log, write status, or touch the disk per frame. The daemon only does that when the status or config changes.
5. `test_catalog_and_animation_frames` already checks every animated look (frame length 371, bytes 3..5 zero, frames differ over time); update its look counts (28 / 9) and the counts in the docs.
6. Restart the daemon (`pkill -TERM -f '[o]macorsair.py daemon'`) to try it. `tests/hardware_smoke.py` cycles every catalog entry, but it changes the lighting, so only run it when asked.

## Add a quick color

Quick colors are the dots under "QUICK COLORS" in the popup. They set `{mode: "solid", color: hex}`.

1. In `Panel.qml`, add `{name: "Teal", hex: "00ccaa"}` to the `colors` property.
2. The grid is declared with `columns: 10` and `width: (parent.width - parent.spacing * 9) / 10`, which assume 10 entries. If you add or remove entries, update those numbers (`columns` and the `9`/`10` in the width) so the row still fits.
3. Use lowercase six-digit hex without `#`; the config stores it that way and the selection highlight compares against `config.color`.
4. Update the "ten quick presets" text in `README.md`.

## Adding another Corsair model (not yet supported)

Not yet supported. The backend is hard-wired to the wired K65 Plus. A new model would need at least:

- **Device ID:** `DEVICE_ID` (`HID_ID=0003:00001B1C:0000XXXX`), the checks in `Keyboard.__init__` and `Dial.__init__` (`(3, 0x1B1C, 0x2B11)`), and the `idProduct` in `70-omacorsair.rules`.
- **Interface numbers:** the lighting interface (default `"01"` in `candidates()`) and the dial/event interface (`DIAL_INTERFACE`), plus the udev `ID_USB_INTERFACE_NUM` match.
- **Key offset map:** replacement `ROW_OFFSETS` and `GAMING_OFFSETS`, derived from the model's OpenLinkHub keyboard JSON. Previews and per-row palettes assume six rows.
- **Buffer length:** the 371-byte buffer (`render_frame`, `color_packets`), its reserved bytes, and the 61-byte chunking, plus the commands in `PROTOCOL.md`, which may differ per model.
- Wireless connections use different USB IDs and endpoints and are likewise unsupported.
