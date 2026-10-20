#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

bash -n "$ROOT/install.sh"
bash -n "$ROOT/uninstall.sh"
bash -n "$ROOT/bin/steamos-cec-permissions-apply"
python3 -m py_compile "$ROOT/bin/steamos-cec-toolkitctl" "$ROOT/bin/steamos-cec-external-volume"

grep -q 'Skipping SteamOS atomic-update configuration' "$ROOT/install.sh"
grep -q 'CEC_DEVICE_DIRECTORY' "$ROOT/bin/steamos-cec-toolkitctl"
grep -q 'steamos-cec-external-volume.socket' "$ROOT/install.sh"
if grep -q 'cec-audio-control.socket' "$ROOT/install.sh"; then
  echo "installer still assumes SteamOS cec-audio-control.socket" >&2
  exit 1
fi

bash -n "$ROOT/scripts/easy-install.sh"
bash -n "$ROOT/easy-install.sh"
bash -n "$ROOT/bin/steamos-cec-adapter-config"
bash -n "$ROOT/bin/steamos-cec-pactl-wrapper"
bash -n "$ROOT/bin/steamos-cec-wpctl-wrapper"
bash -n "$ROOT/bin/steamos-cec-usb-wake-apply"
python3 -m py_compile \
  "$ROOT/bin/steamos-cec-tv-standby-suspend" \
  "$ROOT/bin/steamos-cec-input-away-suspend" \
  "$ROOT/bin/steamos-cec-gamescope-recovery" \
  "$ROOT/bin/steamos-cec-steam-button"

for required in "$ROOT/systemd/system/steamos-cec-adapter-config.service" "$ROOT/udev/99-steamos-cec-adapter-config.rules" "$ROOT/bin/steamos-cec-adapter-config"; do
  if [[ ! -f "$required" ]]; then
    echo "missing adapter-config support file: $required" >&2
    exit 1
  fi
done

grep -q 'cachyos' "$ROOT/lib/platform.sh"
grep -q 'steamos-cec-adapter-config.service' "$ROOT/install.sh"
grep -q 'kripikripi/steamos-cec-toolkit.git' "$ROOT/scripts/easy-install.sh"
grep -q 'REPO_REF' "$ROOT/scripts/easy-install.sh"
grep -q 'steamos-cec-debug-monitor' "$ROOT/bin/steamos-cec-gamescope-recovery"
grep -q 'steamos-cec-debug-monitor' "$ROOT/bin/steamos-cec-input-away-suspend"
grep -q 'steamos-cec-debug-monitor' "$ROOT/bin/steamos-cec-tv-standby-suspend"
grep -q 'CEC_ACTIVE_SOURCE_OPCODES' "$ROOT/bin/steamos-cec-input-away-suspend"
grep -q 'CEC_ACTIVE_SOURCE_OPCODES' "$ROOT/config/steamos-cec-toolkit.conf.example"
# install.sh and the shell helpers source this file, so an uncommented prose line
# ships straight into /etc and aborts the install; reject that at release time.
bash -n "$ROOT/config/steamos-cec-toolkit.conf.example"

for f in steamos-cec-before-sleep steamos-cec-debug-monitor steamos-cec-volume-raw steamos-cec-resume-wake;
  do
  if grep -q 'USER_CONFIG[A-Z_]*="/home/' "$ROOT/bin/$f"; then
    echo "bin/$f still hardcodes /home for the user config" >&2
    exit 1
  fi
done
for f in steamos-cec-steam-button steamos-cec-boot-wake; do
  if grep -q 'USER_CONFIG = f"/home/' "$ROOT/bin/$f"; then
    echo "bin/$f still hardcodes /home for the user config" >&2
    exit 1
  fi
done

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir "$tmp/devices"
touch "$tmp/devices/cec0"
CEC_DEVICE_DIRECTORY="$tmp/devices" \
  STEAMOS_CEC_CONFIG="$tmp/missing.conf" \
  HOME="$tmp/home" \
  python3 - "$ROOT/bin/steamos-cec-toolkitctl" <<'PY'
import importlib.machinery
import importlib.util
import sys

loader = importlib.machinery.SourceFileLoader("toolkitctl", sys.argv[1])
spec = importlib.util.spec_from_loader("toolkitctl", loader)
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)
result = module.discover_cec()
assert len(result["available_cec_devices"]) == 1
assert result["cec_device"].endswith("/cec0")
PY

echo "portability checks passed"
