#!/bin/bash
set -euo pipefail
source_dir=$(dirname "$(realpath "$0")")
destination="$HOME/.config/omarchy/plugins/case.omacorsair"
omarchy plugin validate "$source_dir"
if [[ -e "$destination" || -L "$destination" ]]; then
  [[ $(realpath "$destination") == "$source_dir" ]] || {
    printf 'Existing plugin at %s; refusing to overwrite it.\n' "$destination" >&2
    exit 1
  }
else
  mkdir -p "$(dirname "$destination")"
  ln -s "$source_dir" "$destination"
fi
if [[ -f "$HOME/.config/omarchy/shell.json" ]]; then
  cp -p "$HOME/.config/omarchy/shell.json" "$HOME/.config/omarchy/shell.json.before-omacorsair.$(date +%s)"
fi
omarchy-shell shell rescanPlugins
# Registry discovery is asynchronous; IPC returns before the scan completes.
for attempt in {1..20}; do
  if omarchy plugin list --json | jq -e 'any(.[]; .id == "case.omacorsair")' >/dev/null; then
    break
  fi
  sleep 0.25
done
omarchy plugin enable case.omacorsair
