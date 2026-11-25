#!/usr/bin/env bash
# Install NetworkManager fallback and authenticated local phone provisioning.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV="${VENV:-/opt/venvs/rpi-assistant}"

echo 'Installing private Wi-Fi provisioning.'
sudo apt-get update
sudo apt-get install -y network-manager iw
sudo systemctl enable --now NetworkManager

if systemctl is-active --quiet dhcpcd && grep -q "^interface ${IFACE:-wlan0}" /etc/dhcpcd.conf 2>/dev/null; then
    echo 'dhcpcd manages the Wi-Fi interface. Move that interface to NetworkManager before installing provisioning.'
    exit 1
fi
if ! "$VENV/bin/python" -c 'import flask' >/dev/null 2>&1; then
    echo 'Flask is missing. Install the repository Python requirements in the chosen VENV first.'
    exit 1
fi

sudo --preserve-env=IFACE,AP_SSID,AP_ADDR,FLASK_PORT,AP_NO_CLIENT_TIMEOUT,AP_WIFI_RETRY_INTERVAL \
    "$VENV/bin/python" "$SCRIPT_DIR/configure-piwifi.py" "$PROJECT_ROOT" "$VENV"
sudo systemctl daemon-reload
sudo systemctl enable piwifi-manager.service
echo 'Installation complete. The device-specific code is preserved across updates.'
echo 'Show it privately and save it for your device label: sudo piwifi-setup-code'
echo 'Start or apply provisioning with: sudo systemctl restart piwifi-manager.service'
echo 'The setup page runs only on the setup network and closes after Wi-Fi joins.'
