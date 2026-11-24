#!/usr/bin/env python3
"""Install pinned wake and follow-up speech model assets; run once during setup, never at startup."""

import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

import openwakeword


def main() -> None:
    manifest = Path(__file__).resolve().parents[1] / "rpi_assistant/wakeword-models.json"
    destination = Path(openwakeword.__file__).parent / "resources/models"
    destination.mkdir(parents=True, exist_ok=True)
    for asset in json.loads(manifest.read_text()):
        asset_directory = (manifest.parent / "models"
                           if asset.get("destination") == "assistant" else destination)
        asset_directory.mkdir(parents=True, exist_ok=True)
        target = asset_directory / asset["file"]
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == asset["sha256"]:
            continue
        with urlopen(asset["url"], timeout=60) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != asset["sha256"]:
            raise ValueError(f"Wake model checksum mismatch: {asset['file']}")
        temporary = target.with_suffix(".download")
        temporary.write_bytes(data)
        temporary.replace(target)
        print(f"Installed {asset['file']}")
    print("Wake model assets verified.")


if __name__ == "__main__":
    main()
