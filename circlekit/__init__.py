"""
circlekit - Python SDK for Circle's x402 Batching, Gateway, and Wallet APIs

This SDK provides Python equivalents to Circle's TypeScript SDK
(@circlefin/x402-batching) using titanoboa for all on-chain interactions.

Key components:
- GatewayClient: Buyer-side client for deposits, payments, withdrawals
- create_gateway_middleware: Server-side payment middleware for Flask/FastAPI  
- x402: Protocol helpers for parsing 402 responses and payment signatures
- boa_utils: titanoboa helpers for Arc testnet and other chains

Example usage:
    from circlekit import GatewayClient
    
    client = GatewayClient(
        chain='arcTestnet',
        private_key='0x...'
    )
    
    # Check balances
    balances = await client.get_balances()
    
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
    is_batch_payment,
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

__all__ = [
    # Client
    "GatewayClient",
    # Server
    "create_gateway_middleware",
    # x402 protocol
    "parse_402_response",
    "create_payment_header", 
    "is_batch_payment",
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
