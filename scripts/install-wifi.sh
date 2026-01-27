#!/usr/bin/env bash
# WiFi Provisioning Manager Installation Script
# This sets up NetworkManager-based WiFi with AP fallback for provisioning

set -euo pipefail

# Configuration
AP_SSID="${AP_SSID:-PiAssistant-Setup}"
AP_PASSWORD="${AP_PASSWORD:-ChangeMe12345}"
AP_ADDR="${AP_ADDR:-192.168.4.1/24}"
FLASK_PORT="${FLASK_PORT:-8080}"
IFACE="${IFACE:-wlan0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV="/opt/venvs/rpi-assistant"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Pi WiFi Manager Installation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Configuration:"
echo "  AP SSID:     $AP_SSID"
echo "  AP Password: $AP_PASSWORD"
echo "  AP Address:  $AP_ADDR"
echo "  Flask Port:  $FLASK_PORT"
echo "  Interface:   $IFACE"
echo ""

echo "[1/8] Installing NetworkManager..."
sudo apt-get update
sudo apt-get install -y network-manager

echo "[2/8] Enabling NetworkManager..."
sudo systemctl enable --now NetworkManager

echo "[3/8] Checking dhcpcd configuration..."
# Only disable dhcpcd if it's managing the WiFi interface
if systemctl is-active --quiet dhcpcd; then
    if grep -q "^interface $IFACE" /etc/dhcpcd.conf 2>/dev/null; then
        echo "⚠️  WARNING: dhcpcd is managing $IFACE"
        echo "   NetworkManager conflicts with dhcpcd for WiFi management."
        echo "   Disabling dhcpcd now. If you use dhcpcd for eth0, you may need to:"
        echo "   1. Add 'denyinterfaces $IFACE' to /etc/dhcpcd.conf, or"
        echo "   2. Let NetworkManager handle all interfaces"
        echo ""
        read -p "Disable dhcpcd? [Y/n] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
            sudo systemctl disable --now dhcpcd
            echo "✓ dhcpcd disabled"
        else
            echo "⚠️  Skipping. You may need to manually configure dhcpcd to ignore $IFACE"
        fi
    else
        echo "✓ dhcpcd not managing $IFACE, leaving it enabled"
    fi
else
    echo "✓ dhcpcd not active"
fi

echo "[4/8] Installing Flask (if not already installed)..."
if ! sudo "$VENV/bin/pip" show flask >/dev/null 2>&1; then
    sudo "$VENV/bin/pip" install flask
else
    echo "Flask already installed"
fi

echo "[5/8] Installing piwifi-manager.sh script..."
sudo install -m 0755 "$PROJECT_ROOT/scripts/piwifi-manager.sh" /usr/local/bin/piwifi-manager.sh

echo "[6/8] Creating environment configuration file..."
sudo tee /etc/default/piwifi >/dev/null <<EOF
# Pi WiFi Manager Configuration
# Edit this file to change WiFi provisioning settings

IFACE=$IFACE
AP_SSID=$AP_SSID
AP_PASSWORD=$AP_PASSWORD
AP_ADDR=$AP_ADDR
FLASK_PORT=$FLASK_PORT

# Flask webapp settings
PYTHONPATH=$PROJECT_ROOT
FLASK_WORKING_DIR=$PROJECT_ROOT/rpi_assistant
FLASK_CMD=$VENV/bin/python -m rpi_assistant.piwifi.webapp
EOF

echo "[7/8] Installing systemd units..."
sudo install -m 0644 "$PROJECT_ROOT/systemd/piwifi-flask.service" /etc/systemd/system/piwifi-flask.service
sudo install -m 0644 "$PROJECT_ROOT/systemd/piwifi-manager.service" /etc/systemd/system/piwifi-manager.service

# Create drop-in directory for flask service to set ExecStart
sudo mkdir -p /etc/systemd/system/piwifi-flask.service.d
sudo tee /etc/systemd/system/piwifi-flask.service.d/exec.conf >/dev/null <<EOF
[Service]
WorkingDirectory=$PROJECT_ROOT/rpi_assistant
ExecStart=$VENV/bin/python -m rpi_assistant.piwifi.webapp
Environment="PYTHONPATH=$PROJECT_ROOT"
EOF

echo "[8/8] Enabling services..."
sudo systemctl daemon-reload
sudo systemctl enable piwifi-manager.service

# Configure environment variables via systemd drop-ins
echo "[7/7] Configuring services..."
sudo mkdir -p /etc/systemd/system/piwifi-manager.service.d
sudo tee /etc/systemd/system/piwifi-manager.service.d/override.conf >/dev/null <<EOF
[Service]
Environment=IFACE=$IFACE
Environment=AP_SSID=$AP_SSID
Environment=AP_PASSWORD=$AP_PASSWORD
Environment=AP_ADDR=$AP_ADDR
Environment=FLASK_PORT=$FLASK_PORT
EOF

sudo mkdir -p /etc/systemd/system/piwifi-flask.service.d
sudo tee /etc/systemd/system/piwifi-flask.service.d/override.conf >/dev/null <<EOF
[Service]
Environment=IFACE=$IFACE
Environment=FLASK_PORT=$FLASK_PORT
WorkingDirectory=$PROJECT_ROOT/rpi-assistant
ExecStart=$VENV/bin/python -m piwifi.webapp
EOF

sudo systemctl daemon-reload
sudo systemctl enable piwifi-manager.service

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Installation Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Configuration saved to: /etc/default/piwifi"
echo ""
echo "The WiFi manager will automatically:"
echo "  • Try to connect to known WiFi networks on boot"
echo "  • Start an AP ($AP_SSID) if no connection is found"
echo "  • Provide a web UI at http://${AP_ADDR%/*}:$FLASK_PORT"
echo ""
echo "To customize settings:"
echo "  sudo nano /etc/default/piwifi"
echo "  sudo systemctl restart piwifi-manager.service"
echo ""
echo "To start the service now:"
echo "  sudo systemctl start piwifi-manager.service"
echo ""
echo "To check status:"
echo "  sudo systemctl status piwifi-manager.service"
echo "  sudo journalctl -u piwifi-manager.service -f"
echo ""
