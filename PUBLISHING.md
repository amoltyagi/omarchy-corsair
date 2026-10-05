# Omarchy marketplace submission

Repository: https://github.com/amoltyagi/omarchy-corsair

The repository has a root `manifest.json`, installation/removal instructions,
full GPL-3.0 license text, upstream attribution, and automated unit tests.

## Submission details

- **Name:** Omacorsair
- **Plugin ID:** `case.omacorsair`
- **Version:** `1.2.0`
- **Author / publisher:** `amoltyagi`
- **Category:** System / Hardware (choose the closest available form category)
- **Suggested tags:** keyboard, corsair, rgb, lighting, hyprland
- **Description:** A keyboard control center for the wired Corsair K65 Plus:
  English/German layout switching, 28 lighting looks, nine animations, and a
  wheel-driven preview gallery with custom colors, speed, and brightness controls.
- **Compatibility:** Omarchy 4; tested on 4.0.4, keyboard USB `1b1c:2b11`, firmware `5.26.154`.
- **Install:** `omarchy plugin add https://github.com/amoltyagi/omarchy-corsair --enable`
- **Setup:** One-time device-access rule; `us,de` Hyprland layout configuration
  for EN/DE switching. Both are documented in the README.

## Before submitting a specific commit

Run:

```sh
python3 -m unittest discover -s tests -v
omarchy plugin validate .
bash -n install.sh install-device-access.sh
git rev-parse HEAD
```

Record the commit hash, and check the corresponding GitHub Actions run. Hardware
smoke tests are optional commands documented in the README and briefly change
lighting/layout before restoring the original settings.

An optional marketplace preview should show only the plugin popup. Avoid a
full-desktop screenshot with unrelated windows or personal information.

Submit the repository through the official form:

https://github.com/omacom/omarchy-plugin-marketplace/issues/new?template=submit-plugin.yml

Publishing guide: https://plugins.omarchy.org/publish.html

Marketplace listing approval and snapshot verification are separate workflows.
