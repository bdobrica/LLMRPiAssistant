#!/usr/bin/env python3
"""Sign a voice app store catalog with an Ed25519 private key."""

import argparse
import json
import os
import sys
from pathlib import Path

from nacl.encoding import Base64Encoder
from nacl.signing import SigningKey

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def load_sign_catalog():
    """Import the catalog signing helper after the repo root is on sys.path."""
    from rpi_assistant.app.app_signing import sign_catalog

    return sign_catalog


def main() -> None:
    parser = argparse.ArgumentParser(description="Sign a voice app store catalog")
    parser.add_argument("index_path", type=Path, help="Path to voice_apps/index.json")
    parser.add_argument(
        "private_key",
        nargs="?",
        help="Base64-encoded Ed25519 private key seed",
    )
    parser.add_argument(
        "--key-id",
        default="default",
        help="Identifier stored alongside the signature",
    )
    parser.add_argument(
        "--private-key-env",
        default="APP_STORE_SIGNING_PRIVATE_KEY",
        help="Environment variable holding the Base64-encoded private key when the positional argument is omitted",
    )
    args = parser.parse_args()

    private_key = args.private_key or os.getenv(args.private_key_env, "")
    if not private_key:
        raise ValueError("A private signing key is required via argument or environment variable")
    private_key_bytes = private_key.encode("utf-8")

    payload = json.loads(args.index_path.read_text(encoding="utf-8"))
    catalog = payload.get("catalog", payload)
    sign_catalog = load_sign_catalog()
    signature = sign_catalog(catalog, private_key)
    signing_key = SigningKey(private_key_bytes, encoder=Base64Encoder)
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

