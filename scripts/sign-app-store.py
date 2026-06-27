#!/usr/bin/env python3
"""Sign a voice app store catalog with an Ed25519 private key."""

import argparse
import json
from pathlib import Path

from nacl.encoding import Base64Encoder
from nacl.signing import SigningKey

from rpi_assistant.app.app_signing import sign_catalog


def main() -> None:
    parser = argparse.ArgumentParser(description="Sign a voice app store catalog")
    parser.add_argument("index_path", type=Path, help="Path to voice_apps/index.json")
    parser.add_argument(
        "private_key",
        help="Base64-encoded Ed25519 private key seed",
    )
    parser.add_argument(
        "--key-id",
        default="default",
        help="Identifier stored alongside the signature",
    )
    args = parser.parse_args()

    payload = json.loads(args.index_path.read_text(encoding="utf-8"))
    catalog = payload.get("catalog", payload)
    signature = sign_catalog(catalog, args.private_key)
    signing_key = SigningKey(args.private_key, encoder=Base64Encoder)
    public_key = signing_key.verify_key.encode(encoder=Base64Encoder).decode("utf-8")

    signed_payload = {
        "catalog": catalog,
        "signing": {
            "algorithm": "ed25519",
            "key_id": args.key_id,
            "signature": signature,
        },
    }
    args.index_path.write_text(json.dumps(signed_payload, indent=2), encoding="utf-8")
    print(public_key)


if __name__ == "__main__":
    main()
