"""
GatewayClient - Primary client for buyers to interact with Circle Gateway.

This is the Python equivalent of the TypeScript GatewayClient from
@circlefin/x402-batching/client.

Usage:
    from circlekit import GatewayClient
    
    client = GatewayClient(
        chain='arcTestnet',
        private_key='0x...'
    )
    
    # Deposit USDC into Gateway (one-time setup)
    await client.deposit('1.0')
    
    # Pay for a resource (gasless!)
    result = await client.pay('http://api.example.com/paid')
    
    # Check balances
    balances = await client.get_balances()
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Generic, Optional, TypeVar
import httpx

from circlekit.constants import (
    ChainConfig,
    USDC_DECIMALS,
    get_gateway_api_url,
)
from circlekit.boa_utils import (
    get_chain_config,
    get_account_from_private_key,
    format_usdc,
    parse_usdc,
)
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
    - Withdrawals: Move USDC from Gateway back to wallet
    - Balance queries: Check wallet and Gateway balances
    
    Args:
        chain: Chain name (e.g., 'arcTestnet', 'baseSepolia')
        private_key: Hex-encoded private key (with or without 0x prefix)
        rpc_url: Optional custom RPC URL
    """
    
    def __init__(
        self,
        chain: str,
        private_key: str,
        rpc_url: Optional[str] = None,
    ):
        self._chain = chain
        self._private_key = private_key
        self._rpc_url = rpc_url
        
        # Get chain configuration
        self._config: ChainConfig = get_chain_config(chain)
        
        # Get account from private key
        self._address, self._account = get_account_from_private_key(private_key)
        
        # HTTP client for API calls
        self._http = httpx.AsyncClient(timeout=30.0)
        
        # Gateway API URL
        self._gateway_api = get_gateway_api_url(self._config.is_testnet)
    
    @property
    def address(self) -> str:
        """The account's wallet address."""
        return self._address
    
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
        
        Args:
            amount: Amount to deposit in decimal (e.g., '10.5')
            approve_amount: Amount to approve (defaults to amount)
            
        Returns:
            DepositResult with transaction hashes
            
        Note:
            This requires gas on the source chain.
        """
        amount_raw = parse_usdc(amount)
        approve_raw = parse_usdc(approve_amount) if approve_amount else amount_raw
        
        # For now, we'll use the Gateway API for deposits
        # In a full implementation, we'd use boa to interact with contracts directly
        
        # TODO: Implement actual on-chain deposit using titanoboa
        # 1. Approve USDC transfer to Gateway contract
        # 2. Call Gateway.deposit(amount)
        
        # Placeholder - actual implementation needs on-chain transactions
        raise NotImplementedError(
            "Direct deposit not yet implemented. "
            "Use the Gateway API or TypeScript SDK for deposits."
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
        1. Requests URL → gets 402 response
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
        
        # Step 3: Create payment signature
        payment_header = create_payment_header(
            private_key=self._private_key,
            payer_address=self._address,
            requirements=gateway_option,
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
    ) -> WithdrawResult:
        """
        Withdraw USDC from Gateway to wallet.
        
        Args:
            amount: Amount to withdraw in decimal
            chain: Destination chain (default: same chain)
            recipient: Recipient address (default: your address)
            
        Returns:
            WithdrawResult with transaction info
        """
        # TODO: Implement via Gateway API
        raise NotImplementedError(
            "Withdraw not yet implemented. "
            "Use the Gateway API or TypeScript SDK for withdrawals."
        )
    
    async def get_balances(self, address: Optional[str] = None) -> Balances:
        """
        Get wallet and Gateway balances.
        
        Args:
            address: Address to check (default: your address)
            
        Returns:
            Balances with wallet and Gateway info
        """
        address = address or self._address
        
        # Query Gateway API for balances
        try:
            api_url = f"{self._gateway_api}/v1/balances/{address}"
            response = await self._http.get(api_url)
            
            if response.status_code == 200:
                data = response.json()
                gateway_balance = data.get("balance", {})
                
                total = int(gateway_balance.get("total", 0))
                available = int(gateway_balance.get("available", 0))
                withdrawing = int(gateway_balance.get("withdrawing", 0))
                withdrawable = int(gateway_balance.get("withdrawable", 0))
                
                gateway = GatewayBalance(
                    total=total,
                    available=available,
                    withdrawing=withdrawing,
                    withdrawable=withdrawable,
                    formatted_total=format_usdc(total),
                    formatted_available=format_usdc(available),
                )
            else:
                # Fallback to zero balances
                gateway = GatewayBalance(
                    total=0,
                    available=0,
                    withdrawing=0,
                    withdrawable=0,
                    formatted_total="0.000000",
                    formatted_available="0.000000",
                )
        except Exception:
            # On error, return zero gateway balance
            gateway = GatewayBalance(
                total=0,
                available=0,
                withdrawing=0,
                withdrawable=0,
                formatted_total="0.000000",
                formatted_available="0.000000",
            )
        
        # Query on-chain USDC balance using RPC
        try:
            # Use httpx to make RPC call directly
            rpc_url = self._rpc_url or self._config.rpc_url
            
            # Encode balanceOf call
            # balanceOf(address) selector = 0x70a08231
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
        
        Args:
            url: URL to check
            
        Returns:
            SupportsResult with support status
        """
        try:
            response = await self._http.get(url)
            
            # Free resource
            if response.status_code != 402:
                return SupportsResult(
                    supported=True,
                    requirements=None,
                    error=None,
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
