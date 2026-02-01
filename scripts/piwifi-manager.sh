#!/usr/bin/env bash
set -euo pipefail

IFACE="${IFACE:-wlan0}"
AP_SSID="${AP_SSID:-PiAssistant-Setup}"
AP_PASSWORD="${AP_PASSWORD:-ChangeMe12345}"
AP_ADDR="${AP_ADDR:-192.168.4.1/24}"
FLASK_PORT="${FLASK_PORT:-8080}"

HOTSPOT_CON_NAME="piwifi-hotspot"
PING_TARGET="${PING_TARGET:-1.1.1.1}"

log() { echo "[piwifi-manager] $*"; }

nm_ready() {
  nmcli -t -f RUNNING general | grep -q '^running:yes$'
}

is_connected() {
  # Check if connected to a real WiFi network (not our hotspot)
  local active_wifi=$(nmcli -t -f NAME,TYPE connection show --active | grep ':wifi$' | cut -d: -f1 | grep -v "^$HOTSPOT_CON_NAME$")
  [ -n "$active_wifi" ]
}

internet_ok() {
  ping -c 1 -W 1 "$PING_TARGET" >/dev/null 2>&1
}

stop_hotspot() {
  if nmcli -t -f NAME connection show --active | grep -qx "$HOTSPOT_CON_NAME"; then
    log "Stopping hotspot..."
    nmcli connection down "$HOTSPOT_CON_NAME" || true
  fi
  systemctl stop piwifi-flask.service || true
}

start_hotspot() {
  log "Starting hotspot SSID=$AP_SSID ..."
  nmcli connection delete "$HOTSPOT_CON_NAME" >/dev/null 2>&1 || true

  nmcli dev wifi hotspot ifname "$IFACE" con-name "$HOTSPOT_CON_NAME" ssid "$AP_SSID" password "$AP_PASSWORD"

  nmcli connection modify "$HOTSPOT_CON_NAME" ipv4.method shared ipv4.addresses "$AP_ADDR" ipv6.method ignore

  nmcli connection down "$HOTSPOT_CON_NAME" || true
  nmcli connection up "$HOTSPOT_CON_NAME"

  log "Hotspot up. Starting Flask UI on port $FLASK_PORT ..."
  systemctl start piwifi-flask.service
}

try_connect_wait() {
  local seconds="${1:-25}"
  for _ in $(seq 1 "$seconds"); do
    if is_connected; then
      if internet_ok; then
        log "Connected and internet OK."
        return 0
      else
        log "Wi-Fi connected but internet not reachable (yet)."
        return 0
      fi
    fi
    sleep 1
  done
  return 1
}

main() {
  log "Waiting for NetworkManager..."
  for _ in $(seq 1 20); do
    if nm_ready; then break; fi
    sleep 1
  done

  nmcli radio wifi on || true

  log "Attempting to auto-connect to known Wi-Fi..."
  if try_connect_wait 25; then
    stop_hotspot
    log "All good; staying in client mode."
    exit 0
  fi

  log "No Wi-Fi connection; entering AP provisioning mode."
  start_hotspot

  while true; do
    sleep 5
    if is_connected; then
      log "Detected client Wi-Fi connected. Stopping hotspot/UI."
      stop_hotspot
      exit 0
    fi
  done
}

main "$@"