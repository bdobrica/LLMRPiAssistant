"""Helpers for signing and verifying app-store catalogs."""

import base64
import json
from typing import Any, Dict

from nacl.encoding import Base64Encoder
from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey


def canonicalize_catalog(catalog: Dict[str, Any]) -> bytes:
    """Serialize catalog data into a stable byte representation for signing."""
    return json.dumps(catalog, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_catalog(catalog: Dict[str, Any], private_key_base64: str) -> str:
    """Sign a catalog with an Ed25519 private key encoded as Base64."""
    signing_key = SigningKey(private_key_base64, encoder=Base64Encoder)
    signature = signing_key.sign(canonicalize_catalog(catalog)).signature
    return base64.b64encode(signature).decode("utf-8")


def verify_catalog_signature(
    catalog: Dict[str, Any],
    signature_base64: str,
    public_key_base64: str,
) -> None:
    """Verify a catalog signature with an Ed25519 public key encoded as Base64."""
    verify_key = VerifyKey(public_key_base64, encoder=Base64Encoder)
    signature = base64.b64decode(signature_base64.encode("utf-8"))

    try:
        verify_key.verify(canonicalize_catalog(catalog), signature)
    except BadSignatureError as exc:
        raise ValueError("Catalog signature verification failed") from exc
