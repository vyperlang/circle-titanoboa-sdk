"""
Signer protocol and default PrivateKeySigner implementation.

Circle's SDK defines a BatchEvmSigner interface with just `address` + `signTypedData()`.
This module provides the Python equivalent as a Protocol, plus a batteries-included
PrivateKeySigner for dev/testing.
"""

from typing import Any, Protocol, runtime_checkable

from eth_account import Account

from circlekit.key_utils import PrivateKeyLike, account_from_key_like


@runtime_checkable
class Signer(Protocol):
    """
    Protocol for EIP-712 signing.

    Matches Circle's BatchEvmSigner interface. Any object with an `address`
    property and a `sign_typed_data` method satisfies this protocol.
    """

    @property
    def address(self) -> str: ...

    def sign_typed_data(
        self,
        domain: dict[str, Any],
        types: dict[str, list[dict[str, str]]],
        primary_type: str,
        message: dict[str, Any],
    ) -> str: ...


class PrivateKeySigner:
    """
    Default signer using eth_account. For dev/testing.

    Wraps a raw private key and implements the Signer protocol.
    """

    def __init__(self, private_key: PrivateKeyLike):
        self._account = account_from_key_like(private_key)
        self._private_key = self._account.key

    def __repr__(self) -> str:
        return f"PrivateKeySigner(address={self._account.address})"

    @property
    def address(self) -> str:
        return str(self._account.address)

    def sign_typed_data(
        self,
        domain: dict[str, Any],
        types: dict[str, list[dict[str, str]]],
        primary_type: str,
        message: dict[str, Any],
    ) -> str:
        """
        Sign EIP-712 typed data.

        Uses eth_account's full_message form with explicit EIP712Domain type.
        """
        # Build EIP712Domain type from the domain keys present
        domain_type = []
        if "name" in domain:
            domain_type.append({"name": "name", "type": "string"})
        if "version" in domain:
            domain_type.append({"name": "version", "type": "string"})
        if "chainId" in domain:
            domain_type.append({"name": "chainId", "type": "uint256"})
        if "verifyingContract" in domain:
            domain_type.append({"name": "verifyingContract", "type": "address"})

        full_message = {
            "types": {
                "EIP712Domain": domain_type,
                **types,
            },
            "primaryType": primary_type,
            "domain": domain,
            "message": message,
        }

        signed = Account.sign_typed_data(self._private_key, full_message=full_message)
        sig_hex: str = signed.signature.hex()
        return "0x" + sig_hex
