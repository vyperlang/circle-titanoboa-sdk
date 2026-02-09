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
    execute_approve,
    execute_deposit,
    check_allowance,
    get_usdc_balance,
    get_gateway_balance,
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
        
        Steps:
        1. Check current allowance
        2. If insufficient, approve Gateway to spend USDC
        3. Call Gateway.deposit(amount)
        
        Args:
            amount: Amount to deposit in decimal (e.g., '10.5')
            approve_amount: Amount to approve (defaults to amount)
            
        Returns:
            DepositResult with transaction hashes
            
        Note:
            This requires gas on the source chain. On Arc Testnet,
            gas is paid in USDC.
        """
        import asyncio
        
        amount_raw = parse_usdc(amount)
        approve_raw = parse_usdc(approve_amount) if approve_amount else amount_raw
        
        approval_tx_hash: Optional[str] = None
        
        # Run blocking boa operations in thread pool to not block async
        loop = asyncio.get_event_loop()
        
        # Step 1: Check current allowance
        current_allowance = await loop.run_in_executor(
            None,
            check_allowance,
            self._chain,
            self._address,
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
        
        This uses Circle Gateway's instant withdrawal API, which allows
        cross-chain withdrawals without waiting for finality.
        
        Args:
            amount: Amount to withdraw in decimal (e.g., '5.0')
            chain: Destination chain (default: same chain as client)
            recipient: Recipient address (default: your address)
            
        Returns:
            WithdrawResult with transaction info
            
        Note:
            Cross-chain withdrawals mint USDC on the destination chain.
            The recipient needs gas on that chain to receive the tokens.
        """
        amount_raw = parse_usdc(amount)
        dest_chain = chain or self._chain
        dest_recipient = recipient or self._address
        
        # Get destination chain config
        dest_config = get_chain_config(dest_chain)
        
        # Create withdrawal request via Gateway API
        # The API requires a signed message authorizing the withdrawal
        import time
        import base64
        import json as json_module
        
        # Build withdrawal request
        withdrawal_request = {
            "amount": str(amount_raw),
            "sourceChain": f"eip155:{self._config.chain_id}",
            "destinationChain": f"eip155:{dest_config.chain_id}",
            "recipient": dest_recipient,
            "sender": self._address,
        }
        
        # Sign the withdrawal request using EIP-712
        from circlekit.boa_utils import sign_typed_data
        
        domain = {
            "name": "CircleGateway",
            "version": "1",
            "chainId": self._config.chain_id,
            "verifyingContract": self._config.gateway_address,
        }
        
        types = {
            "Withdraw": [
                {"name": "amount", "type": "uint256"},
                {"name": "recipient", "type": "address"},
                {"name": "destinationDomain", "type": "uint32"},
                {"name": "nonce", "type": "uint256"},
            ]
        }
        
        nonce = int(time.time() * 1000)  # Use timestamp as nonce
        
        message = {
            "amount": amount_raw,
            "recipient": dest_recipient,
            "destinationDomain": dest_config.gateway_domain,
            "nonce": nonce,
        }
        
        signature = sign_typed_data(
            private_key=self._private_key,
            domain_data=domain,
            message_types=types,
            message_data=message,
            primary_type="Withdraw",
        )
        
        # Submit to Gateway API
        api_url = f"{self._gateway_api}/v1/withdraw"
        
        payload = {
            **withdrawal_request,
            "nonce": nonce,
            "signature": signature,
        }
        
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
        
        return WithdrawResult(
            mint_tx_hash=result.get("transactionHash", ""),
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
        address = address or self._address
        
        # Query Gateway API for balances (POST endpoint with body)
        try:
            api_url = f"{self._gateway_api}/v1/balances"
            # Gateway API requires POST with token and sources
            request_body = {
                "token": "USDC",
                "sources": [
                    {
                        "depositor": address,
                        # Omit domain to get balances from all domains
                    }
                ]
            }
            response = await self._http.post(api_url, json=request_body)
            
            if response.status_code == 200:
                data = response.json()
                
                # Gateway API returns {token: "USDC", balances: [{domain, depositor, balance}]}
                balances_list = data.get("balances", [])
                
                # Sum up all balances across domains
                total = 0
                for bal in balances_list:
                    total += int(bal.get("balance", 0))
                
                # Available is typically the same as total unless funds are locked
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
