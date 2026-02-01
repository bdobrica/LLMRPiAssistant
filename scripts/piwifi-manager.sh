#!/usr/bin/env bash
set -euo pipefail

IFACE="${IFACE:-wlan0}"
AP_SSID="${AP_SSID:-PiAssistant-Setup}"
AP_PASSWORD="${AP_PASSWORD:-ChangeMe12345}"
AP_ADDR="${AP_ADDR:-192.168.4.1/24}"
FLASK_PORT="${FLASK_PORT:-8080}"

HOTSPOT_CON_NAME="piwifi-hotspot"
PING_TARGET="${PING_TARGET:-1.1.1.1}"

# How long to wait (in seconds) with no clients before giving up on AP mode
AP_NO_CLIENT_TIMEOUT="${AP_NO_CLIENT_TIMEOUT:-30}"
# How often to check if original WiFi is back while in AP mode
AP_WIFI_RETRY_INTERVAL="${AP_WIFI_RETRY_INTERVAL:-15}"

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

has_hotspot_clients() {
  # Check if any clients are connected to the hotspot
  local clients=$(nmcli -t -f GENERAL.STATE,IP4.ADDRESS device show "$IFACE" 2>/dev/null | grep -c "IP4.ADDRESS" || echo "0")
  # If hotspot is up and has more than just the host IP, there are clients
  [ "$clients" -gt 1 ]
}

cleanup_hotspot() {
  log "Cleaning up any existing hotspot..."
  if nmcli connection show "$HOTSPOT_CON_NAME" >/dev/null 2>&1; then
    nmcli connection down "$HOTSPOT_CON_NAME" 2>/dev/null || true
    nmcli connection delete "$HOTSPOT_CON_NAME" 2>/dev/null || true
  fi
  systemctl stop piwifi-flask.service 2>/dev/null || true
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
  
  # Clean up any leftover hotspot from previous run
  cleanup_hotspot

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
      
      # Track time with no clients
      local ap_start_time=$(date +%s)
      local last_wifi_check=$(date +%s)
      
      # Stay in AP mode monitoring for both client connections and WiFi recovery
      while true; do
        sleep 5
        local current_time=$(date +%s)
        
        # Check if a saved WiFi network connected (user clicked "Connect" in UI)
        if is_connected; then
          if internet_ok; then
            log "Detected client Wi-Fi connected with internet. Stopping hotspot."
            stop_hotspot
            break
          else
            log "WiFi connected but no internet yet..."
          fi
        else
          # Periodically try to reconnect to known WiFi networks
          local time_since_check=$((current_time - last_wifi_check))
          if [ $time_since_check -ge $AP_WIFI_RETRY_INTERVAL ]; then
            log "Checking if original WiFi networks are back..."
            last_wifi_check=$current_time
            
            # Temporarily bring down hotspot to check for WiFi
            nmcli connection down "$HOTSPOT_CON_NAME" 2>/dev/null || true
            sleep 2
            
            # See if NetworkManager auto-connects to a known network
            if is_connected && internet_ok; then
              log "Original WiFi network is back! Exiting AP mode."
              cleanup_hotspot
              break
            fi
            
            # No luck, bring hotspot back up
            nmcli connection up "$HOTSPOT_CON_NAME" 2>/dev/null || true
          fi
          
          # Check if we should give up on AP mode (no clients for too long)
          local time_in_ap=$((current_time - ap_start_time))
          if [ $time_in_ap -ge $AP_NO_CLIENT_TIMEOUT ]; then
            if ! has_hotspot_clients; then
              log "No clients connected after ${AP_NO_CLIENT_TIMEOUT}s. Likely temporary glitch. Stopping AP mode."
              cleanup_hotspot
              break
            else
              # Clients are connected, reset timer
              ap_start_time=$current_time
            fi
          fi
        fi
      done
    fi
  done
}

main "$@"