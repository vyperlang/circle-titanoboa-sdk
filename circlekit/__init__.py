"""
circlekit - Python SDK for Circle's x402 Batching, Gateway, and Wallet APIs

This SDK provides Python equivalents to Circle's TypeScript SDK
(@circlefin/x402-batching) using titanoboa for all on-chain interactions.

Key components:
- GatewayClient: Buyer-side client for deposits, payments, withdrawals
- create_gateway_middleware: Server-side payment middleware for Flask/FastAPI  
- AgentWalletManager: Circle Programmable Wallets for agent identity
- x402: Protocol helpers for parsing 402 responses and payment signatures
- boa_utils: titanoboa helpers for Arc testnet and other chains

Circle Products Used:
- Circle Gateway: Gasless batched payments
- Circle Programmable Wallets: Agent wallet identity/signing
- USDC: Payment token with EIP-3009 TransferWithAuthorization
- x402 Protocol: HTTP 402 payment negotiation

Example usage:
    from circlekit import GatewayClient, AgentWalletManager
    
    # Option 1: Use with private key (existing flow)
    client = GatewayClient(
        chain='arcTestnet',
        private_key='0x...'
    )
    
    # Option 2: Use with Circle Programmable Wallet (agent identity)
    wallet_mgr = AgentWalletManager(api_key="...", entity_secret="...")
    agent_wallet = wallet_mgr.create_wallet("my-agent", blockchain="arcTestnet")
    
    # Pay for a resource (gasless!)
    result = await client.pay('http://api.example.com/paid-endpoint')
"""

__version__ = "0.1.0"
__author__ = "circlekit contributors"

# Re-export main classes for convenience
from circlekit.client import GatewayClient
from circlekit.server import create_gateway_middleware
from circlekit.x402 import (
    parse_402_response,
    create_payment_header,
    decode_payment_header,
    is_batch_payment,
    get_verifying_contract,
    X402Response,
    PaymentRequirements,
)
from circlekit.boa_utils import (
    get_chain_config,
    get_rpc_url,
    CHAIN_CONFIGS,
)
from circlekit.constants import (
    CIRCLE_BATCHING_NAME,
    CIRCLE_BATCHING_VERSION,
    CIRCLE_BATCHING_SCHEME,
)

# Circle Programmable Wallets (agent identity management)
from circlekit.wallets import (
    AgentWalletManager,
    AgentWallet,
    create_agent_wallet_manager,
)

__all__ = [
    # Client
    "GatewayClient",
    # Server
    "create_gateway_middleware",
    # Wallets (Circle Programmable Wallets)
    "AgentWalletManager",
    "AgentWallet",
    "create_agent_wallet_manager",
    # x402 protocol
    "parse_402_response",
    "create_payment_header",
    "decode_payment_header",
    "is_batch_payment",
    "get_verifying_contract",
    "X402Response",
    "PaymentRequirements",
    # Chain utilities
    "get_chain_config",
    "get_rpc_url",
    "CHAIN_CONFIGS",
    # Constants
    "CIRCLE_BATCHING_NAME",
    "CIRCLE_BATCHING_VERSION",
    "CIRCLE_BATCHING_SCHEME",
]
