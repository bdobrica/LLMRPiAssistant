#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C

IFACE="${IFACE:-wlan0}"
PIWIFI_PYTHON="${PIWIFI_PYTHON:-/opt/venvs/rpi-assistant/bin/python}"
HOTSPOT_CON_NAME=piwifi-hotspot
AP_NO_CLIENT_TIMEOUT="${AP_NO_CLIENT_TIMEOUT:-300}"
AP_WIFI_RETRY_INTERVAL="${AP_WIFI_RETRY_INTERVAL:-120}"
CONNECTING_FILE="${CONNECTING_FILE:-/run/piwifi/connecting}"

log() { echo "[piwifi-manager] $*"; }

nm_ready() {
    nmcli -g RUNNING general 2>/dev/null | grep -qx running
}

is_connected() {
    local state connection
    state=$(nmcli -g GENERAL.STATE device show "$IFACE" 2>/dev/null) || return 1
    connection=$(nmcli -g GENERAL.CONNECTION device show "$IFACE" 2>/dev/null) || return 1
    [[ "$state" == '100 (connected)' && "$connection" != "$HOTSPOT_CON_NAME" ]]
}

hotspot_active() {
    nmcli -g GENERAL.CONNECTION device show "$IFACE" 2>/dev/null | grep -qx "$HOTSPOT_CON_NAME"
}

has_hotspot_clients() {
    local stations
    # Interface IP addresses are not a count of associated phones. If iw fails,
    # keep setup available rather than disconnecting an unknown client.
    stations=$(iw dev "$IFACE" station dump 2>/dev/null) || return 0
    [[ "$stations" == *'Station '* ]]
}

setup_in_progress() {
    local deadline now
    [[ -f "$CONNECTING_FILE" ]] || return 1
    read -r deadline < "$CONNECTING_FILE" || true
    now=$(date +%s)
    [[ "$deadline" =~ ^[0-9]{1,12}$ ]] && ((deadline > now && deadline <= now + 180))
}

stop_hotspot() {
    # The UI is never kept alive on the joined home network.
    systemctl stop piwifi-flask.service >/dev/null 2>&1 || true
    nmcli --wait 10 connection down id "$HOTSPOT_CON_NAME" >/dev/null 2>&1 || true
}

cleanup_hotspot() {
    stop_hotspot
    nmcli --wait 10 connection delete id "$HOTSPOT_CON_NAME" >/dev/null 2>&1 || true
}

start_hotspot() {
    log 'Starting private setup hotspot.'
    "$PIWIFI_PYTHON" -m rpi_assistant.piwifi.network hotspot
    systemctl start piwifi-flask.service
}

try_connect_wait() {
    local seconds="${1:-25}"
    for ((i=0; i<seconds; i++)); do
        if is_connected; then return 0; fi
        sleep 1
    done
    return 1
}

main() {
    [[ "$AP_NO_CLIENT_TIMEOUT" =~ ^[0-9]+$ && "$AP_WIFI_RETRY_INTERVAL" =~ ^[0-9]+$ ]] || {
        log 'Invalid setup timeout configuration.'; exit 1;
    }
    trap cleanup_hotspot EXIT
    log 'Waiting for NetworkManager.'
    for _ in {1..20}; do
        if nm_ready; then break; fi
        sleep 1
    done
    nm_ready || { log 'NetworkManager unavailable.'; exit 1; }
    nmcli radio wifi on >/dev/null 2>&1
    cleanup_hotspot
    while true; do
        if try_connect_wait 25; then
            stop_hotspot
            log 'Joined Wi-Fi; setup closed. Internet availability does not reopen setup.'
            while is_connected; do sleep 5; done
        else
            start_hotspot
            local last_client last_retry now
            last_client=$(date +%s); last_retry=$last_client
            while true; do
                sleep 5
                # Give the worker time to persist the successful profile before
                # stopping its service, or to restore setup after a wrong password.
                if setup_in_progress; then continue; fi
                if is_connected; then
                    cleanup_hotspot
                    break
                fi
                if ! hotspot_active; then start_hotspot; fi
                now=$(date +%s)
                if has_hotspot_clients; then
                    last_client=$now
                    last_retry=$now
                elif (( (AP_NO_CLIENT_TIMEOUT > 0 && now - last_client >= AP_NO_CLIENT_TIMEOUT) ||
                        (AP_WIFI_RETRY_INTERVAL > 0 && now - last_retry >= AP_WIFI_RETRY_INTERVAL) )); then
                    log 'No setup clients; retrying saved Wi-Fi.'
                    cleanup_hotspot
                    break
                fi
            done
        fi
    done
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then main "$@"; fi
