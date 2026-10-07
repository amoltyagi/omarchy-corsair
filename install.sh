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
# Back up shell.json only when it differs from the newest backup, so re-running
# the installer does not pile up identical copies. Nothing is ever deleted.
shell_json="$HOME/.config/omarchy/shell.json"
if [[ -f "$shell_json" ]]; then
  newest_backup=""
  # The suffix is an epoch timestamp, so glob (lexical) order is chronological.
  for backup in "$shell_json".before-omacorsair.*; do
    [[ -f "$backup" ]] && newest_backup="$backup"
  done
  if [[ -z "$newest_backup" ]] || ! cmp -s "$shell_json" "$newest_backup"; then
    cp -p "$shell_json" "$shell_json.before-omacorsair.$(date +%s)"
  fi
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
