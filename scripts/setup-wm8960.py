#!/usr/bin/env python3
"""Configure the ReSpeaker 2-Mic v1 using Raspberry Pi kernel drivers.

--prepare prevents the legacy DKMS driver from rebuilding during an OS upgrade.
--apply additionally selects the kernel overlay for the next boot. Neither mode
unloads live audio modules or reboots the board.
"""

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import platform
import re
import subprocess
import tarfile


OVERLAY = "dtoverlay=wm8960-soundcard,alsaname=seeed-2mic-voicecard"
SPI = "dtparam=spi=on"
PLAYBACK_PCM = "assistant_wm8960"
PLAYBACK_CONFIG = '''# Match the assistant's 32-bit microphone stream on the shared WM8960 bus.
pcm.assistant_wm8960 {
    type plug
    slave {
        pcm "hw:CARD=seeed2micvoicec,DEV=0"
        format S32_LE
        channels 2
    }
}
'''
LEGACY_MODULES = {"snd-soc-seeed-voicecard", "snd-soc-ac108", "snd-soc-ac101", "snd-soc-wm8960"}


def boot_config(text: str) -> str:
    """Replace only this card's legacy/managed overlays; retain other settings."""
    lines = []
    for line in text.splitlines():
        match = re.match(r"\s*dtoverlay\s*=\s*([^,\s#]+)", line)
        if match and match[1] in {"seeed-2mic-voicecard", "wm8960-soundcard", "i2s-mmap"}:
            continue
        if re.match(r"\s*dtparam\s*=\s*spi=(?:on|off)\s*(?:#.*)?$", line):
            continue
        lines.append(line)
    # config.txt may end in a board-specific conditional section.
    result = "\n".join(lines).rstrip()
    if not result.endswith("[all]"):
        result += "\n\n[all]"
    # The retired vendor service enabled SPI dynamically for the HAT LEDs.
    return result + "\n" + SPI + "\n" + OVERLAY + "\n"


def module_config(text: str) -> str:
    lines = []
    for line in text.splitlines():
        name = line.split("#", 1)[0].strip().replace("_", "-")
        if name not in LEGACY_MODULES:
            lines.append(line)
    return "\n".join(lines) + "\n"


def dkms_config(text: str) -> str:
    lines = [line for line in text.splitlines() if not re.match(r"\s*AUTOINSTALL\s*=", line)]
    return "\n".join(lines).rstrip() + '\nAUTOINSTALL="no"\n'


def assistant_config(text: str, cards: str) -> str:
    """Keep the selected WM8960 output stable and match its capture word size."""
    card = re.search(r"^\s*(\d+)\s+\[seeed2micvoicec\s*\]", cards, re.M)
    if card is None:
        return text
    output = False
    lines = []
    for line in text.splitlines(keepends=True):
        section = re.match(r"\s*\[([^]]+)\]", line)
        if section:
            output = section[1] == "audio_output"
        body = line.rstrip("\r\n")
        ending = line[len(body):]
        device = re.match(r"(\s*device\s*=\s*)((?:plug)?hw:[^\s#;]+)(\s*(?:[#;].*)?)$", body)
        selected = {f"{kind}:{address}" for kind in ("hw", "plughw")
                    for address in (f"{card[1]},0", "CARD=seeed2micvoicec,DEV=0", "seeed2micvoicec,0")}
        if output and device and device[2] in selected:
            line = device[1] + PLAYBACK_PCM + device[3] + ending
        lines.append(line)
    return "".join(lines)


def snapshot(paths: list[Path]) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = Path("/var/backups/rpi-assistant-audio") / stamp
    destination.mkdir(parents=True, mode=0o700)
    # Preserve symlinks and their targets (notably modules.conf and ALSA state).
    included = set()
    with tarfile.open(destination / "configuration.tar.gz", "w:gz") as archive:
        for path in paths:
            for item in (path, path.resolve()):
                if (item.exists() or item.is_symlink()) and str(item) not in included:
                    archive.add(item, arcname=str(item).lstrip("/"))
                    included.add(str(item))
    print(f"Configuration snapshot: {destination}")
    return destination


def run(*args: str) -> None:
    subprocess.run(args, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--assistant-config", type=Path, help="Preserve numeric WM8960 output selection across reboot")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Run as root on the target Pi.")
    if platform.machine() != "aarch64":
        parser.error("This setup targets Raspberry Pi OS 64-bit (aarch64).")
    model = Path("/proc/device-tree/model")
    if not model.exists() or "Raspberry Pi" not in model.read_text():
        parser.error("This setup requires a Raspberry Pi.")

    config = Path("/boot/firmware/config.txt")
    if not config.exists():
        parser.error("Expected Raspberry Pi OS boot configuration at /boot/firmware/config.txt.")
    current = config.read_text()
    # Do not silently migrate an AC108/AC101 or newer non-WM8960 HAT.
    cards = Path("/proc/asound/cards")
    detected = cards.read_text() if cards.exists() else ""
    if re.search(r"seeed[-_ ]?(?:4|6|8)mic", current + detected, re.I):
        parser.error("This script supports the WM8960 2-Mic v1 only, not AC108/AC101 cards.")
    if args.apply and not Path("/boot/firmware/overlays/wm8960-soundcard.dtbo").exists():
        parser.error("Kernel WM8960 overlay is missing; install current Raspberry Pi OS firmware first.")
    # Includes can override the managed overlay: require an explicit review.
    for line in current.splitlines():
        if re.match(r"\s*include\s+", line):
            parser.error("Review included boot configuration before using this installer.")

    modules = [Path("/etc/modules"), *Path("/etc/modules-load.d").glob("*.conf")]
    override = Path("/etc/dkms/seeed-voicecard.conf")
    playback = Path("/etc/alsa/conf.d/99-rpi-assistant-wm8960.conf")
    paths = [config, override, playback, *modules, Path("/etc/asound.conf"),
             Path("/var/lib/alsa/asound.state"), Path("/etc/voicecard")]
    if args.assistant_config is not None:
        paths.append(args.assistant_config)
    backup = snapshot(paths)
    state = subprocess.run(["systemctl", "is-enabled", "seeed-voicecard.service"],
                           capture_output=True, text=True)
    (backup / "legacy-service-state.txt").write_text(state.stdout.strip() + "\n")
    override.parent.mkdir(parents=True, exist_ok=True)
    override.write_text(dkms_config(override.read_text() if override.exists() else ""))
    if args.prepare:
        print("Legacy Seeed DKMS autoinstall disabled. Existing kernel modules are retained.")
        return

    # Fail before changing boot configuration if service disabling is unsuccessful.
    service = subprocess.run(["systemctl", "show", "-p", "LoadState", "--value",
                              "seeed-voicecard.service"], capture_output=True, text=True, check=True)
    if service.stdout.strip() != "not-found":
        run("systemctl", "disable", "seeed-voicecard.service")
    # Store the owner's current mixer settings; ALSA restores them after reboot.
    if "seeed" in detected.lower() or "wm8960" in detected.lower():
        run("alsactl", "store")
    playback.parent.mkdir(parents=True, exist_ok=True)
    playback.write_text(PLAYBACK_CONFIG)
    if args.assistant_config is not None and args.assistant_config.exists():
        original = args.assistant_config.read_text()
        updated = assistant_config(original, detected)
        if updated != original:
            args.assistant_config.write_text(updated)
            print("Selected WM8960 output now uses the stable 32-bit playback PCM.")
    config.write_text(boot_config(current))
    seen = set()
    for path in modules:
        resolved = path.resolve()
        if resolved in seen or not path.exists():
            continue
        seen.add(resolved)
        path.write_text(module_config(path.read_text()))
    print("Kernel WM8960 overlay configured for next boot; ALSA card name retained.")
    print("Reboot, then verify capture/playback and the assistant. No reboot was performed.")


if __name__ == "__main__":
    main()
