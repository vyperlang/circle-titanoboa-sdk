"""
CircleWalletSigner — Developer-Controlled Wallets adapter for the Signer protocol.

Circle's Developer-Controlled Wallets are MPC-backed: signing happens via
Circle's API, so no private key ever leaves Circle's infrastructure.

Requires: pip install circle-titanoboa-sdk[wallets]

Usage:
    from circlekit.wallets import CircleWalletSigner

    signer = CircleWalletSigner(wallet_id="...", wallet_address="0x...")
    client = GatewayClient(chain="arcTestnet", signer=signer)
    result = await client.pay("https://api.example.com/paid-endpoint")
"""

from __future__ import annotations

import json
import os
from typing import Any

try:
    from circle.web3.developer_controlled_wallets import (
        SigningApi,
        SignTypedDataRequest,
        WalletsApi,
    )
    from circle.web3.utils import (
        init_developer_controlled_wallets_client,
    )

    HAS_CIRCLE_WALLETS = True
except ImportError:
    HAS_CIRCLE_WALLETS = False
    # Stubs so the names exist at module level (enables patching in tests)
    SigningApi = None  # type: ignore[assignment,misc]
    SignTypedDataRequest = None  # type: ignore[assignment,misc]
    WalletsApi = None  # type: ignore[assignment,misc]
    init_developer_controlled_wallets_client = None  # type: ignore[assignment]


class CircleWalletSigner:
    """
    Signer backed by Circle Developer-Controlled Wallets.

    Implements the Signer protocol (circlekit.signer.Signer) by calling
    Circle's signing API. No private key material is ever exposed.
    """

    def __init__(
        self,
        wallet_id: str,
        wallet_address: str | None = None,
        api_key: str | None = None,
        entity_secret: str | None = None,
    ):
        if not HAS_CIRCLE_WALLETS:
            raise ImportError(
                "circle-developer-controlled-wallets package required. "
                "Install with: pip install circle-titanoboa-sdk[wallets]"
            )

        api_key = api_key or os.environ.get("CIRCLE_API_KEY")
        entity_secret = entity_secret or os.environ.get("CIRCLE_ENTITY_SECRET")

        if not api_key:
            raise ValueError("api_key is required. Pass it directly or set CIRCLE_API_KEY env var.")
        if not entity_secret:
            raise ValueError(
                "entity_secret is required. Pass it directly or set CIRCLE_ENTITY_SECRET env var."
            )

        self._wallet_id = wallet_id

        client = init_developer_controlled_wallets_client(
            api_key=api_key, entity_secret=entity_secret
        )
        self._signing_api = SigningApi(client)
        self._wallets_api = WalletsApi(client)

        if wallet_address is not None:
            self._address = wallet_address
        else:
            # SDK returns WalletResponse with .data.wallet structure
            response = self._wallets_api.get_wallet(id=wallet_id)
            self._address = response.data.wallet.address

    def __repr__(self) -> str:
        return f"CircleWalletSigner(wallet_id={self._wallet_id!r}, address={self._address})"

    @property
    def address(self) -> str:
        return self._address

    def sign_typed_data(
        self,
        domain: dict[str, Any],
        types: dict[str, list[dict[str, str]]],
        primary_type: str,
        message: dict[str, Any],
    ) -> str:
        """Sign EIP-712 typed data via Circle's signing API."""
        # Build EIP712Domain type from the domain keys present
        domain_type: list[dict[str, str]] = []
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

        # Circle's REST API takes a JSON string for the data field
        data_json = json.dumps(full_message)

        # entitySecretCiphertext is auto-filled by the SDK's @auto_fill decorator
        # on SigningApi.sign_typed_data. The decorator calls
        # api_client.fill_entity_secret_ciphertext() which generates a fresh
        # ciphertext from the entity_secret stored in the client configuration.
        # SignTypedDataRequest.__init__ defaults it to a "#REFILL_PLACEHOLDER"
        # sentinel that the decorator detects and replaces.
        response = self._signing_api.sign_typed_data(
            SignTypedDataRequest(
                walletId=self._wallet_id,
                data=data_json,
            ),
        )

        # SignatureResponse has .data.signature (no actual_instance wrapper)
        signature: str = response.data.signature

        if not signature.startswith("0x"):
            signature = "0x" + signature

        return signature
