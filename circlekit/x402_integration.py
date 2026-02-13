"""
Optional integration with the standard x402 Python package.

Requires: pip install x402[httpx]

Usage:
    from circlekit.x402_integration import create_resource_server, register_batch_scheme

    # Server-side:
    server = create_resource_server(is_testnet=True)
    server.initialize()  # sync — fetches supported kinds from Gateway API

    # Client-side (register Circle batch scheme with x402 client):
    from x402.client import x402Client
    from circlekit.signer import PrivateKeySigner
    client = x402Client()
    register_batch_scheme(client, signer=PrivateKeySigner('0x...'))
"""

from typing import Any, List, Optional

from circlekit.signer import Signer
from circlekit.x402 import BatchEvmScheme


def create_resource_server(url: Optional[str] = None, is_testnet: bool = True):
    """Create an x402 ResourceServer backed by Circle Gateway.

    Args:
        url: Custom Gateway API URL (overrides is_testnet)
        is_testnet: Use testnet Gateway API (default True)

    Returns:
        x402ResourceServer instance configured with BatchFacilitatorClient

    Raises:
        ImportError: If the x402 package is not installed
    """
    try:
        from x402.server import x402ResourceServer
    except ImportError:
        raise ImportError(
            "x402 package required for this integration. "
            "Install with: pip install x402[httpx]"
        )

    from circlekit.facilitator import BatchFacilitatorClient
    from circlekit.constants import get_gateway_api_url

    client = BatchFacilitatorClient(url=url or get_gateway_api_url(is_testnet))
    return x402ResourceServer(client)


def register_batch_scheme(
    client: Any,
    signer: Signer,
    networks: Optional[List[str]] = None,
) -> BatchEvmScheme:
    """Register the Circle Gateway batch scheme with an x402 client.

    Creates a BatchEvmScheme and registers it for each specified network
    on the x402 client via ``client.register(network, scheme)``.

    Args:
        client: An x402 client instance (x402Client or x402ClientSync)
        signer: Signer instance for EIP-712 signing
        networks: Network patterns to register for (default: ["eip155:*"])

    Returns:
        The BatchEvmScheme instance that was registered.
    """
    scheme = BatchEvmScheme(signer)
    for network in (networks or ["eip155:*"]):
        client.register(network, scheme)
    return scheme
