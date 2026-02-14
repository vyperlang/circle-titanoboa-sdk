#!/usr/bin/env python3
"""
Check all Gateway and wallet balances.

Usage:
    export PRIVATE_KEY=0x...
    python check_balances.py

This shows balances on Arc Testnet and Base Sepolia.

"""

import asyncio
import os
import sys

# Add parent directory to path for circlekit import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from circlekit import GatewayClient


async def main():
    private_key = os.environ.get("PRIVATE_KEY")

    if not private_key:
        print("Error: PRIVATE_KEY environment variable is required")
        sys.exit(1)

    # Create clients for each chain
    arc_client = GatewayClient(
        chain="arcTestnet",
        private_key=private_key,
    )

    base_client = GatewayClient(
        chain="baseSepolia",
        private_key=private_key,
    )

    print("\n=== Current Balances ===\n")
    print(f"Account: {arc_client.address}\n")

    # Arc Testnet
    print("--- Arc Testnet ---")
    try:
        arc_balances = await arc_client.get_balances()
        print(f"Wallet USDC:        {arc_balances.wallet.formatted}")
        print(f"Gateway Total:      {arc_balances.gateway.formatted_total}")
        print(f"Gateway Available:  {arc_balances.gateway.formatted_available}")
        print(
            f"Gateway Withdrawing: {arc_balances.gateway.formatted_withdrawing} (trustless in progress)"
        )
        print(
            f"Gateway Withdrawable: {arc_balances.gateway.formatted_withdrawable} (trustless ready)"
        )
    except Exception as e:
        print(f"⚠️  Could not fetch Arc balances: {e}")
        arc_balances = None

    # Base Sepolia
    print("\n--- Base Sepolia ---")
    try:
        base_balances = await base_client.get_balances()
        print(f"Wallet USDC:        {base_balances.wallet.formatted}")
        print(f"Gateway Total:      {base_balances.gateway.formatted_total}")
        print(f"Gateway Available:  {base_balances.gateway.formatted_available}")
    except Exception as e:
        print(f"⚠️  Could not fetch Base balances: {e}")
        base_balances = None

    # Summary
    print("\n--- Summary ---")
    if arc_balances and base_balances:
        total_wallet = (arc_balances.wallet.balance + base_balances.wallet.balance) / 1e6
        total_gateway = (arc_balances.gateway.available + base_balances.gateway.available) / 1e6
        print(f"Total Wallet USDC:      {total_wallet:.6f}")
        print(f"Total Gateway Available: {total_gateway:.6f}")
    else:
        print("Could not calculate totals due to fetch errors above.")

    await arc_client.close()
    await base_client.close()


if __name__ == "__main__":
    asyncio.run(main())
