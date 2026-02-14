"""
GatewayClient - Primary client for buyers to interact with Circle Gateway.

Usage:
    from circlekit import GatewayClient

    # Full local wallet (private_key creates both signer + tx_executor):
    client = GatewayClient(chain='arcTestnet', private_key='0x...')

    # Deposit USDC into Gateway (one-time setup, requires tx_executor)
    await client.deposit('1.0')

    # Pay for a resource (gasless, requires signer only!)
    result = await client.pay('http://api.example.com/paid')

    # Withdraw from Gateway (requires signer + tx_executor)
    result = await client.withdraw('5.0')

    # Pay-only usage (signer is enough):
    from circlekit.signer import PrivateKeySigner
    client = GatewayClient(chain='arcTestnet', signer=PrivateKeySigner('0x...'))
    result = await client.pay('http://api.example.com/paid')
"""

import asyncio
import os
import warnings
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Generic, TypeVar

import httpx

from circlekit.boa_utils import (
    format_usdc,
    parse_usdc,
)
from circlekit.boa_utils import (
    get_block_number as _boa_get_block_number,
)
from circlekit.boa_utils import (
    get_withdrawal_block as _boa_get_withdrawal_block,
)
from circlekit.boa_utils import (
    get_withdrawal_delay as _boa_get_withdrawal_delay,
)
from circlekit.constants import (
    ChainConfig,
    get_chain_config,
    get_gateway_api_url,
)
from circlekit.key_utils import PRIVATE_KEY_ENV_VAR, PrivateKeyLike
from circlekit.signer import PrivateKeySigner, Signer
from circlekit.tx_executor import BoaTxExecutor, TxExecutor
from circlekit.x402 import (
    PAYMENT_SIGNATURE_HEADER,
    PaymentPayload,
    PaymentRequirements,
    create_payment_header,
    create_payment_payload,
    decode_payment_response,
    get_payment_required,
)

# Default max fee for withdrawals: 2.01 USDC = 2_010_000 raw units
DEFAULT_WITHDRAW_MAX_FEE = 2_010_000

T = TypeVar("T")


@dataclass
class DepositResult:
    """Result of a deposit operation."""

    approval_tx_hash: str | None
    deposit_tx_hash: str
    amount: int
    formatted_amount: str
    depositor: str


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
    transfer_id: str
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
class TrustlessWithdrawalResult:
    """Result of a trustless (on-chain) withdrawal operation."""

    tx_hash: str
    amount: int
    formatted_amount: str
    withdrawal_block: int | None = None  # only set for initiate


@dataclass
class SupportsResult:
    """Result of checking if URL supports Gateway."""

    supported: bool
    requirements: dict[str, Any] | None = None
    error: str | None = None


class GatewayClient:
    """
    Primary client for buyers to interact with Circle Gateway.

    Handles:
    - Deposits: Move USDC from wallet into Gateway (requires tx_executor or private_key)
    - Payments: Pay for x402-protected resources (gasless, requires signer)
    - Withdrawals: Move USDC from Gateway back to wallet (requires signer + tx_executor)
    - Balance queries: Check wallet and Gateway balances

    Args:
        chain: Chain name (e.g., 'arcTestnet', 'baseSepolia')
        signer: Signer instance for EIP-712 signing (pay, withdraw intent)
        tx_executor: TxExecutor instance for onchain transactions (deposit, withdraw mint)
        rpc_url: Optional custom RPC URL
        private_key: Convenience shorthand — creates both PrivateKeySigner + BoaTxExecutor.
            Also accepts a ``LocalAccount`` object.  Falls back to the
            ``PRIVATE_KEY`` environment variable when both *private_key*
            and *signer* are ``None``.
    """

    def __init__(
        self,
        chain: str,
        signer: Signer | None = None,
        tx_executor: TxExecutor | None = None,
        rpc_url: str | None = None,
        private_key: PrivateKeyLike | None = None,
    ):
        self._chain = chain
        self._rpc_url = rpc_url
        self._tx_executor: TxExecutor | None

        # Env var fallback: only when both private_key and signer are absent
        if private_key is None and signer is None:
            env_key = os.environ.get(PRIVATE_KEY_ENV_VAR)
            if env_key:
                private_key = env_key

        if private_key is not None:
            pk_signer = PrivateKeySigner(private_key)
            if signer is not None and signer.address.lower() != pk_signer.address.lower():
                raise ValueError(
                    f"signer address {signer.address} does not match "
                    f"private_key address {pk_signer.address}"
                )
            self._signer = signer or pk_signer
            self._tx_executor = tx_executor or BoaTxExecutor(private_key)
        elif signer is not None:
            self._signer = signer
            self._tx_executor = tx_executor  # may be None
        else:
            raise ValueError(
                "Either signer or private_key is required "
                f"(or set the {PRIVATE_KEY_ENV_VAR} environment variable)"
            )

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
        approve_amount: str | None = None,
        skip_approval_check: bool = False,
    ) -> DepositResult:
        """
        Deposit USDC from wallet into Gateway contract.

        This is a one-time setup step. Once you have a Gateway balance,
        you can make gasless payments.

        Requires a tx_executor (or private_key) for onchain transactions.

        Args:
            amount: Amount to deposit in decimal (e.g., '10.5')
            approve_amount: Amount to approve (defaults to amount)
            skip_approval_check: Skip the allowance check and approval step
                entirely, going straight to the deposit transaction

        Returns:
            DepositResult with transaction hashes
        """
        if self._tx_executor is None:
            raise ValueError("deposit() requires a tx_executor or private_key")

        amount_raw = parse_usdc(amount)
        approve_raw = parse_usdc(approve_amount) if approve_amount else amount_raw

        # Preflight: check wallet USDC balance
        wallet = await self.get_usdc_balance()
        if wallet.balance < amount_raw:
            raise ValueError(f"Insufficient USDC balance. Have: {wallet.formatted}, Need: {amount}")

        approval_tx_hash: str | None = None

        loop = asyncio.get_event_loop()

        if not skip_approval_check:
            # Step 1: Check current allowance
            current_allowance = await loop.run_in_executor(
                None,
                self._tx_executor.check_allowance,
                self._chain,
                self.address,
                self._config.gateway_address,
                self._rpc_url,
            )

            # Step 2: Approve if needed
            if current_allowance < amount_raw:
                approval_tx_hash = await loop.run_in_executor(
                    None,
                    self._tx_executor.execute_approve,
                    self._chain,
                    self.address,
                    self._config.gateway_address,
                    approve_raw,
                    self._rpc_url,
                )

        # Step 3: Execute deposit
        deposit_tx_hash = await loop.run_in_executor(
            None,
            self._tx_executor.execute_deposit,
            self._chain,
            self.address,
            amount_raw,
            self._rpc_url,
        )

        return DepositResult(
            approval_tx_hash=approval_tx_hash,
            deposit_tx_hash=deposit_tx_hash,
            amount=amount_raw,
            formatted_amount=format_usdc(amount_raw),
            depositor=self.address,
        )

    def create_payment_payload(
        self,
        requirements: PaymentRequirements,
        x402_version: int = 1,
    ) -> PaymentPayload:
        """
        Create a signed payment payload for the given requirements.

        This is a lower-level primitive — most callers should use pay() instead,
        which handles the full 402 negotiation automatically.

        Args:
            requirements: Payment requirements (from a 402 response)
            x402_version: x402 protocol version (default: 1)

        Returns:
            PaymentPayload with signature and authorization
        """
        return create_payment_payload(self._signer, requirements, x402_version)

    async def pay(
        self,
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: Any | None = None,
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

        # If not 402, check for errors or return response as-is (free resource)
        if response.status_code != 402:
            # Non-2xx, non-402 responses are errors
            if response.status_code >= 400 or response.status_code < 200:
                raise httpx.HTTPStatusError(
                    f"Request failed with status {response.status_code}",
                    request=response.request,
                    response=response,
                )
            return PayResult(
                data=response.json()
                if response.headers.get("content-type", "").startswith("application/json")
                else response.text,
                amount=0,
                formatted_amount="0",
                transaction="",
                status=response.status_code,
            )

        # Step 2: Parse 402 response (v2 header strict, v1 body fallback)
        payment_required_header = response.headers.get("payment-required")
        x402_response = get_payment_required(payment_required_header, response.content)

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
        headers[PAYMENT_SIGNATURE_HEADER] = payment_header

        if method == "GET":
            paid_response = await self._http.get(url, headers=headers)
        else:
            paid_response = await self._http.request(method, url, headers=headers, json=body)

        # Paid response must be successful
        if paid_response.status_code >= 400 or paid_response.status_code < 200:
            raise httpx.HTTPStatusError(
                f"Payment failed with status {paid_response.status_code}",
                request=paid_response.request,
                response=paid_response,
            )

        # Parse response
        content_type = paid_response.headers.get("content-type", "")
        if content_type.startswith("application/json"):
            data = paid_response.json()
        else:
            data = paid_response.text

        # Extract transaction from PAYMENT-RESPONSE header first, then body fallback.
        # Best-effort: malformed header should not fail an otherwise successful payment.
        transaction = ""
        payment_response_header = paid_response.headers.get("payment-response")
        if payment_response_header:
            try:
                receipt = decode_payment_response(payment_response_header)
                transaction = receipt.get("transaction", "")
            except Exception:
                pass
        if not transaction and isinstance(data, dict):
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
        chain: str | None = None,
        recipient: str | None = None,
        max_fee: int | None = None,
    ) -> WithdrawResult:
        """
        Withdraw USDC from Gateway to wallet.

        Uses Circle Gateway's withdrawal flow:
        1. Create BurnIntent with nested TransferSpec (EIP-712 struct)
        2. Sign with domain {name: "GatewayWallet", version: "1"} (no chainId/verifyingContract)
        3. POST to /v1/transfer with [{burnIntent, signature}]
        4. Receive {attestation, signature} back
        5. Call gatewayMint on destination chain's minter contract

        Requires both signer (for step 2) and tx_executor (for step 5).

        Args:
            amount: Amount to withdraw in decimal (e.g., '5.0')
            chain: Destination chain (default: same chain as client)
            recipient: Recipient address (default: your address)
            max_fee: Maximum fee in raw USDC units (default: 2.01 USDC).
                     Pass 0 explicitly to override.

        Returns:
            WithdrawResult with transaction info
        """
        if self._tx_executor is None:
            raise ValueError("withdraw() requires a tx_executor or private_key")

        max_fee = max_fee if max_fee is not None else DEFAULT_WITHDRAW_MAX_FEE

        amount_raw = parse_usdc(amount)

        # Preflight: check gateway balance
        balances = await self.get_gateway_balance()
        if balances.available < amount_raw:
            raise ValueError(
                f"Insufficient available balance. Have: {balances.formatted_available}, Need: {amount}"
            )
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
            "version": 1,
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

        # EIP-712 domain for withdrawal: {name: "GatewayWallet", version: "1"}
        # No chainId or verifyingContract — withdrawal signing domain is unscoped
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
                "version": 1,
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

        # Extract attestation, signature, and transfer ID from API response
        if isinstance(result, list) and len(result) > 0:
            transfer_data = result[0]
        elif isinstance(result, dict):
            transfer_data = result
        else:
            transfer_data = {}

        # Check API-level success/error flags before attempting mint
        if transfer_data.get("success") is False:
            error_msg = transfer_data.get("error", "Unknown error")
            raise ValueError(f"Withdrawal failed: {error_msg}")
        if transfer_data.get("error"):
            raise ValueError(f"Withdrawal failed: {transfer_data['error']}")

        attestation = transfer_data.get("attestation", "")
        mint_signature = transfer_data.get("signature", "")
        transfer_id = transfer_data.get("transferId", transfer_data.get("transactionHash", ""))

        if not attestation or not mint_signature:
            raise ValueError(
                "Withdrawal API response missing attestation or signature. "
                f"Got keys: {list(transfer_data.keys())}"
            )

        # Execute gatewayMint on the destination chain.
        # Don't pass self._rpc_url — it's for the source chain. The destination
        # chain's TxExecutor/boa_utils will use its own default RPC.
        loop = asyncio.get_event_loop()
        mint_tx_hash = await loop.run_in_executor(
            None,
            self._tx_executor.execute_gateway_mint,
            dest_chain,
            attestation,
            mint_signature,
            None,
        )

        return WithdrawResult(
            mint_tx_hash=mint_tx_hash,
            transfer_id=transfer_id,
            amount=amount_raw,
            formatted_amount=format_usdc(amount_raw),
            source_chain=self._config.name,
            destination_chain=dest_config.name,
            recipient=dest_recipient,
        )

    async def get_gateway_balance(self, address: str | None = None) -> GatewayBalance:
        """
        Get Gateway balance for an address.

        Args:
            address: Address to check (default: your address)

        Returns:
            GatewayBalance with available/withdrawing/withdrawable breakdown

        Raises:
            ValueError: If the Gateway API returns an error or empty balances
        """
        address = address or self.address

        api_url = f"{self._gateway_api}/v1/balances"
        request_body = {
            "token": "USDC",
            "sources": [
                {
                    "depositor": address,
                    "domain": self._config.gateway_domain,
                }
            ],
        }
        response = await self._http.post(api_url, json=request_body)

        if response.status_code != 200:
            raise ValueError(
                f"Gateway balance query failed with status {response.status_code}: {response.text}"
            )

        data = response.json()
        balances_list = data.get("balances", [])

        if not balances_list:
            raise ValueError("Gateway balance query returned empty balances")

        def _parse_balance(val: str) -> int:
            return int(Decimal(val) * 10**6)

        balance_data = balances_list[0]
        available = _parse_balance(balance_data.get("balance", "0"))
        withdrawing = _parse_balance(balance_data.get("withdrawing", "0"))
        withdrawable = _parse_balance(balance_data.get("withdrawable", "0"))
        total = available + withdrawing

        return GatewayBalance(
            total=total,
            available=available,
            withdrawing=withdrawing,
            withdrawable=withdrawable,
            formatted_total=format_usdc(total),
            formatted_available=format_usdc(available),
            formatted_withdrawing=format_usdc(withdrawing),
            formatted_withdrawable=format_usdc(withdrawable),
        )

    async def get_usdc_balance(self, address: str | None = None) -> WalletBalance:
        """
        Get on-chain USDC wallet balance for an address.

        Args:
            address: Address to check (default: your address)

        Returns:
            WalletBalance with raw and formatted balance
        """
        address = address or self.address

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

        wallet_balance = int(result["result"], 16) if "result" in result and result["result"] else 0

        return WalletBalance(
            balance=wallet_balance,
            formatted=format_usdc(wallet_balance),
        )

    async def get_balance(self, address: str | None = None) -> GatewayBalance:
        """
        Get Gateway balance for an address.

        Alias for :meth:`get_gateway_balance`.

        Args:
            address: Address to check (default: your address)

        Returns:
            GatewayBalance with available/withdrawing/withdrawable breakdown
        """
        return await self.get_gateway_balance(address)

    async def get_balances(self, address: str | None = None) -> Balances:
        """
        Get wallet and Gateway balances.

        Args:
            address: Address to check (default: your address)

        Returns:
            Balances with wallet and Gateway info

        Raises:
            ValueError: If the Gateway API returns an error or empty balances
        """
        address = address or self.address
        gateway = await self.get_gateway_balance(address)
        wallet = await self.get_usdc_balance(address)
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

            # Parse 402 response (v2 header strict, v1 body fallback)
            payment_required_header = response.headers.get("payment-required")
            x402_response = get_payment_required(payment_required_header, response.content)
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

    async def deposit_for(
        self,
        amount: str,
        depositor: str,
        approve_amount: str | None = None,
        skip_approval_check: bool = False,
    ) -> DepositResult:
        """
        Deposit USDC into Gateway on behalf of another address.

        The caller's tokens are transferred, but credited to ``depositor``'s
        Gateway balance.  Approval is still for the caller's tokens against
        the gateway contract.

        Requires a tx_executor (or private_key) for onchain transactions.

        Args:
            amount: Amount to deposit in decimal (e.g., '10.5')
            depositor: Address to credit the deposit to
            approve_amount: Amount to approve (defaults to amount)
            skip_approval_check: Skip the allowance check and approval step
                entirely, going straight to the deposit transaction

        Returns:
            DepositResult with transaction hashes
        """
        if self._tx_executor is None:
            raise ValueError("deposit_for() requires a tx_executor or private_key")

        amount_raw = parse_usdc(amount)
        approve_raw = parse_usdc(approve_amount) if approve_amount else amount_raw

        # Preflight: check wallet USDC balance
        wallet = await self.get_usdc_balance()
        if wallet.balance < amount_raw:
            raise ValueError(f"Insufficient USDC balance. Have: {wallet.formatted}, Need: {amount}")

        approval_tx_hash: str | None = None

        loop = asyncio.get_event_loop()

        if not skip_approval_check:
            # Step 1: Check current allowance
            current_allowance = await loop.run_in_executor(
                None,
                self._tx_executor.check_allowance,
                self._chain,
                self.address,
                self._config.gateway_address,
                self._rpc_url,
            )

            # Step 2: Approve if needed
            if current_allowance < amount_raw:
                approval_tx_hash = await loop.run_in_executor(
                    None,
                    self._tx_executor.execute_approve,
                    self._chain,
                    self.address,
                    self._config.gateway_address,
                    approve_raw,
                    self._rpc_url,
                )

        # Step 3: Execute depositFor
        deposit_tx_hash = await loop.run_in_executor(
            None,
            self._tx_executor.execute_deposit_for,
            self._chain,
            self.address,
            depositor,
            amount_raw,
            self._rpc_url,
        )

        return DepositResult(
            approval_tx_hash=approval_tx_hash,
            deposit_tx_hash=deposit_tx_hash,
            amount=amount_raw,
            formatted_amount=format_usdc(amount_raw),
            depositor=depositor,
        )

    async def get_trustless_withdrawal_delay(self) -> int:
        """
        Get the trustless withdrawal delay (in blocks) from the Gateway contract.

        This is a view call and does not require a tx_executor.

        Returns:
            Withdrawal delay in blocks
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            _boa_get_withdrawal_delay,
            self._chain,
            self._rpc_url,
        )

    async def get_trustless_withdrawal_block(self, address: str | None = None) -> int:
        """
        Get the block at which a trustless withdrawal becomes completable.

        This is a view call and does not require a tx_executor.

        Args:
            address: Address to check (default: your address)

        Returns:
            Block number (0 if no pending withdrawal)
        """
        address = address or self.address
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            _boa_get_withdrawal_block,
            self._chain,
            address,
            self._rpc_url,
        )

    async def initiate_trustless_withdrawal(self, amount: str) -> TrustlessWithdrawalResult:
        """
        Initiate a trustless (on-chain) withdrawal from the Gateway contract.

        This starts the withdrawal timer. After the withdrawal delay has
        passed, call ``complete_trustless_withdrawal()`` to finalize.

        Requires a tx_executor (or private_key).

        Args:
            amount: Amount to withdraw in decimal (e.g., '5.0')

        Returns:
            TrustlessWithdrawalResult with tx_hash and withdrawal_block
        """
        if self._tx_executor is None:
            raise ValueError(
                "initiate_trustless_withdrawal() requires a tx_executor or private_key"
            )

        amount_raw = parse_usdc(amount)

        # Preflight: check gateway balance
        balances = await self.get_gateway_balance()
        if balances.available < amount_raw:
            raise ValueError(
                f"Insufficient available balance. Have: {balances.formatted_available}, Need: {amount}"
            )

        loop = asyncio.get_event_loop()
        tx_hash = await loop.run_in_executor(
            None,
            self._tx_executor.execute_initiate_withdrawal,
            self._chain,
            self.address,
            amount_raw,
            self._rpc_url,
        )

        # Read the withdrawal block after initiation
        withdrawal_block = await self.get_trustless_withdrawal_block()

        return TrustlessWithdrawalResult(
            tx_hash=tx_hash,
            amount=amount_raw,
            formatted_amount=format_usdc(amount_raw),
            withdrawal_block=withdrawal_block,
        )

    async def complete_trustless_withdrawal(self) -> TrustlessWithdrawalResult:
        """
        Complete a previously initiated trustless withdrawal.

        The withdrawal delay must have passed since ``initiate_trustless_withdrawal()``.

        Requires a tx_executor (or private_key).

        Returns:
            TrustlessWithdrawalResult with tx_hash
        """
        if self._tx_executor is None:
            raise ValueError(
                "complete_trustless_withdrawal() requires a tx_executor or private_key"
            )

        loop = asyncio.get_event_loop()

        # Preflight: check that there's something withdrawable
        balances = await self.get_gateway_balance()
        if balances.withdrawable <= 0:
            withdrawal_block = await self.get_trustless_withdrawal_block()
            if withdrawal_block == 0:
                raise ValueError("No withdrawal has been initiated.")
            current_block = await loop.run_in_executor(
                None,
                _boa_get_block_number,
                self._chain,
                self._rpc_url,
            )
            raise ValueError(
                f"Withdrawal not yet available. Current block: {current_block}, "
                f"withdrawal block: {withdrawal_block}."
            )
        tx_hash = await loop.run_in_executor(
            None,
            self._tx_executor.execute_complete_withdrawal,
            self._chain,
            self.address,
            self._rpc_url,
        )

        return TrustlessWithdrawalResult(
            tx_hash=tx_hash,
            amount=balances.withdrawable,
            formatted_amount=format_usdc(balances.withdrawable),
        )

    async def transfer(
        self,
        amount: str,
        destination_chain: str,
        recipient: str | None = None,
    ) -> WithdrawResult:
        """
        Transfer USDC from Gateway to another chain/wallet.

        .. deprecated::
            Use :meth:`withdraw` instead.  ``transfer()`` is a compatibility
            alias for :meth:`withdraw`.

        Args:
            amount: Amount to transfer in decimal (e.g., '5.0')
            destination_chain: Destination chain name
            recipient: Recipient address (default: your address)

        Returns:
            WithdrawResult with transaction info
        """
        warnings.warn(
            "transfer() is deprecated, use withdraw() instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return await self.withdraw(amount, chain=destination_chain, recipient=recipient)

    async def close(self):
        """Close the HTTP client."""
        await self._http.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
