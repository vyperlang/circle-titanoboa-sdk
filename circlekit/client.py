"""
GatewayClient - Primary client for buyers to interact with Circle Gateway.

Usage:
    from circlekit import GatewayClient
    from circlekit.signer import PrivateKeySigner

    signer = PrivateKeySigner('0x...')
    client = GatewayClient(
        chain='arcTestnet',
        signer=signer,
    )

    # Deposit USDC into Gateway (one-time setup)
    await client.deposit('1.0')

    # Pay for a resource (gasless!)
    result = await client.pay('http://api.example.com/paid')

    # Check balances
    balances = await client.get_balances()
"""

import asyncio
import os
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Generic, Optional, TypeVar
import httpx

from circlekit.constants import (
    ChainConfig,
    CIRCLE_BATCHING_NAME,
    CIRCLE_BATCHING_VERSION,
    USDC_DECIMALS,
    get_gateway_api_url,
)
from circlekit.boa_utils import (
    get_chain_config,
    get_account_from_private_key,
    format_usdc,
    parse_usdc,
    execute_approve,
    execute_deposit,
    check_allowance,
    get_usdc_balance,
    get_gateway_balance,
)
from circlekit.signer import Signer, PrivateKeySigner
from circlekit.x402 import (
    parse_402_response,
    create_payment_header,
    PaymentRequirements,
    X402Response,
)


T = TypeVar("T")


@dataclass
class DepositResult:
    """Result of a deposit operation."""
    approval_tx_hash: Optional[str]
    deposit_tx_hash: str
    amount: int
    formatted_amount: str


@dataclass
class PayResult(Generic[T]):
    """Result of a pay operation."""
    data: T
    amount: int
    formatted_amount: str
    transaction: str
    status: int


@dataclass
class WithdrawResult:
    """Result of a withdraw operation."""
    mint_tx_hash: str
    amount: int
    formatted_amount: str
    source_chain: str
    destination_chain: str
    recipient: str


@dataclass
class WalletBalance:
    """Wallet USDC balance."""
    balance: int
    formatted: str


@dataclass
class GatewayBalance:
    """Gateway balance with available/locked breakdown."""
    total: int
    available: int
    withdrawing: int
    withdrawable: int
    formatted_total: str
    formatted_available: str
    formatted_withdrawing: str
    formatted_withdrawable: str


@dataclass
class Balances:
    """Combined wallet and Gateway balances."""
    wallet: WalletBalance
    gateway: GatewayBalance


@dataclass
class SupportsResult:
    """Result of checking if URL supports Gateway."""
    supported: bool
    requirements: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class GatewayClient:
    """
    Primary client for buyers to interact with Circle Gateway.

    Handles:
    - Deposits: Move USDC from wallet into Gateway
    - Payments: Pay for x402-protected resources (gasless)
    - Withdrawals: Move USDC from Gateway back to wallet (via BurnIntent)
    - Balance queries: Check wallet and Gateway balances

    Args:
        chain: Chain name (e.g., 'arcTestnet', 'baseSepolia')
        signer: Signer instance (implements Signer protocol)
        rpc_url: Optional custom RPC URL
        private_key: DEPRECATED - use signer instead. Kept for backwards compat.
    """

    def __init__(
        self,
        chain: str,
        signer: Optional[Signer] = None,
        rpc_url: Optional[str] = None,
        private_key: Optional[str] = None,
    ):
        self._chain = chain
        self._rpc_url = rpc_url

        # Support both signer and legacy private_key
        if signer is not None:
            self._signer = signer
            self._private_key = None
        elif private_key is not None:
            self._signer = PrivateKeySigner(private_key)
            self._private_key = private_key
        else:
            raise ValueError("Either signer or private_key is required")

        # Get chain configuration
        self._config: ChainConfig = get_chain_config(chain)

        # HTTP client for API calls
        self._http = httpx.AsyncClient(timeout=30.0)

        # Gateway API URL
        self._gateway_api = get_gateway_api_url(self._config.is_testnet)

    @property
    def address(self) -> str:
        """The account's wallet address."""
        return self._signer.address

    @property
    def chain_name(self) -> str:
        """Human-readable chain name."""
        return self._config.name

    @property
    def chain_id(self) -> int:
        """Chain ID."""
        return self._config.chain_id

    @property
    def domain(self) -> int:
        """Gateway domain identifier."""
        return self._config.gateway_domain

    async def deposit(
        self,
        amount: str,
        approve_amount: Optional[str] = None,
    ) -> DepositResult:
        """
        Deposit USDC from wallet into Gateway contract.

        This is a one-time setup step. Once you have a Gateway balance,
        you can make gasless payments.

        Note: Requires a private_key (not just a signer) because on-chain
        transactions go through titanoboa.

        Args:
            amount: Amount to deposit in decimal (e.g., '10.5')
            approve_amount: Amount to approve (defaults to amount)

        Returns:
            DepositResult with transaction hashes
        """
        if self._private_key is None:
            raise ValueError("deposit() requires private_key (on-chain transaction)")

        amount_raw = parse_usdc(amount)
        approve_raw = parse_usdc(approve_amount) if approve_amount else amount_raw

        approval_tx_hash: Optional[str] = None

        loop = asyncio.get_event_loop()

        # Step 1: Check current allowance
        current_allowance = await loop.run_in_executor(
            None,
            check_allowance,
            self._chain,
            self.address,
            self._config.gateway_address,
            self._rpc_url,
        )

        # Step 2: Approve if needed
        if current_allowance < amount_raw:
            approval_tx_hash = await loop.run_in_executor(
                None,
                execute_approve,
                self._chain,
                self._private_key,
                self._config.gateway_address,
                approve_raw,
                self._rpc_url,
            )

        # Step 3: Execute deposit
        deposit_tx_hash = await loop.run_in_executor(
            None,
            execute_deposit,
            self._chain,
            self._private_key,
            amount_raw,
            self._rpc_url,
        )

        return DepositResult(
            approval_tx_hash=approval_tx_hash,
            deposit_tx_hash=deposit_tx_hash,
            amount=amount_raw,
            formatted_amount=format_usdc(amount_raw),
        )

    async def pay(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        body: Optional[Any] = None,
    ) -> PayResult:
        """
        Pay for an x402-protected resource.

        Handles the full 402 negotiation automatically:
        1. Requests URL -> gets 402 response
        2. Signs payment intent (offline, gasless)
        3. Requests URL again with Payment-Signature header

        Args:
            url: URL to pay for
            method: HTTP method (default: GET)
            headers: Optional additional headers
            body: Optional request body (for POST, etc.)

        Returns:
            PayResult with response data and payment info

        Raises:
            ValueError: If URL doesn't support Gateway batching
            httpx.HTTPError: If request fails
        """
        headers = headers or {}

        # Step 1: Make initial request to get 402
        if method == "GET":
            response = await self._http.get(url, headers=headers)
        else:
            response = await self._http.request(method, url, headers=headers, json=body)

        # If not 402, return response as-is (free resource)
        if response.status_code != 402:
            return PayResult(
                data=response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text,
                amount=0,
                formatted_amount="$0.00",
                transaction="",
                status=response.status_code,
            )

        # Step 2: Parse 402 response
        x402_response = parse_402_response(response.content)

        # Find Gateway batching option
        gateway_option = x402_response.get_gateway_option()
        if not gateway_option:
            raise ValueError(
                f"URL {url} does not support Circle Gateway batching. "
                f"Available schemes: {[a.scheme for a in x402_response.accepts]}"
            )

        # Step 3: Create payment signature with resource and x402Version
        payment_header = create_payment_header(
            signer=self._signer,
            requirements=gateway_option,
            resource=x402_response.resource,
            x402_version=x402_response.x402_version,
        )

        # Step 4: Retry request with payment header
        headers["Payment-Signature"] = payment_header

        if method == "GET":
            paid_response = await self._http.get(url, headers=headers)
        else:
            paid_response = await self._http.request(method, url, headers=headers, json=body)

        # Parse response
        content_type = paid_response.headers.get("content-type", "")
        if content_type.startswith("application/json"):
            data = paid_response.json()
        else:
            data = paid_response.text

        # Extract transaction from response if available
        transaction = ""
        if isinstance(data, dict):
            payment_info = data.get("payment", {})
            transaction = payment_info.get("transaction", "")

        return PayResult(
            data=data,
            amount=int(gateway_option.amount),
            formatted_amount=gateway_option.amount_formatted,
            transaction=transaction,
            status=paid_response.status_code,
        )

    async def withdraw(
        self,
        amount: str,
        chain: Optional[str] = None,
        recipient: Optional[str] = None,
        max_fee: int = 0,
    ) -> WithdrawResult:
        """
        Withdraw USDC from Gateway to wallet.

        Uses Circle Gateway's withdrawal flow:
        1. Create BurnIntent with nested TransferSpec (EIP-712 struct)
        2. Sign with domain {name: "GatewayWallet", version: "1"} (no chainId/verifyingContract)
        3. POST to /v1/transfer with [{burnIntent, signature}]
        4. Receive {attestation, signature} back
        5. Call gatewayMint on destination chain's minter contract

        Args:
            amount: Amount to withdraw in decimal (e.g., '5.0')
            chain: Destination chain (default: same chain as client)
            recipient: Recipient address (default: your address)
            max_fee: Maximum fee in raw USDC units (default: 0)

        Returns:
            WithdrawResult with transaction info
        """
        amount_raw = parse_usdc(amount)
        dest_chain = chain or self._chain
        dest_recipient = recipient or self.address

        dest_config = get_chain_config(dest_chain)

        # Generate random salt (32 bytes)
        salt = "0x" + os.urandom(32).hex()

        # Pad addresses to bytes32 (left-pad with zeros to 32 bytes)
        def _addr_to_bytes32(addr: str) -> str:
            return "0x" + addr[2:].lower().zfill(64)

        # Zero bytes32 for unused fields
        zero_bytes32 = "0x" + "00" * 32

        # Build nested TransferSpec
        transfer_spec = {
            "version": 0,
            "sourceDomain": self._config.gateway_domain,
            "destinationDomain": dest_config.gateway_domain,
            "sourceContract": _addr_to_bytes32(self._config.gateway_address),
            "destinationContract": _addr_to_bytes32(dest_config.gateway_minter),
            "sourceToken": _addr_to_bytes32(self._config.usdc_address),
            "destinationToken": _addr_to_bytes32(dest_config.usdc_address),
            "sourceDepositor": _addr_to_bytes32(self.address),
            "destinationRecipient": _addr_to_bytes32(dest_recipient),
            "sourceSigner": _addr_to_bytes32(self.address),
            "destinationCaller": zero_bytes32,
            "value": amount_raw,
            "salt": salt,
            "hookData": "0x",
        }

        # BurnIntent wraps TransferSpec
        max_block_height = 2**256 - 1  # maxUint256

        burn_intent = {
            "maxBlockHeight": str(max_block_height),
            "maxFee": str(max_fee),
            "spec": transfer_spec,
        }

        # EIP-712 domain for withdrawal: {name: "GatewayWallet", version: "1"}
        # No chainId or verifyingContract (confirmed correct from TS)
        domain = {
            "name": "GatewayWallet",
            "version": "1",
        }

        types = {
            "BurnIntent": [
                {"name": "maxBlockHeight", "type": "uint256"},
                {"name": "maxFee", "type": "uint256"},
                {"name": "spec", "type": "TransferSpec"},
            ],
            "TransferSpec": [
                {"name": "version", "type": "uint32"},
                {"name": "sourceDomain", "type": "uint32"},
                {"name": "destinationDomain", "type": "uint32"},
                {"name": "sourceContract", "type": "bytes32"},
                {"name": "destinationContract", "type": "bytes32"},
                {"name": "sourceToken", "type": "bytes32"},
                {"name": "destinationToken", "type": "bytes32"},
                {"name": "sourceDepositor", "type": "bytes32"},
                {"name": "destinationRecipient", "type": "bytes32"},
                {"name": "sourceSigner", "type": "bytes32"},
                {"name": "destinationCaller", "type": "bytes32"},
                {"name": "value", "type": "uint256"},
                {"name": "salt", "type": "bytes32"},
                {"name": "hookData", "type": "bytes"},
            ],
        }

        signing_message = {
            "maxBlockHeight": max_block_height,
            "maxFee": max_fee,
            "spec": {
                "version": 0,
                "sourceDomain": self._config.gateway_domain,
                "destinationDomain": dest_config.gateway_domain,
                "sourceContract": _addr_to_bytes32(self._config.gateway_address),
                "destinationContract": _addr_to_bytes32(dest_config.gateway_minter),
                "sourceToken": _addr_to_bytes32(self._config.usdc_address),
                "destinationToken": _addr_to_bytes32(dest_config.usdc_address),
                "sourceDepositor": _addr_to_bytes32(self.address),
                "destinationRecipient": _addr_to_bytes32(dest_recipient),
                "sourceSigner": _addr_to_bytes32(self.address),
                "destinationCaller": zero_bytes32,
                "value": amount_raw,
                "salt": salt,
                "hookData": "0x",
            },
        }

        signature = self._signer.sign_typed_data(
            domain=domain,
            types=types,
            primary_type="BurnIntent",
            message=signing_message,
        )

        # POST to /v1/transfer
        api_url = f"{self._gateway_api}/v1/transfer"

        # Serialize burn_intent for API: convert spec values to strings
        api_spec = {
            "version": transfer_spec["version"],
            "sourceDomain": transfer_spec["sourceDomain"],
            "destinationDomain": transfer_spec["destinationDomain"],
            "sourceContract": transfer_spec["sourceContract"],
            "destinationContract": transfer_spec["destinationContract"],
            "sourceToken": transfer_spec["sourceToken"],
            "destinationToken": transfer_spec["destinationToken"],
            "sourceDepositor": transfer_spec["sourceDepositor"],
            "destinationRecipient": transfer_spec["destinationRecipient"],
            "sourceSigner": transfer_spec["sourceSigner"],
            "destinationCaller": transfer_spec["destinationCaller"],
            "value": str(amount_raw),
            "salt": transfer_spec["salt"],
            "hookData": transfer_spec["hookData"],
        }

        api_burn_intent = {
            "maxBlockHeight": str(max_block_height),
            "maxFee": str(max_fee),
            "spec": api_spec,
        }

        payload = [
            {
                "burnIntent": api_burn_intent,
                "signature": signature,
            }
        ]

        response = await self._http.post(api_url, json=payload)

        if response.status_code != 200:
            error_msg = response.text
            try:
                error_data = response.json()
                error_msg = error_data.get("error", error_msg)
            except Exception:
                pass
            raise ValueError(f"Withdrawal failed: {error_msg}")

        result = response.json()

        # The response contains attestation + signature for minting
        tx_hash = ""
        if isinstance(result, list) and len(result) > 0:
            tx_hash = result[0].get("transactionHash", "")
        elif isinstance(result, dict):
            tx_hash = result.get("transactionHash", "")

        return WithdrawResult(
            mint_tx_hash=tx_hash,
            amount=amount_raw,
            formatted_amount=format_usdc(amount_raw),
            source_chain=self._config.name,
            destination_chain=dest_config.name,
            recipient=dest_recipient,
        )

    async def get_balances(self, address: Optional[str] = None) -> Balances:
        """
        Get wallet and Gateway balances.

        Args:
            address: Address to check (default: your address)

        Returns:
            Balances with wallet and Gateway info
        """
        address = address or self.address

        # Query Gateway API for balances (POST endpoint with body)
        try:
            api_url = f"{self._gateway_api}/v1/balances"
            request_body = {
                "token": "USDC",
                "sources": [
                    {
                        "depositor": address,
                    }
                ]
            }
            response = await self._http.post(api_url, json=request_body)

            if response.status_code == 200:
                data = response.json()
                balances_list = data.get("balances", [])

                total = 0
                for bal in balances_list:
                    balance_str = bal.get("balance", "0")
                    total += int(Decimal(balance_str) * 1_000_000)

                available = total
                withdrawing = 0
                withdrawable = 0

                gateway = GatewayBalance(
                    total=total,
                    available=available,
                    withdrawing=withdrawing,
                    withdrawable=withdrawable,
                    formatted_total=format_usdc(total),
                    formatted_available=format_usdc(available),
                    formatted_withdrawing=format_usdc(withdrawing),
                    formatted_withdrawable=format_usdc(withdrawable),
                )
            else:
                gateway = GatewayBalance(
                    total=0, available=0, withdrawing=0, withdrawable=0,
                    formatted_total="0.000000", formatted_available="0.000000",
                    formatted_withdrawing="0.000000", formatted_withdrawable="0.000000",
                )
        except Exception:
            gateway = GatewayBalance(
                total=0, available=0, withdrawing=0, withdrawable=0,
                formatted_total="0.000000", formatted_available="0.000000",
                formatted_withdrawing="0.000000", formatted_withdrawable="0.000000",
            )

        # Query on-chain USDC balance using RPC
        try:
            rpc_url = self._rpc_url or self._config.rpc_url
            address_padded = address[2:].lower().zfill(64)
            call_data = f"0x70a08231{address_padded}"

            rpc_payload = {
                "jsonrpc": "2.0",
                "method": "eth_call",
                "params": [
                    {
                        "to": self._config.usdc_address,
                        "data": call_data,
                    },
                    "latest",
                ],
                "id": 1,
            }

            response = await self._http.post(rpc_url, json=rpc_payload)
            result = response.json()

            if "result" in result and result["result"]:
                wallet_balance = int(result["result"], 16)
            else:
                wallet_balance = 0

        except Exception:
            wallet_balance = 0

        wallet = WalletBalance(
            balance=wallet_balance,
            formatted=format_usdc(wallet_balance),
        )

        return Balances(wallet=wallet, gateway=gateway)

    async def supports(self, url: str) -> SupportsResult:
        """
        Check if a URL supports Gateway batching.

        Returns supported=False with error for non-402 responses.

        Args:
            url: URL to check

        Returns:
            SupportsResult with support status
        """
        try:
            response = await self._http.get(url)

            # Non-402 = does not support Gateway batching
            if response.status_code != 402:
                return SupportsResult(
                    supported=False,
                    requirements=None,
                    error="Resource does not require payment (not 402)",
                )

            # Parse 402 response
            x402_response = parse_402_response(response.content)
            gateway_option = x402_response.get_gateway_option()

            if gateway_option:
                return SupportsResult(
                    supported=True,
                    requirements={
                        "scheme": gateway_option.scheme,
                        "network": gateway_option.network,
                        "amount": gateway_option.amount,
                        "payTo": gateway_option.pay_to,
                    },
                    error=None,
                )
            else:
                return SupportsResult(
                    supported=False,
                    requirements=None,
                    error="No Gateway batching option available",
                )

        except Exception as e:
            return SupportsResult(
                supported=False,
                requirements=None,
                error=str(e),
            )

    async def close(self):
        """Close the HTTP client."""
        await self._http.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
