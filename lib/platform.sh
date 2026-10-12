#!/usr/bin/env bash

cec_platform_id() {
  local id=""
  if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    id="${ID:-}"
  fi
  printf '%s\n' "${id:-unknown}"
}

cec_is_steamos() {
  [[ "$(cec_platform_id)" == "steamos" ]]
}

# Distributions without Valve's cecd: CachyOS (including cachyos-handheld style
# IDs) and Arch rely on cec-ctl raw fallbacks plus the adapter-config service.
cec_platform_generic_cec() {
  case "$(cec_platform_id)" in
    cachyos|cachyos-*|arch|arch-*) return 0 ;;
    *) return 1 ;;
  esac
}

cec_optional_user_service_available() {
  systemctl --user cat "$1" >/dev/null 2>&1
}

cec_warn_missing_user_service() {
  local unit="$1"
  if ! cec_optional_user_service_available "$unit"; then
    printf 'warning: optional user service %s is not installed; using toolkit fallback where available.\n' "$unit" >&2
  fi
}
