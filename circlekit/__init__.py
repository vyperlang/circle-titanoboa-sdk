"""
circlekit - Python SDK for x402 batching with Circle Gateway APIs

This SDK provides Python equivalents to Circle's TypeScript SDK
(@circlefin/x402-batching) using titanoboa for all on-chain interactions.

Key components:
- GatewayClient: Buyer-side client for deposits, payments, withdrawals
- create_gateway_middleware: Server-side payment middleware (framework-agnostic)
- Signer/PrivateKeySigner: EIP-712 signing protocol
- TxExecutor/BoaTxExecutor: Onchain transaction execution protocol
- BatchEvmScheme: Payment payload creation
- BatchFacilitatorClient: Gateway API verify/settle
- x402: Protocol helpers for parsing 402 responses and payment signatures
- boa_utils: titanoboa helpers for Arc testnet and other chains

Example usage:
    from circlekit import GatewayClient

    # Full local wallet (creates PrivateKeySigner + BoaTxExecutor):
    client = GatewayClient(chain='arcTestnet', private_key='0x...')

    # Pay-only (signer is enough for gasless payments):
    from circlekit.signer import PrivateKeySigner
    client = GatewayClient(chain='arcTestnet', signer=PrivateKeySigner('0x...'))

    # Advanced (inject capabilities separately):
    from circlekit.tx_executor import BoaTxExecutor
    client = GatewayClient(chain='arcTestnet', signer=my_signer, tx_executor=BoaTxExecutor('0x...'))

    # Pay for a resource (gasless!)
    result = await client.pay('http://api.example.com/paid-endpoint')
"""

__version__ = "0.1.0"
__author__ = "circlekit contributors"

# Re-export main classes for convenience
from circlekit.client import GatewayClient, TrustlessWithdrawalResult
from circlekit.server import create_gateway_middleware
from circlekit.signer import Signer, PrivateKeySigner
from circlekit.tx_executor import TxExecutor, BoaTxExecutor
from circlekit.facilitator import BatchFacilitatorClient
from circlekit.x402 import (
    parse_402_response,
    create_payment_header,
    decode_payment_header,
    is_batch_payment,
    get_verifying_contract,
    BatchEvmScheme,
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

# x402 integration (x402 package is imported lazily inside create_resource_server)
from circlekit.x402_integration import create_resource_server, register_batch_scheme

__all__ = [
    # Client
    "GatewayClient",
    "TrustlessWithdrawalResult",
    # Server
    "create_gateway_middleware",
    # Signer
    "Signer",
    "PrivateKeySigner",
    # TxExecutor
    "TxExecutor",
    "BoaTxExecutor",
    # Facilitator
    "BatchFacilitatorClient",
    # x402 protocol
    "parse_402_response",
    "create_payment_header",
    "decode_payment_header",
    "is_batch_payment",
    "get_verifying_contract",
    "BatchEvmScheme",
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
    # x402 integration (optional)
    "create_resource_server",
    "register_batch_scheme",
]
