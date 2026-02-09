#!/usr/bin/env python3
"""
Deposit USDC into the Gateway Wallet contract.

This is a prerequisite for using Circle Gateway batched payments.
The buyer must have a USDC balance in the Gateway contract to pay for resources.

Usage:
    1. Get Testnet USDC from https://faucet.circle.com (Use Arc Testnet)
    2. Set PRIVATE_KEY environment variable
    3. Run: python deposit.py --amount 0.5

Options:
    --amount, -a   Amount of USDC to deposit (default: 0.5)
    --help, -h     Show this help message

Port of: basic-paywall/deposit.ts
"""

import argparse
import asyncio
import os
import sys

# Add parent directory to path for circlekit import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from circlekit import GatewayClient


def parse_args():
    parser = argparse.ArgumentParser(
        description="Deposit USDC into Gateway Wallet",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python deposit.py              # Deposit 0.5 USDC (default)
  python deposit.py --amount 0.3 # Deposit 0.3 USDC

Get testnet USDC from: https://faucet.circle.com
        """,
    )
    parser.add_argument(
        "--amount",
        "-a",
        type=str,
        default=os.environ.get("DEPOSIT_AMOUNT", "0.5"),
        help="Amount of USDC to deposit (default: 0.5)",
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    deposit_amount = args.amount

    # Validate amount
    try:
        amount_float = float(deposit_amount)
        if amount_float <= 0:
            raise ValueError("Amount must be positive")
    except ValueError:
        print("Error: Invalid deposit amount. Must be a positive number.")
        sys.exit(1)

    # Check for private key
    private_key = os.environ.get("PRIVATE_KEY")
    if not private_key:
        print("Error: PRIVATE_KEY environment variable is required")
        sys.exit(1)

    print("\n=== Deposit USDC into Gateway Wallet ===\n")

    # Create Gateway client
    client = GatewayClient(
        chain="arcTestnet",
        private_key=private_key,
    )

    print(f"Account: {client.address}")
    print(f"Chain: {client.chain_name}")

    # Step 1: Check balances before
    print("\n1. Checking balances...")
    try:
        before = await client.get_balances()
        print(f"   Wallet USDC: {before.wallet.formatted}")
        print(f"   Gateway Available: {before.gateway.formatted_available}")
    except Exception as e:
        print(f"   ⚠️  Could not fetch balances: {e}")
        print("   Continuing with deposit anyway...")
        before = None

    # Check if enough balance
    if before and float(before.wallet.formatted) < amount_float:
        print("\n❌ Insufficient USDC balance in wallet.")
        print("   Get tokens from: https://faucet.circle.com")
        await client.close()
        return

    # Step 2: Execute deposit
    print(f"\n2. Depositing {deposit_amount} USDC...")
    try:
        result = await client.deposit(deposit_amount)
        if result.approval_tx_hash:
            print(f"   Approval Tx: {result.approval_tx_hash}")
        print(f"   Deposit Tx: {result.deposit_tx_hash}")
    except Exception as e:
        print(f"   ❌ Deposit failed: {e}")
        await client.close()
        sys.exit(1)

    # Step 3: Check balances after
    print("\n3. Updated balances:")
    try:
        after = await client.get_balances()
        print(f"   Wallet USDC: {after.wallet.formatted}")
        print(f"   Gateway Available: {after.gateway.formatted_available}")
    except Exception as e:
        print(f"   ⚠️  Could not fetch updated balances: {e}")

    print("\n✅ Done! You can now make gasless payments.\n")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
