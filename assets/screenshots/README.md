# Screenshots

Real captures of the Omacorsair popup, taken October 7, 2026 on the LG ultrawide
(DP-2): 3840x1600, 160% scaling, Omarchy 4.0.4, theme "Last Horizon", on an
empty workspace. Nothing was generated or edited. Controls and values are as
the plugin rendered them.

Process: switch the focused monitor to an empty workspace, set the look with
`omarchy-shell case.omacorsair setMode <id>`, open the popup with
`omarchy-shell case.omacorsair open`, then `grim -o DP-2`. The popup rectangle
came from a difference image between a capture with the popup open and one with it
closed (616 px wide, top at y=46). The saved lighting settings and the workspace
were restored afterwards.

| Panel (native size, transparent rounded corners) | Backdrop | Look | State |
| --- | --- | --- | --- |
| `panel-hero.png` (616x941) | `desktop-hero.jpg` | Synthwave | default view |
| `panel-motion.png` (616x1097) | `desktop-motion.jpg` | Aurora | speed controls visible |
| `panel-gallery.png` (616x1546) | `desktop-gallery.jpg` | Aurora | Browse all 28 looks expanded |

The backdrops are the same desktop captured with the popup closed (bar and
wallpaper only), cropped to the right-hand 1784 px.

Note: in the gallery view the popup is taller than the screen allows, so its
Flickable ends after the speed slider. The speed presets, brightness and the Theme
sync / Off / Built-in row are scrolled out of view. Nothing was modified to avoid this.
The gallery panel carries a keyboard-focus highlight on the "Hide gallery" button,
because the view was opened with the keyboard (Tab and Enter).

`../hero.svg`, `../motion.svg` and `../gallery.svg` compose the panel over the
backdrop with a headline and bullets. Render from the repository root:

```bash
rsvg-convert assets/hero.svg -o preview.png
rsvg-convert assets/motion.svg -o preview-motion.png
rsvg-convert assets/gallery.svg -o preview-gallery.png
```
