#!/usr/bin/env python3
"""
Circle Programmable Wallets Demo - Agent Identity Management

This demonstrates using Circle's Developer-Controlled Wallets SDK for
creating and managing agent wallets without handling raw private keys.

Circle handles key security; you get a wallet address for use with
GatewayClient and Vyper contract interactions via titanoboa.

Prerequisites:
    1. Circle Developer Account: https://console.circle.com
    2. API key from Circle Console (API Keys section)
    3. Entity secret (generate in Circle Console under Developer > Entity Secret)

Usage:
    export CIRCLE_API_KEY=your-api-key
    export CIRCLE_ENTITY_SECRET=your-entity-secret
    python wallet_demo.py

Circle Products Used:
    - Circle Programmable Wallets (wallet identity)
    - Integrates with Circle Gateway (for gasless payments via GatewayClient)
"""

import os
import sys

# Add parent directory to path for circlekit import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from circlekit import AgentWalletManager, create_agent_wallet_manager


def main():
    print("""
╔════════════════════════════════════════════════════════════════╗
║     Circle Programmable Wallets Demo - Agent Identity          ║
║                                                                ║
║  Creates agent wallets using Circle's Developer-Controlled     ║
║  Wallets SDK. No raw private keys needed!                      ║
╚════════════════════════════════════════════════════════════════╝
""")
    
    # ──────────────────────────────────────────────────────────────────────────
    # 1. Check Credentials
    # ──────────────────────────────────────────────────────────────────────────
    print("1. Checking credentials...")
    
    api_key = os.environ.get("CIRCLE_API_KEY")
    entity_secret = os.environ.get("CIRCLE_ENTITY_SECRET")
    
    if not api_key:
        print("""
   ❌ Error: CIRCLE_API_KEY environment variable required
   
   To get one:
   1. Go to https://console.circle.com
   2. Create a new project (or use existing)
   3. Go to "API Keys" and create a new key
   4. Export it: export CIRCLE_API_KEY=your-key-here
""")
        sys.exit(1)
    
    if not entity_secret:
        print("""
   ❌ Error: CIRCLE_ENTITY_SECRET environment variable required
   
   To generate one:
   1. Go to https://console.circle.com
   2. Navigate to "Developer" > "Entity Secret"
   3. Generate and securely store the secret
   4. Export it: export CIRCLE_ENTITY_SECRET=your-secret-here
""")
        sys.exit(1)
    
    print("   ✅ API key found")
    print("   ✅ Entity secret found")
    
    # ──────────────────────────────────────────────────────────────────────────
    # 2. Initialize Wallet Manager
    # ──────────────────────────────────────────────────────────────────────────
    print("\n2. Initializing Circle Wallet Manager...")
    
    try:
        manager = create_agent_wallet_manager(
            api_key=api_key,
            entity_secret=entity_secret,
        )
        print("   ✅ Connected to Circle API")
    except Exception as e:
        print(f"   ❌ Failed to initialize: {e}")
        sys.exit(1)
    
    # ──────────────────────────────────────────────────────────────────────────
    # 3. List or Create Wallet Set
    # ──────────────────────────────────────────────────────────────────────────
    print("\n3. Checking wallet sets...")
    
    wallet_set_id = None
    
    try:
        wallet_sets = manager.list_wallet_sets()
        print(f"   Found {len(wallet_sets)} wallet set(s)")
        
        for i, ws in enumerate(wallet_sets[:3]):
            print(f"   [{i+1}] {ws.name or 'Unnamed'}: {ws.wallet_set_id}")
        
        if wallet_sets:
            # Use existing wallet set
            wallet_set_id = wallet_sets[0].wallet_set_id
            print(f"   Using existing wallet set: {wallet_set_id}")
        else:
            # Create a new wallet set
            print("   No wallet sets found. Creating one...")
            wallet_set = manager.create_wallet_set("circlekit-demo-agents")
            wallet_set_id = wallet_set.wallet_set_id
            print(f"   ✅ Created wallet set: {wallet_set_id}")
            
    except Exception as e:
        print(f"   ⚠️  Could not list/create wallet sets: {e}")
    
    # ──────────────────────────────────────────────────────────────────────────
    # 4. List Existing Wallets
    # ──────────────────────────────────────────────────────────────────────────
    print("\n4. Listing existing wallets...")
    
    try:
        wallets = manager.list_wallets()
        print(f"   Found {len(wallets)} wallet(s)")
        
        for i, w in enumerate(wallets[:5]):  # Show first 5
            addr_short = f"{w.address[:10]}...{w.address[-6:]}" if w.address else "N/A"
            print(f"   [{i+1}] {w.name or 'Unnamed'}: {addr_short} ({w.blockchain})")
        
        if len(wallets) > 5:
            print(f"   ... and {len(wallets) - 5} more")
            
    except Exception as e:
        print(f"   ⚠️  Could not list wallets: {e}")
        wallets = []
    
    # ──────────────────────────────────────────────────────────────────────────
    # 5. Create New Agent Wallet
    # ──────────────────────────────────────────────────────────────────────────
    if wallet_set_id:
        print("\n5. Creating new agent wallet...")
        
        try:
            wallet = manager.create_wallet(
                wallet_set_id=wallet_set_id,
                name="circlekit-demo-agent",
                blockchain="arcTestnet",  # Arc Testnet (matches circlekit defaults)
            )
            
            print(f"   ✅ Created wallet successfully!")
            print(f"   Wallet ID: {wallet.wallet_id}")
            print(f"   Address:   {wallet.address}")
            print(f"   Chain:     {wallet.blockchain}")
            print(f"   State:     {wallet.state}")
            
        except Exception as e:
            print(f"   ⚠️  Could not create wallet: {e}")
    else:
        print("\n5. Skipping wallet creation (no wallet set available)")
    
    # ──────────────────────────────────────────────────────────────────────────
    # 6. Integration Example
    # ──────────────────────────────────────────────────────────────────────────
    print("\n6. Integration with circlekit-py...")
    print("""
   Circle Programmable Wallets + GatewayClient:
   
   # 1. Create wallet set (one-time)
   wallet_set = manager.create_wallet_set("my-agents")
   
   # 2. Create agent wallet (Circle manages keys)
   wallet = manager.create_wallet(
       wallet_set_id=wallet_set.wallet_set_id,
       name="my-agent",
       blockchain="arcTestnet"
   )
   
   # 3. Use wallet address for on-chain operations
   print(f"Agent address: {wallet.address}")
   
   # 4. Sign EIP-712 typed data for x402 payments
   signature = manager.sign_typed_data(
       wallet_id=wallet.wallet_id,
       typed_data={
           "domain": {...},  # USDC EIP-712 domain
           "types": {...},   # TransferWithAuthorization type
           "primaryType": "TransferWithAuthorization",
           "message": {...}  # Authorization details
       }
   )
""")
    
    print("""
╔════════════════════════════════════════════════════════════════╗
║                        Demo Complete!                          ║
║                                                                ║
║  You've seen how to:                                           ║
║  ✓ Initialize Circle Wallet Manager                            ║
║  ✓ Create/list wallet sets                                     ║
║  ✓ Create new agent wallets on Arc Testnet                     ║
║  ✓ Understand integration with GatewayClient                   ║
║                                                                ║
║  Circle Products Used:                                         ║
║  - Circle Programmable Wallets (this demo)                     ║
║  - Circle Gateway (via GatewayClient for payments)             ║
║  - USDC on Arc Testnet                                         ║
╚════════════════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    main()
