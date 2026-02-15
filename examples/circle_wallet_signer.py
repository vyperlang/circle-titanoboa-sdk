#!/usr/bin/env python3
"""
Circle Wallet Signer Example

Demonstrates gasless payments using Circle Developer-Controlled Wallets
instead of a raw private key. The signing happens via Circle's MPC API,
so no private key ever leaves Circle's infrastructure.

Prerequisites:
    pip install circle-titanoboa-sdk[wallets]

Usage:
    export CIRCLE_API_KEY=...
    export CIRCLE_ENTITY_SECRET=...
    python circle_wallet_signer.py

Get a developer-controlled wallet at: https://console.circle.com
"""

import asyncio
import os
import sys

from circlekit import GatewayClient
from circlekit.wallets import CircleWalletSigner

# ============================================================================
# CONFIGURATION
# ============================================================================

WALLET_ID = os.environ.get("CIRCLE_WALLET_ID")
WALLET_ADDRESS = os.environ.get("CIRCLE_WALLET_ADDRESS")
SERVER_URL = os.environ.get("SERVER_URL", "http://localhost:4022")

if not WALLET_ID:
    print("Error: CIRCLE_WALLET_ID environment variable is required")
    print("Usage: CIRCLE_WALLET_ID=... python circle_wallet_signer.py")
    sys.exit(1)


# ============================================================================
# MAIN
# ============================================================================


async def main():
    # Create signer backed by Circle's MPC wallets
    # CIRCLE_API_KEY and CIRCLE_ENTITY_SECRET are read from env vars automatically
    signer = CircleWalletSigner(
        wallet_id=WALLET_ID,
        wallet_address=WALLET_ADDRESS,  # optional, fetched from API if omitted
    )
    print(f"Signer: {signer}")

    # Use with GatewayClient just like a PrivateKeySigner
    async with GatewayClient(chain="arcTestnet", signer=signer) as client:
        print(f"Address: {client.address}")

        # Check balances
        balances = await client.get_balances()
        print(f"Gateway balance: {balances.gateway.formatted_available} USDC")

        # Pay for a resource (gasless!)
        result = await client.pay(f"{SERVER_URL}/api/analyze")
        print(f"Paid {result.formatted_amount} USDC (status: {result.status})")


if __name__ == "__main__":
    asyncio.run(main())
