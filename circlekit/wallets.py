"""
Circle Developer-Controlled Wallets adapters for Signer and TxExecutor protocols.

Circle's Developer-Controlled Wallets are MPC-backed: signing happens via
Circle's API, so no private key ever leaves Circle's infrastructure.

Requires: pip install circle-titanoboa-sdk[wallets]

Usage:
    from circlekit.wallets import CircleWalletSigner, CircleTxExecutor

    signer = CircleWalletSigner(wallet_id="...", wallet_address="0x...")
    tx_executor = CircleTxExecutor(wallet_id="...", wallet_address="0x...")
    client = GatewayClient(chain="arcTestnet", signer=signer, tx_executor=tx_executor)
    result = await client.pay("https://api.example.com/paid-endpoint")
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx

from circlekit.constants import get_chain_config

try:
    from circle.web3.developer_controlled_wallets import (
        SigningApi,
        SignTypedDataRequest,
        TransactionsApi,
        WalletsApi,
    )
    from circle.web3.developer_controlled_wallets.models.abi_parameters_inner import (
        AbiParametersInner,
    )
    from circle.web3.developer_controlled_wallets.models.create_contract_execution_transaction_for_developer_request import (
        CreateContractExecutionTransactionForDeveloperRequest,
    )
    from circle.web3.developer_controlled_wallets.models.fee_level import FeeLevel
    from circle.web3.utils import (
        init_developer_controlled_wallets_client,
    )

    HAS_CIRCLE_WALLETS = True
except ImportError:
    HAS_CIRCLE_WALLETS = False
    # Stubs so the names exist at module level (enables patching in tests)
    SigningApi = None  # type: ignore[assignment,misc]
    SignTypedDataRequest = None  # type: ignore[assignment,misc]
    TransactionsApi = None  # type: ignore[assignment,misc]
    WalletsApi = None  # type: ignore[assignment,misc]
    AbiParametersInner = None  # type: ignore[assignment,misc]
    CreateContractExecutionTransactionForDeveloperRequest = None  # type: ignore[assignment,misc]
    FeeLevel = None  # type: ignore[assignment,misc]
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_to_hex(v: str | bytes) -> str:
    """Convert bytes or hex string to 0x-prefixed hex string.

    Used for AbiParametersInner values (attestation, signature).
    """
    if isinstance(v, bytes):
        if not v:
            raise ValueError("Expected non-empty bytes")
        return "0x" + v.hex()
    if not v:
        raise ValueError("Expected non-empty hex string")
    s = v if v.startswith("0x") else "0x" + v
    if len(s) <= 2:
        raise ValueError("Expected non-empty hex string")
    return s


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class CircleTransactionError(Exception):
    """Raised when a Circle transaction reaches a terminal failure state."""

    def __init__(self, transaction_id: str, state: str, error_reason: str | None = None):
        self.transaction_id = transaction_id
        self.state = state
        self.error_reason = error_reason
        detail = f": {error_reason}" if error_reason else ""
        super().__init__(f"Transaction {transaction_id} {state}{detail}")


class CircleTransactionTimeoutError(CircleTransactionError):
    """Raised when polling for a Circle transaction exceeds the timeout."""

    def __init__(self, transaction_id: str, timeout: float):
        super().__init__(transaction_id, "TIMEOUT", f"exceeded {timeout}s")
        self.timeout = timeout


# ---------------------------------------------------------------------------
# CircleTxExecutor
# ---------------------------------------------------------------------------

# Terminal states indicating a transaction has completed (success or failure)
_SUCCESS_STATES = frozenset({"CONFIRMED", "COMPLETE", "CLEARED"})
_FAILURE_STATES = frozenset({"FAILED", "CANCELLED", "DENIED"})


class CircleTxExecutor:
    """
    TxExecutor backed by Circle Developer-Controlled Wallets.

    Implements the TxExecutor protocol (circlekit.tx_executor.TxExecutor) by
    submitting contract-execution transactions via Circle's API and polling
    until they reach a terminal state.

    No private key material is ever exposed — all transactions are executed
    by Circle's MPC infrastructure.
    """

    def __init__(
        self,
        wallet_id: str,
        wallet_address: str | None = None,
        api_key: str | None = None,
        entity_secret: str | None = None,
        poll_interval: float = 1.0,
        timeout: float = 120.0,
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
        self._poll_interval = poll_interval
        self._timeout = timeout

        client = init_developer_controlled_wallets_client(
            api_key=api_key, entity_secret=entity_secret
        )
        self._transactions_api = TransactionsApi(client)
        self._wallets_api = WalletsApi(client)

        if wallet_address is not None:
            self._address = wallet_address
        else:
            response = self._wallets_api.get_wallet(id=wallet_id)
            self._address = response.data.wallet.address

        self._http = httpx.Client()

    def __repr__(self) -> str:
        return f"CircleTxExecutor(wallet_id={self._wallet_id!r}, address={self._address})"

    @property
    def address(self) -> str:
        return self._address

    # -- core helper ---------------------------------------------------------

    def _submit_and_wait(
        self,
        contract_address: str,
        abi_function_signature: str,
        abi_parameters: list[str],
    ) -> str:
        """Submit a contract-execution transaction and poll until terminal.

        Parameters are positional plain values matching the types declared in
        abi_function_signature.  The Circle API infers types from the
        signature, so each element is just the value itself — e.g.
        ``["0xAddress", "1000000"]`` for ``approve(address,uint256)``.

        All callers in this class pre-stringify values; the annotation is
        ``list[str]`` to reflect that.  ``AbiParametersInner`` itself also
        accepts ``int | bool | list`` if needed by future callers.

        Returns the on-chain tx_hash on success.
        Raises CircleTransactionError on failure or CircleTransactionTimeoutError
        if polling exceeds the configured timeout.
        """
        request = CreateContractExecutionTransactionForDeveloperRequest(
            walletId=self._wallet_id,
            contractAddress=contract_address,
            abiFunctionSignature=abi_function_signature,
            abiParameters=[AbiParametersInner(p) for p in abi_parameters],
            feeLevel=FeeLevel("HIGH"),
        )

        response = self._transactions_api.create_developer_transaction_contract_execution(request)
        tx_id = response.data.transaction.id

        deadline = time.monotonic() + self._timeout
        while True:
            poll = self._transactions_api.get_transaction(id=tx_id)
            tx = poll.data.transaction
            state = tx.state

            if state in _SUCCESS_STATES:
                result: str = tx.tx_hash
                return result

            if state in _FAILURE_STATES:
                error_reason = getattr(tx, "error_reason", None)
                raise CircleTransactionError(tx_id, state, error_reason)

            if time.monotonic() >= deadline:
                raise CircleTransactionTimeoutError(tx_id, self._timeout)

            time.sleep(self._poll_interval)

    # -- TxExecutor protocol methods -----------------------------------------

    def execute_approve(
        self, chain: str, owner: str, spender: str, amount: int, rpc_url: str | None = None
    ) -> str:
        config = get_chain_config(chain)
        return self._submit_and_wait(
            contract_address=config.usdc_address,
            abi_function_signature="approve(address,uint256)",
            abi_parameters=[spender, str(amount)],
        )

    def execute_deposit(
        self, chain: str, owner: str, amount: int, rpc_url: str | None = None
    ) -> str:
        config = get_chain_config(chain)
        return self._submit_and_wait(
            contract_address=config.gateway_address,
            abi_function_signature="deposit(address,uint256)",
            abi_parameters=[config.usdc_address, str(amount)],
        )

    def execute_deposit_for(
        self, chain: str, owner: str, depositor: str, amount: int, rpc_url: str | None = None
    ) -> str:
        config = get_chain_config(chain)
        return self._submit_and_wait(
            contract_address=config.gateway_address,
            abi_function_signature="depositFor(address,address,uint256)",
            abi_parameters=[config.usdc_address, depositor, str(amount)],
        )

    def execute_gateway_mint(
        self,
        chain: str,
        attestation: str | bytes,
        signature: str | bytes,
        rpc_url: str | None = None,
    ) -> str:
        config = get_chain_config(chain)
        att_hex = _normalize_to_hex(attestation)
        sig_hex = _normalize_to_hex(signature)
        return self._submit_and_wait(
            contract_address=config.gateway_minter,
            abi_function_signature="gatewayMint(bytes,bytes)",
            abi_parameters=[att_hex, sig_hex],
        )

    def execute_initiate_withdrawal(
        self, chain: str, owner: str, amount: int, rpc_url: str | None = None
    ) -> str:
        raise NotImplementedError("Trustless withdrawals via Circle wallets are not yet supported")

    def execute_complete_withdrawal(
        self, chain: str, owner: str, rpc_url: str | None = None
    ) -> str:
        raise NotImplementedError("Trustless withdrawals via Circle wallets are not yet supported")

    def check_allowance(
        self, chain: str, owner: str, spender: str, rpc_url: str | None = None
    ) -> int:
        config = get_chain_config(chain)
        url = rpc_url or config.rpc_url

        owner_padded = owner[2:].lower().zfill(64)
        spender_padded = spender[2:].lower().zfill(64)
        call_data = f"0xdd62ed3e{owner_padded}{spender_padded}"

        rpc_payload = {
            "jsonrpc": "2.0",
            "method": "eth_call",
            "params": [
                {"to": config.usdc_address, "data": call_data},
                "latest",
            ],
            "id": 1,
        }

        response = self._http.post(url, json=rpc_payload)
        response.raise_for_status()
        body = response.json()

        if "error" in body:
            err = body["error"]
            msg = err.get("message", err) if isinstance(err, dict) else err
            raise RuntimeError(f"RPC error from {url}: {msg}")

        hex_result = body.get("result")
        if not hex_result:
            raise RuntimeError(f"RPC response missing 'result' field from {url}")

        return int(hex_result, 16)
