#!/usr/bin/env python3
"""
Agent Client Example

This demonstrates how to pay for x402-protected resources using circlekit.

Usage:
    export PRIVATE_KEY=0x...
    python agent_client.py

Prerequisites:
    1. Server running: SELLER_ADDRESS=0x... python paywall_server.py
    2. USDC deposited in Gateway (use deposit.py)

Get testnet USDC from: https://faucet.circle.com
"""

import asyncio
import os
import sys

# Add parent directory to path for circlekit import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from circlekit import GatewayClient


# ============================================================================
# CONFIGURATION
# ============================================================================

PRIVATE_KEY = os.environ.get("PRIVATE_KEY")
SERVER_URL = os.environ.get("SERVER_URL", "http://localhost:4022")

if not PRIVATE_KEY:
    print("Error: PRIVATE_KEY environment variable is required")
    print("Usage: PRIVATE_KEY=0x... python agent_client.py")
    print("\nGet testnet USDC from: https://faucet.circle.com")
    sys.exit(1)


# ============================================================================
# MAIN
# ============================================================================

async def main():
    print("""
╔════════════════════════════════════════════════════════════════╗
║        Agent Marketplace - Python x402 Buyer (circlekit)       ║
╚════════════════════════════════════════════════════════════════╝
""")
    
    # ──────────────────────────────────────────────────────────────────────────
    # 1. Create Gateway Client
    # ──────────────────────────────────────────────────────────────────────────
    print("1. Creating Gateway client...")
    
    async with GatewayClient(
        chain="arcTestnet",
        private_key=PRIVATE_KEY,
    ) as gateway:
        
        print(f"   Address: {gateway.address}")
        print(f"   Chain: {gateway.chain_name}")
        
        # ──────────────────────────────────────────────────────────────────────
        # 2. Check Balances
        # ──────────────────────────────────────────────────────────────────────
        print("\n2. Checking balances...")
        
        balances = await gateway.get_balances()
        
        print(f"   Wallet USDC:  {balances.wallet.formatted}")
        print(f"   Gateway:      {balances.gateway.formatted_available} available")
        
        # ──────────────────────────────────────────────────────────────────────
        # 3. Discover Agent
        # ──────────────────────────────────────────────────────────────────────
        print("\n3. Discovering agent...")
        
        import httpx
        async with httpx.AsyncClient() as http:
            try:
                info_response = await http.get(f"{SERVER_URL}/")
                if info_response.status_code != 200:
                    print(f"   ❌ Failed to fetch agent info: {info_response.status_code}")
                    print("   Make sure server is running: SELLER_ADDRESS=0x... python paywall_server.py")
                    return
                
                agent_info = info_response.json()
                agent = agent_info.get("agent", {})
                
                print(f"   Agent: {agent.get('name', 'Unknown')}")
                print(f"   Description: {agent.get('description', 'N/A')}")
                print(f"   Capabilities: {', '.join(agent.get('capabilities', []))}")
                pricing = agent.get("pricing", {})
                print(f"   Pricing: analyze={pricing.get('analyze')}, generate={pricing.get('generate')}")
                print(f"   x402 Support: {'✅ Yes' if agent.get('x402Support') else '❌ No'}")
                print(f"   SDK: {agent_info.get('sdk', 'unknown')}")
                
            except Exception as e:
                print(f"   ❌ Failed to connect to server: {e}")
                print("   Make sure server is running: SELLER_ADDRESS=0x... python paywall_server.py")
                return
        
        # ──────────────────────────────────────────────────────────────────────
        # 4. Check Reputation (simulated)
        # ──────────────────────────────────────────────────────────────────────
        print("\n4. Checking agent reputation...")
        print("   📝 [SIMULATED] Would query AgentReputation.vy on-chain")
        print("   Average Score: 88/100")
        print("   Tier: Gold")
        print("   Total Feedbacks: 56")
        
        # ──────────────────────────────────────────────────────────────────────
        # 5. Check x402 Support
        # ──────────────────────────────────────────────────────────────────────
        print("\n5. Checking x402 support...")
        
        analyze_url = f"{SERVER_URL}/api/analyze"
        support = await gateway.supports(analyze_url)
        
        if support.supported:
            print("   ✅ Server supports Gateway batching")
            if support.requirements:
                print(f"   Price: {support.requirements.get('amount', 'unknown')} USDC")
        else:
            print(f"   ❌ Server does NOT support Gateway batching: {support.error}")
            return
        
        # ──────────────────────────────────────────────────────────────────────
        # 6. Pay for Analysis Service (Gasless!)
        # ──────────────────────────────────────────────────────────────────────
        print("\n6. Paying for /api/analyze ($0.01)...")
        
        try:
            result = await gateway.pay(analyze_url)
            
            print(f"   ✅ Paid {result.formatted_amount} USDC (gasless!)")
            print(f"   Transaction: {result.transaction or '(pending settlement)'}")
            print(f"   Status: {result.status}")
            print("\n   Response from agent:")
            
            if isinstance(result.data, dict):
                analysis = result.data.get("result", {})
                print(f"   - Summary: {analysis.get('summary', 'N/A')}")
                print(f"   - Confidence: {int(analysis.get('confidence', 0) * 100)}%")
                insights = analysis.get("insights", [])
                print(f"   - Insights: {len(insights)} found")
            else:
                print(f"   - Raw response: {result.data}")
                
        except ValueError as e:
            print(f"   ❌ Payment failed: {e}")
            return
        except Exception as e:
            print(f"   ❌ Request failed: {e}")
            return
        
        # ──────────────────────────────────────────────────────────────────────
        # 7. Submit Feedback (simulated)
        # ──────────────────────────────────────────────────────────────────────
        print("\n7. Submitting reputation feedback...")
        print("   📝 [SIMULATED] Would write to AgentReputation.vy on-chain")
        print("   Score: 92/100")
        print("   Comment: 'Excellent Python analysis!'")
        
        # ──────────────────────────────────────────────────────────────────────
        # 8. Final Balances
        # ──────────────────────────────────────────────────────────────────────
        print("\n8. Updated balances...")
        
        new_balances = await gateway.get_balances()
        
        print(f"   Wallet USDC:  {new_balances.wallet.formatted}")
        print(f"   Gateway:      {new_balances.gateway.formatted_available} available")
        
        print("""
╔════════════════════════════════════════════════════════════════╗
║                        Complete!                               ║
╚════════════════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    asyncio.run(main())
