.PHONY: setup update upgrade-os prepare-audio install-deps create-venv update-python install-voicecard install-assistant install-wifi install-service restart-service install-wakeword-models test-mcp reboot-prompt help

# Variables
SHELL_PWD := $(shell pwd)
VENV_DIR := /opt/venvs/rpi-assistant
PYTHON := $(VENV_DIR)/bin/python3
PIP := $(VENV_DIR)/bin/pip
APP_DIR := $(SHELL_PWD)/rpi_assistant
REQUIREMENTS_FILE := $(APP_DIR)/requirements.txt
SCRIPTS_DIR := $(SHELL_PWD)/scripts
SYSTEMD_DIR := $(SHELL_PWD)/systemd

# Default target
help:
	@echo "Available targets:"
	@echo "  make setup             - Complete installation and setup"
	@echo "  make update            - Refresh an existing installation after pulling new code"
	@echo "  make upgrade-os        - Update Raspberry Pi OS and configure WM8960 audio (reboot separately)"
	@echo "  make prepare-audio     - Snapshot audio config and disable legacy Seeed DKMS rebuilds"
	@echo "  make install-deps      - Install system dependencies"
	@echo "  make create-venv       - Create Python virtual environment"
	@echo "  make update-python     - Update Python packages in the existing virtual environment"
	@echo "  make install-voicecard - Configure kernel WM8960 overlay for ReSpeaker 2-Mic v1"
	@echo "  make install-assistant - Install rpi-assistant as CLI command"
	@echo "  make install-service   - Install rpi-assistant as systemd service"
	@echo "  make restart-service   - Restart the installed rpi-assistant service if it is running"
	@echo "  make install-wifi      - Install WiFi provisioning manager"
	@echo "  make install-wakeword-models - Download and verify pinned wake model assets"
	@echo "  make test-mcp          - Run generic MCP manager and tool-loop tests"

test-mcp:
	PYTHONPATH=$(SHELL_PWD) $(PYTHON) -m unittest \
		tests.test_mcp_manager tests.test_openai_client tests.test_config

# Complete setup
setup:
	$(MAKE) prepare-audio
	$(MAKE) install-deps
	$(MAKE) create-venv
	$(MAKE) install-voicecard
	$(MAKE) install-wakeword-models
	$(MAKE) install-assistant
	$(MAKE) install-service
	$(MAKE) reboot-prompt

# Update an existing installation after pulling changes
update:
	$(MAKE) install-deps
	$(MAKE) update-python
	$(MAKE) install-wakeword-models
	$(MAKE) install-assistant
	$(MAKE) install-service
	$(MAKE) restart-service

# OS/audio migration is explicit and does not change the Python environment.
# Recursive calls keep these steps ordered even with make -j.
prepare-audio:
	sudo python3 "$(SCRIPTS_DIR)/setup-wm8960.py" --prepare

upgrade-os:
	$(MAKE) prepare-audio
	sudo apt-get update
	sudo apt-get full-upgrade
	sudo apt-get install linux-image-rpi-v8 linux-headers-rpi-v8 alsa-utils libportaudio2 portaudio19-dev network-manager
	$(MAKE) install-voicecard
	@echo "OS/audio update prepared. Reboot, then run the checks in docs/audio-upgrade.md."

# Install system dependencies
install-deps:
	@echo "=== Installing system dependencies ==="
	sudo apt-get update
	sudo apt-get install -y python3-venv python3-pip libportaudio2 portaudio19-dev alsa-utils git mpg123 build-essential libffi-dev python3-dev swig libspeexdsp-dev liblgpio-dev

# Create Python virtual environment
create-venv:
	@echo "=== Creating Python virtual environment ==="
	sudo mkdir -p /opt/venvs
	sudo python3 -m venv $(VENV_DIR)
	$(MAKE) update-python

# Update Python packages inside the existing virtual environment
update-python:
	@echo "=== Updating Python packages ==="
	@if [ ! -x "$(PIP)" ]; then \
		echo "❌ Virtual environment not found at $(VENV_DIR)"; \
		echo "   Run 'make create-venv' or 'make setup' first."; \
		exit 1; \
	fi
	@echo "=== Installing Python packages ==="
	sudo env TMPDIR=/var/tmp $(PIP) install pip==26.3
	sudo env TMPDIR=/var/tmp $(PIP) install --no-cache-dir --build-constraint "$(APP_DIR)/requirements-build.txt" -r $(REQUIREMENTS_FILE)

# Use kernel-provided WM8960 support; never run the obsolete vendor installer.
install-voicecard:
	sudo python3 "$(SCRIPTS_DIR)/setup-wm8960.py" --apply --assistant-config "$(APP_DIR)/config.ini"

# Install rpi-assistant as CLI command
install-assistant:
	@echo "=== Installing rpi-assistant CLI command ==="
	@echo '#!/bin/bash' | sudo tee /usr/local/bin/rpi-assistant > /dev/null
	@echo 'export PYTHONPATH="$(dir $(APP_DIR))"' | sudo tee -a /usr/local/bin/rpi-assistant > /dev/null
	@echo 'exec $(PYTHON) -m rpi_assistant.app "$$@"' | sudo tee -a /usr/local/bin/rpi-assistant > /dev/null
	sudo chmod +x /usr/local/bin/rpi-assistant
	@echo "rpi-assistant command installed successfully"

# Install rpi-assistant as systemd service
install-service:
	@echo "=== Installing rpi-assistant systemd service ==="
	@# Create a temporary service file with correct paths
	@sed -e 's|WorkingDirectory=.*|WorkingDirectory=$(dir $(APP_DIR))|' \
	     -e 's|ExecStart=.*|ExecStart=$(PYTHON) -m rpi_assistant.app|' \
	     $(SYSTEMD_DIR)/rpi-assistant.service | sudo tee /etc/systemd/system/rpi-assistant.service > /dev/null
	sudo systemctl daemon-reload
	@echo "Service installed. Enable with: sudo systemctl enable rpi-assistant.service"
	@echo "Start with: sudo systemctl start rpi-assistant.service"

# Restart service if it is already installed and running
restart-service:
	@echo "=== Restarting rpi-assistant service if needed ==="
	@if sudo systemctl list-unit-files rpi-assistant.service >/dev/null 2>&1; then \
		if sudo systemctl is-active --quiet rpi-assistant.service; then \
			sudo systemctl restart rpi-assistant.service; \
			echo "✅ rpi-assistant.service restarted"; \
		else \
			echo "ℹ️  rpi-assistant.service is installed but not running; skipping restart"; \
		fi; \
	else \
		echo "ℹ️  rpi-assistant.service is not installed; skipping restart"; \
	fi

# Install WiFi provisioning manager
install-wifi:
	@echo "=== Installing WiFi provisioning manager ==="
	@bash $(SCRIPTS_DIR)/install-wifi.sh

# Fetch assets at setup time; startup never downloads models.
install-wakeword-models:
	sudo $(PYTHON) "$(SCRIPTS_DIR)/download-wakeword-models.py"

# Prompt for reboot
reboot-prompt:
	@echo ""
	@echo "========================================"
	@echo "Setup complete!"
	@echo "========================================"
	@echo ""
	@echo "The WM8960 overlay requires a reboot after initial audio setup."
	@read -p "Press any key to reboot now..." dummy
	sudo reboot
