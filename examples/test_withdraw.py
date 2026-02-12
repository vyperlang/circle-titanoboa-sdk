#!/usr/bin/env python3
"""
Test the GatewayClient.withdraw() method.

Demonstrates:
    1. Same-chain withdrawal (instant)
    2. Cross-chain withdrawal to Base Sepolia (requires ETH on Base for gas)

Usage:
    export PRIVATE_KEY=0x...
    python test_withdraw.py

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

    print("\n=== Testing GatewayClient.withdraw() ===\n")

    client = GatewayClient(
        chain="arcTestnet",
        private_key=private_key,
    )

    print(f"Account: {client.address}")
    print(f"Source Chain: {client.chain_name}")

    # Step 1: Check balances before
    print("\n1. Checking balances before withdraw...")
    try:
        before = await client.get_balances()
        print(f"   Gateway Available: {before.gateway.formatted_available} USDC")
        print(f"   Wallet USDC: {before.wallet.formatted} USDC")
    except Exception as e:
        print(f"   ⚠️  Could not fetch balances: {e}")
        await client.close()
        return

    # Check minimum balance (0.01 USDC = 10000 units)
    if before.gateway.available < 10000:
        print("\n⚠️  Insufficient Gateway balance for test. Deposit first.")
        print("   Run: python deposit.py --amount 0.5")
        await client.close()
        return

    # Step 2: Test same-chain withdrawal
    print("\n2. Testing same-chain withdrawal (instant)...")
    print("   Withdrawing 0.01 USDC from Gateway to wallet on Arc Testnet...")

    try:
        result = await client.withdraw("0.01")
        print("   ✅ Withdrawal successful!")
        print(f"   Mint Tx: {result.mint_tx_hash}")
        print(f"   Amount: {result.formatted_amount} USDC")
        print(f"   Source: {result.source_chain}")
        print(f"   Destination: {result.destination_chain}")
        print(f"   Recipient: {result.recipient}")
    except Exception as e:
        print(f"   ❌ Withdrawal failed: {e}")
        print("   (This may fail if Gateway API is not available)")

    # Step 3: Check balances after
    print("\n3. Checking balances after withdrawal...")
    try:
        after = await client.get_balances()
        print(f"   Gateway Available: {after.gateway.formatted_available} USDC")

        gateway_change = (after.gateway.available - before.gateway.available) / 1e6
        wallet_change = (after.wallet.balance - before.wallet.balance) / 1e6

        print(f"   Gateway Change: {gateway_change:+.6f} USDC")
        print(f"   Wallet USDC: {after.wallet.formatted} USDC")
        print(f"   Wallet Change: {wallet_change:+.6f} USDC")
    except Exception as e:
        print(f"   ⚠️  Could not fetch updated balances: {e}")

    # Step 4: Cross-chain example (not executed)
    print("\n4. Cross-chain withdrawal example (not executed):")
    print("")
    print("   # Withdraw 0.02 USDC to Base Sepolia - requires ETH on Base for gas!")
    print('   # result = await client.withdraw("0.02", chain="baseSepolia")')
    print('   # print(f"Mint Tx: {result.mint_tx_hash}")')
    print("")
    print("   To run this, ensure you have ETH on Base Sepolia for the mint transaction gas.")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
