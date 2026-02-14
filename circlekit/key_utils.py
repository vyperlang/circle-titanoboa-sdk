"""
Private key validation, normalization, and account creation.

Single source of truth for private key handling across the SDK.
"""

from __future__ import annotations

import re

from eth_account import Account
from eth_account.signers.local import LocalAccount

# Type alias: accept a hex string or an already-built LocalAccount
PrivateKeyLike = str | LocalAccount

# Environment variable name used as a fallback in GatewayClient
PRIVATE_KEY_ENV_VAR = "PRIVATE_KEY"

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def normalize_private_key(key: str) -> str:
    """Normalize a hex-encoded private key to a lowercase 0x-prefixed string.

    Accepts keys with or without ``0x`` prefix, strips surrounding whitespace,
    and validates that the result is exactly 32 bytes (64 hex chars).

    Raises ``ValueError`` with a message that **never** includes key material.
    """
    if not isinstance(key, str):
        raise ValueError("Private key must be a string")

    key = key.strip()

    if key.startswith("0x") or key.startswith("0X"):
        key = key[2:]

    key = key.lower()

    if not key:
        raise ValueError("Private key must not be empty")

    if not _HEX64_RE.match(key):
        if len(key) != 64:
            raise ValueError(
                f"Private key must be exactly 32 bytes (64 hex chars), got {len(key)} chars"
            )
        raise ValueError("Private key contains invalid (non-hex) characters")

    return "0x" + key


def account_from_key_like(key: PrivateKeyLike) -> LocalAccount:
    """Create a ``LocalAccount`` from a hex string or pass through an existing one.

    Raises ``ValueError`` with a safe message on invalid input.
    """
    if isinstance(key, LocalAccount):
        return key

    normalized = normalize_private_key(key)
    account: LocalAccount = Account.from_key(normalized)
    return account
