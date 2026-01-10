.PHONY: setup install-deps create-venv install-voicecard install-assistant patch-openwakeword reboot-prompt help

# Variables
SHELL_PWD := $(shell pwd)
VENV_DIR := /opt/venvs/rpi-assistant
PYTHON := $(VENV_DIR)/bin/python3
PIP := $(VENV_DIR)/bin/pip
APP_DIR := $(SHELL_PWD)/rpi-assistant
VOICECARD_DIR := $(SHELL_PWD)/seeed-voicecard
VOICECARD_PATCH := $(SHELL_PWD)/seeed-voicecard.patch
OPENWAKEWORD_PATCH := $(SHELL_PWD)/openwakeword.patch

# Default target
help:
	@echo "Available targets:"
	@echo "  make setup          - Complete installation and setup"
	@echo "  make install-deps   - Install system dependencies"
	@echo "  make create-venv    - Create Python virtual environment"
	@echo "  make install-voicecard - Install and patch seeed-voicecard"
	@echo "  make install-assistant - Install rpi-assistant as CLI command"
	@echo "  make patch-openwakeword - Apply openwakeword bug fix patch"

# Complete setup
setup: install-deps create-venv install-voicecard patch-openwakeword install-assistant reboot-prompt

# Install system dependencies
install-deps:
	@echo "=== Installing system dependencies ==="
	sudo apt-get update
	sudo apt-get install -y python3-venv python3-pip libportaudio2 portaudio19-dev alsa-utils git mpg123

# Create Python virtual environment
create-venv:
	@echo "=== Creating Python virtual environment ==="
	sudo mkdir -p /opt/venvs
	sudo python3 -m venv $(VENV_DIR)
	@echo "=== Installing Python packages ==="
	sudo $(PIP) install --upgrade pip
	sudo $(PIP) install -r $(APP_DIR)/requirements.txt

# Clone, patch, and install seeed-voicecard
install-voicecard:
	@echo "=== Installing seeed-voicecard driver ==="
	@if [ ! -d "$(VOICECARD_DIR)" ]; then \
		echo "Cloning seeed-voicecard repository..."; \
		git clone https://github.com/seeed-studio-projects/seeed-voicecard.git; \
	else \
		echo "seeed-voicecard directory already exists"; \
	fi
	@echo "Applying patch..."
	cd seeed-voicecard && git checkout v6.14 && git apply $(VOICECARD_PATCH) || echo "Patch may already be applied"
	@echo "Running seeed-voicecard install script..."
	cd seeed-voicecard && sudo ./install.sh

# Install rpi-assistant as CLI command
install-assistant:
	@echo "=== Installing rpi-assistant CLI command ==="
	@echo '#!/bin/bash' | sudo tee /usr/local/bin/rpi-assistant > /dev/null
	@echo 'cd ${APP_DIR}' | sudo tee -a /usr/local/bin/rpi-assistant > /dev/null
	@echo 'exec $(PYTHON) -m app "$$@"' | sudo tee -a /usr/local/bin/rpi-assistant > /dev/null
	sudo chmod +x /usr/local/bin/rpi-assistant
	@echo "rpi-assistant command installed successfully"

# Apply openwakeword bug fix patch
patch-openwakeword:
	@echo "=== Applying openwakeword bug fix patch ==="
	@OPENWAKEWORD_MODEL=$$(find $(VENV_DIR)/lib -name "model.py" -path "*/openwakeword/model.py" 2>/dev/null | head -n1); \
	if [ -z "$$OPENWAKEWORD_MODEL" ]; then \
		echo "⚠️  Warning: openwakeword model.py not found. Skipping patch."; \
		echo "   Run 'make patch-openwakeword' after installing openwakeword."; \
	else \
		echo "Found openwakeword at: $$OPENWAKEWORD_MODEL"; \
		if grep -q "Fix kwargs for AudioFeatures" "$$OPENWAKEWORD_MODEL"; then \
			echo "✅ Patch already applied"; \
		else \
			echo "Applying patch..."; \
			cd "$$(dirname $$OPENWAKEWORD_MODEL)" && sudo patch -p1 < $(OPENWAKEWORD_PATCH) && \
			echo "✅ Patch applied successfully" || \
			echo "❌ Failed to apply patch"; \
		fi \
	fi

# Prompt for reboot
reboot-prompt:
	@echo ""
	@echo "========================================"
	@echo "Setup complete!"
	@echo "========================================"
	@echo ""
	@echo "The seeed-voicecard driver requires a system reboot to load kernel modules."
	@read -p "Press any key to reboot now..." dummy
	sudo reboot
