#!/bin/bash
set -euo pipefail
if (( EUID != 0 )); then
  exec pkexec /bin/bash "$(realpath "$0")"
fi
install -m 0644 "$(dirname "$(realpath "$0")")/70-omacorsair.rules" /etc/udev/rules.d/70-omacorsair.rules
udevadm control --reload-rules
udevadm trigger --action=change --subsystem-match=hidraw
udevadm settle
