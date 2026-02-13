"""
TxExecutor protocol and default BoaTxExecutor implementation.

TxExecutor defines the capability for executing onchain transactions
(approve, deposit, gatewayMint, allowance checks). This is separate from
the Signer protocol (EIP-712 signing for gasless intents).

BoaTxExecutor wraps the existing boa_utils helpers with a private key.
"""

from typing import Protocol, runtime_checkable

from circlekit import boa_utils


@runtime_checkable
class TxExecutor(Protocol):
    """Protocol for executing onchain transactions."""

    def execute_approve(self, chain: str, owner: str, spender: str, amount: int, rpc_url: str | None = None) -> str: ...
    def execute_deposit(self, chain: str, owner: str, amount: int, rpc_url: str | None = None) -> str: ...
    def execute_gateway_mint(self, chain: str, attestation: str | bytes, signature: str | bytes, rpc_url: str | None = None) -> str: ...
    def check_allowance(self, chain: str, owner: str, spender: str, rpc_url: str | None = None) -> int: ...


def _normalize_bytes(v: str | bytes) -> bytes:
    """Normalize hex string or bytes to bytes.

    Raises ValueError on empty input.
    """
    if isinstance(v, bytes):
        if not v:
            raise ValueError("Expected non-empty bytes")
        return v
    if not v:
        raise ValueError("Expected non-empty hex string")
    s = v
    if s.startswith("0x"):
        s = s[2:]
    if not s:
        raise ValueError("Expected non-empty hex string")
    return bytes.fromhex(s)


class BoaTxExecutor:
    """TxExecutor backed by titanoboa (requires private key)."""

    def __init__(self, private_key: str):
        self._private_key = private_key

    def execute_approve(self, chain: str, owner: str, spender: str, amount: int, rpc_url: str | None = None) -> str:
        return boa_utils.execute_approve(chain, self._private_key, spender, amount, rpc_url)

    def execute_deposit(self, chain: str, owner: str, amount: int, rpc_url: str | None = None) -> str:
        return boa_utils.execute_deposit(chain, self._private_key, amount, rpc_url)

    def execute_gateway_mint(self, chain: str, attestation: str | bytes, signature: str | bytes, rpc_url: str | None = None) -> str:
        att = _normalize_bytes(attestation)
        sig = _normalize_bytes(signature)
        return boa_utils.execute_gateway_mint(chain, self._private_key, att, sig, rpc_url)

    def check_allowance(self, chain: str, owner: str, spender: str, rpc_url: str | None = None) -> int:
        return boa_utils.check_allowance(chain, owner, spender, rpc_url)
