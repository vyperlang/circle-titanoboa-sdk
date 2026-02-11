"""
Optional integration with the standard x402 Python package.

Requires: pip install x402[httpx]

Usage:
    from circlekit.x402_integration import create_resource_server

    server = create_resource_server(is_testnet=True)
    server.initialize()  # sync — fetches supported kinds from Gateway API

    # Use with FastAPI, Flask, or any x402 middleware
"""

from typing import Optional


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
