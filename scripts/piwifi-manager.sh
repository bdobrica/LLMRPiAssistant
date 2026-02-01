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
  # Check if the WiFi device is in connected state (not our hotspot)
  local device_state=$(nmcli -t -f DEVICE,TYPE,STATE device | awk -F: -v d="$IFACE" '$1==d && $2=="wifi"{print $3}')
  
  if [ "$device_state" != "connected" ]; then
    return 1
  fi
  
  # Make sure it's not our hotspot that's active
  local active_con=$(nmcli -t -f DEVICE,CONNECTION device | awk -F: -v d="$IFACE" '$1==d{print $2}')
  
  if [ "$active_con" = "$HOTSPOT_CON_NAME" ]; then
    return 1
  fi
  
  # Device is connected and it's not the hotspot
  return 0
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
  local connected_without_internet=false
  
  for _ in $(seq 1 "$seconds"); do
    if is_connected; then
      if internet_ok; then
        log "Connected and internet OK."
        return 0
      else
        # Connected to WiFi but no internet yet - keep waiting
        if [ "$connected_without_internet" = false ]; then
          log "Wi-Fi connected but internet not reachable (yet), waiting..."
          connected_without_internet=true
        fi
      fi
    fi
    sleep 1
  done
  
  # If we're connected but still no internet after timeout, consider it a success
  # The monitoring loop will handle internet coming back later
  if is_connected; then
    log "Connected to WiFi (internet may come up later)."
    return 0
  fi
  
  return 1
}

main() {
  log "Waiting for NetworkManager..."
  for _ in $(seq 1 20); do
    if nm_ready; then break; fi
    sleep 1
  done

  nmcli radio wifi on || true

  log "Starting continuous WiFi management loop..."
  
  while true; do
    log "Attempting to auto-connect to known Wi-Fi..."
    if try_connect_wait 25; then
      log "Connected to WiFi."
      stop_hotspot
      
      # Monitor connection while we're online
      while true; do
        sleep 5
        
        # Check if still connected
        if ! is_connected; then
          log "WiFi connection lost. Device state: $(nmcli -t -f DEVICE,STATE device | grep "^$IFACE:")"
          break
        fi
        
        # Check if internet is working (but don't break immediately if it fails)
        # Give it a few chances since internet might be temporarily unreachable
        if ! internet_ok; then
          log "Internet check failed, verifying..."
          sleep 2
          if ! internet_ok; then
            sleep 3
            if ! internet_ok; then
              log "Internet connectivity lost after multiple checks. Entering AP mode."
              break
            fi
          fi
        fi
      done
    else
      log "No WiFi connection; entering AP provisioning mode."
      start_hotspot
      
      # Stay in AP mode until a client WiFi connects
      while true; do
        sleep 5
        if is_connected; then
          if internet_ok; then
            log "Detected client Wi-Fi connected with internet. Stopping hotspot."
            stop_hotspot
            break
          else
            log "WiFi connected but no internet yet..."
          fi
        fi
      done
    fi
  done
}

main "$@"