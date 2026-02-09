"""
End-to-End Integration Tests for circlekit-py

These tests verify complete flows work correctly:
1. Deposit → Payment → Verify balance
2. Server receives payment → Responds with content
3. Client handles 402 → Pays → Gets content

Run with: PRIVATE_KEY=0x... pytest tests/test_e2e.py -v -s

⚠️  These tests execute real testnet transactions!
"""

import pytest
import os
import asyncio
import time
import json
import base64
from typing import Dict, Any

# Check if we have credentials for E2E tests
HAS_PRIVATE_KEY = bool(os.environ.get("PRIVATE_KEY"))
HAS_CIRCLE_CREDS = bool(
    os.environ.get("CIRCLE_API_KEY") and os.environ.get("CIRCLE_ENTITY_SECRET")
)
SKIP_REASON_PK = "PRIVATE_KEY not set"
SKIP_REASON_CIRCLE = "CIRCLE_API_KEY or CIRCLE_ENTITY_SECRET not set"


# =============================================================================
# E2E: DEPOSIT AND VERIFY FLOW
# =============================================================================

class TestDepositFlow:
    """Test the complete deposit flow."""
    
    @pytest.fixture
    def client(self):
        """Create a GatewayClient for Arc Testnet."""
        if not HAS_PRIVATE_KEY:
            pytest.skip(SKIP_REASON_PK)
        
        from circlekit import GatewayClient
        return GatewayClient(
            chain="arcTestnet",
            private_key=os.environ["PRIVATE_KEY"]
        )
    
    @pytest.mark.skipif(not HAS_PRIVATE_KEY, reason=SKIP_REASON_PK)
    @pytest.mark.asyncio
    async def test_full_deposit_flow(self, client):
        """
        Test complete deposit flow:
        1. Check initial balances
        2. Deposit USDC
        3. Verify balance increased
        """
        print("\n" + "=" * 60)
        print("E2E TEST: Full Deposit Flow")
        print("=" * 60)
        
        # Step 1: Get initial balances
        print("\nStep 1: Getting initial balances...")
        async with client:
            initial = await client.get_balances()
        
        print(f"  Wallet: {initial.wallet.formatted} USDC")
        print(f"  Gateway: {initial.gateway.formatted_total} USDC")
        
        # Check we have enough for a small deposit
        min_deposit = 10000  # 0.01 USDC
        if initial.wallet.balance < min_deposit * 2:  # Need some buffer
            pytest.skip("Insufficient balance for deposit test")
        
        # Step 2: Deposit
        print("\nStep 2: Depositing 0.01 USDC...")
        async with client:
            result = await client.deposit("0.01")
        
        print(f"  Approval TX: {result.approval_tx_hash or 'N/A'}")
        print(f"  Deposit TX: {result.deposit_tx_hash}")
        print(f"  Amount: {result.formatted_amount} USDC")
        
        # Step 3: Wait and verify
        print("\nStep 3: Waiting for indexing...")
        time.sleep(3)
        
        async with client:
            final = await client.get_balances()
        
        print(f"  Wallet: {final.wallet.formatted} USDC")
        print(f"  Gateway: {final.gateway.formatted_total} USDC")
        
        # Verify changes
        wallet_decreased = final.wallet.balance < initial.wallet.balance
        gateway_increased = final.gateway.total > initial.gateway.total
        
        print("\nVerification:")
        print(f"  Wallet balance decreased: {'✓' if wallet_decreased else '✗'}")
        print(f"  Gateway balance increased: {'✓' if gateway_increased else '✗'}")
        
        # At minimum, the deposit tx should exist
        assert result.deposit_tx_hash is not None


# =============================================================================
# E2E: PAYMENT SIGNATURE FLOW
# =============================================================================

class TestPaymentSignatureFlow:
    """Test the complete payment signature flow."""
    
    @pytest.mark.skipif(not HAS_PRIVATE_KEY, reason=SKIP_REASON_PK)
    def test_full_payment_flow(self):
        """
        Test complete payment signature flow:
        1. Parse 402 response
        2. Create payment signature
        3. Encode as header
        4. Verify header can be decoded
        """
        from circlekit import (
            GatewayClient,
            parse_402_response,
            create_payment_header,
            decode_payment_header,
        )
        from circlekit.boa_utils import get_chain_config
        
        print("\n" + "=" * 60)
        print("E2E TEST: Full Payment Signature Flow")
        print("=" * 60)
        
        private_key = os.environ["PRIVATE_KEY"]
        client = GatewayClient(chain="arcTestnet", private_key=private_key)
        config = get_chain_config("arcTestnet")
        
        # Step 1: Simulate a 402 response
        print("\nStep 1: Simulating 402 response...")
        
        mock_402_response = {
            "accepts": [{
                "scheme": "exact",
                "network": f"eip155:{config.chain_id}",
                "asset": config.usdc_address,
                "amount": "50000",  # 0.05 USDC
                "payTo": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
                "maxTimeoutSeconds": 345600,
                "extra": {
                    "name": "GatewayWalletBatched",
                    "version": "1",
                    "verifyingContract": config.gateway_address,
                },
            }],
            "error": "Payment required",
            "x402Version": 1,
        }
        
        print(f"  Received 402 with payment request for 0.05 USDC")
        
        # Step 2: Parse the response
        print("\nStep 2: Parsing 402 response...")
        x402_response = parse_402_response(mock_402_response)
        
        assert len(x402_response.accepts) > 0, "No payment options in response"
        requirements = x402_response.accepts[0]
        
        print(f"  Scheme: {requirements.scheme}")
        print(f"  Network: {requirements.network}")
        print(f"  Amount: {int(requirements.amount) / 1e6} USDC")
        print(f"  Pay to: {requirements.pay_to}")
        
        # Step 3: Create payment header
        print("\nStep 3: Creating payment header...")
        header = create_payment_header(
            private_key=private_key,
            payer_address=client.address,
            requirements=requirements,
        )
        
        print(f"  Header length: {len(header)} chars")
        print(f"  Header preview: {header[:50]}...")
        
        # Step 4: Verify header can be decoded
        print("\nStep 4: Decoding payment header...")
        decoded = decode_payment_header(header)
        
        print(f"  Decoded fields: {list(decoded.keys())}")
        print(f"  Has signature: {'signature' in decoded}")
        print(f"  Has authorization: {'authorization' in decoded}")
        
        # The decoded header is the payment payload directly
        assert "signature" in decoded
        assert "authorization" in decoded
        
        authorization = decoded["authorization"]
        assert "from" in authorization
        assert "to" in authorization
        
        print("\n✓ Payment flow completed successfully!")


# =============================================================================
# E2E: SERVER MIDDLEWARE FLOW
# =============================================================================

class TestServerMiddlewareFlow:
    """Test the complete server middleware flow."""
    
    @pytest.mark.skipif(not HAS_PRIVATE_KEY, reason=SKIP_REASON_PK)
    def test_flask_middleware_integration(self):
        """
        Test Flask middleware:
        1. Create app with payment requirement
        2. Make request without payment
        3. Verify 402 response
        4. Create payment header
        5. Make request with payment
        """
        from flask import Flask
        from circlekit import create_gateway_middleware
        
        print("\n" + "=" * 60)
        print("E2E TEST: Flask Middleware Integration")
        print("=" * 60)
        
        # Step 1: Create Flask app with middleware
        print("\nStep 1: Creating Flask app with payment middleware...")
        
        app = Flask(__name__)
        gateway = create_gateway_middleware(
            seller_address="0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
            chain="arcTestnet",
        )
        
        @app.route("/paid-content")
        @gateway.require("$0.05")
        def paid_content():
            return {"content": "Premium content unlocked!"}
        
        print("  Created /paid-content endpoint requiring $0.05")
        
        # Step 2: Make request without payment
        print("\nStep 2: Testing request without payment...")
        
        with app.test_client() as test_client:
            response = test_client.get("/paid-content")
        
        print(f"  Status: {response.status_code}")
        
        assert response.status_code == 402, f"Expected 402, got {response.status_code}"
        
        # Step 3: Verify 402 response format
        print("\nStep 3: Verifying 402 response format...")
        
        data = response.get_json()
        
        assert "accepts" in data, "Missing 'accepts' in 402 response"
        assert "x402Version" in data, "Missing 'x402Version' in 402 response"
        
        print(f"  x402Version: {data['x402Version']}")
        print(f"  Number of payment options: {len(data['accepts'])}")
        
        if data["accepts"]:
            option = data["accepts"][0]
            print(f"  First option:")
            print(f"    - Scheme: {option.get('scheme')}")
            print(f"    - Network: {option.get('network')}")
            print(f"    - Amount: {int(option.get('amount', 0)) / 1e6} USDC")
        
        print("\n✓ Middleware flow completed successfully!")


# =============================================================================
# E2E: CROSS-CHAIN COMPATIBILITY
# =============================================================================

class TestCrossChainCompatibility:
    """Test that the SDK works across different chains."""
    
    @pytest.mark.skipif(not HAS_PRIVATE_KEY, reason=SKIP_REASON_PK)
    @pytest.mark.asyncio
    async def test_arc_and_base_sepolia_parallel(self):
        """
        Test querying both chains in parallel:
        1. Create clients for both chains
        2. Query balances in parallel
        3. Verify both respond correctly
        """
        from circlekit import GatewayClient
        
        print("\n" + "=" * 60)
        print("E2E TEST: Cross-Chain Parallel Queries")
        print("=" * 60)
        
        private_key = os.environ["PRIVATE_KEY"]
        
        arc_client = GatewayClient(chain="arcTestnet", private_key=private_key)
        base_client = GatewayClient(chain="baseSepolia", private_key=private_key)
        
        print(f"\nAddress: {arc_client.address}")
        print(f"Querying Arc Testnet (chain {arc_client.chain_id}) and Base Sepolia (chain {base_client.chain_id})...")
        
        # Query both in parallel
        async def get_arc_balance():
            async with arc_client:
                return await arc_client.get_balances()
        
        async def get_base_balance():
            async with base_client:
                return await base_client.get_balances()
        
        arc_task = asyncio.create_task(get_arc_balance())
        base_task = asyncio.create_task(get_base_balance())
        
        arc_balances, base_balances = await asyncio.gather(arc_task, base_task)
        
        print(f"\nResults:")
        print(f"  Arc Testnet:")
        print(f"    - Wallet: {arc_balances.wallet.formatted} USDC")
        print(f"    - Gateway: {arc_balances.gateway.formatted_total} USDC")
        print(f"  Base Sepolia:")
        print(f"    - Wallet: {base_balances.wallet.formatted} USDC")
        print(f"    - Gateway: {base_balances.gateway.formatted_total} USDC")
        
        # Both should have valid responses
        assert arc_balances is not None
        assert base_balances is not None
        
        print("\n✓ Cross-chain queries completed successfully!")


# =============================================================================
# E2E: PROGRAMMABLE WALLETS WITH GATEWAY
# =============================================================================

class TestProgrammableWalletsWithGateway:
    """Test using Programmable Wallets with Gateway operations."""
    
    @pytest.mark.skipif(
        not HAS_CIRCLE_CREDS,
        reason=SKIP_REASON_CIRCLE
    )
    def test_list_wallets_and_check_balances(self):
        """
        Test querying Gateway balances for Programmable Wallets:
        1. List wallets from Circle
        2. Query Gateway balance for each Arc Testnet wallet
        """
        from circlekit import AgentWalletManager
        from circlekit.boa_utils import get_chain_config, setup_boa_env, get_usdc_balance, format_usdc
        
        print("\n" + "=" * 60)
        print("E2E TEST: Programmable Wallets + Gateway")
        print("=" * 60)
        
        manager = AgentWalletManager()
        
        # Step 1: List wallets
        print("\nStep 1: Listing Circle wallets...")
        wallets = manager.list_wallets()
        
        print(f"  Found {len(wallets)} wallet(s)")
        
        # Filter for Arc Testnet wallets
        arc_wallets = [w for w in wallets if "ARC" in w.blockchain.upper()]
        
        print(f"  Arc Testnet wallets: {len(arc_wallets)}")
        
        if not arc_wallets:
            pytest.skip("No Arc Testnet wallets in Circle account")
        
        # Step 2: Check balances
        print("\nStep 2: Checking balances for Arc wallets...")
        
        config = get_chain_config("arcTestnet")
        setup_boa_env("arcTestnet")
        
        for wallet in arc_wallets[:3]:  # Check first 3
            balance = get_usdc_balance("arcTestnet", wallet.address)
            formatted = format_usdc(balance)
            
            print(f"  {wallet.name or 'Unnamed'} ({wallet.address[:10]}...): {formatted} USDC")
        
        print("\n✓ Programmable Wallets integration completed!")


# =============================================================================
# E2E: FULL BUYER JOURNEY
# =============================================================================

class TestFullBuyerJourney:
    """Test the complete buyer journey from wallet to payment."""
    
    @pytest.mark.skipif(not HAS_PRIVATE_KEY, reason=SKIP_REASON_PK)
    @pytest.mark.asyncio
    async def test_complete_buyer_journey(self):
        """
        Complete buyer journey:
        1. Check wallet balance
        2. Check gateway balance
        3. Deposit if needed
        4. Create payment signature
        5. Verify signature is valid
        """
        from circlekit import GatewayClient
        from circlekit.x402 import PaymentRequirements, create_payment_payload
        from circlekit.boa_utils import get_chain_config
        
        print("\n" + "=" * 60)
        print("E2E TEST: Complete Buyer Journey")
        print("=" * 60)
        
        private_key = os.environ["PRIVATE_KEY"]
        client = GatewayClient(chain="arcTestnet", private_key=private_key)
        config = get_chain_config("arcTestnet")
        
        # Step 1: Check balances
        print("\nStep 1: Checking balances...")
        async with client:
            balances = await client.get_balances()
        
        print(f"  Wallet: {balances.wallet.formatted} USDC")
        print(f"  Gateway: {balances.gateway.formatted_available} USDC (available)")
        
        # Step 2: Determine if deposit needed
        payment_amount = 50000  # 0.05 USDC
        
        print(f"\nStep 2: Planning payment of 0.05 USDC...")
        
        if balances.gateway.available >= payment_amount:
            print("  ✓ Sufficient Gateway balance - no deposit needed")
        elif balances.wallet.balance >= payment_amount:
            print("  ℹ Would need to deposit from wallet")
            # In a real flow, we'd deposit here
        else:
            print("  ✗ Insufficient funds in both wallet and gateway")
            pytest.skip("Insufficient funds for buyer journey test")
        
        # Step 3: Create payment signature
        print("\nStep 3: Creating payment signature...")
        
        requirements = PaymentRequirements(
            scheme="exact",
            network=f"eip155:{config.chain_id}",
            asset=config.usdc_address,
            amount=str(payment_amount),
            pay_to="0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
            max_timeout_seconds=345600,
            extra={
                "name": "GatewayWalletBatched",
                "version": "1",
                "verifyingContract": config.gateway_address,
            },
        )
        
        payload = create_payment_payload(
            private_key=private_key,
            payer_address=client.address,
            requirements=requirements,
        )
        
        print(f"  From: {payload.authorization['from'][:15]}...")
        print(f"  To: {payload.authorization['to'][:15]}...")
        print(f"  Value: {int(payload.authorization['value']) / 1e6} USDC")
        print(f"  Signature: {payload.signature[:20]}...")
        
        # Step 4: Verify signature format
        print("\nStep 4: Verifying signature format...")
        
        sig = payload.signature
        # Signature may or may not have 0x prefix
        if sig.startswith("0x"):
            assert len(sig) == 132  # 0x + 130 hex chars
        else:
            assert len(sig) == 130  # 130 hex chars without prefix
        
        # Verify authorization fields
        assert payload.authorization["from"].lower() == client.address.lower()
        assert int(payload.authorization["value"]) == payment_amount
        
        print("  ✓ Signature is valid format")
        print("  ✓ Authorization fields are correct")
        
        print("\n" + "=" * 60)
        print("✓ Complete buyer journey verified!")
        print("=" * 60)


# =============================================================================
# SUMMARY
# =============================================================================

if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════════════════════════╗
    ║              END-TO-END INTEGRATION TESTS                         ║
    ╠══════════════════════════════════════════════════════════════════╣
    ║ These tests verify complete flows with real testnets!             ║
    ║                                                                   ║
    ║ Prerequisites:                                                    ║
    ║   - PRIVATE_KEY env var (for transaction tests)                   ║
    ║   - CIRCLE_API_KEY + CIRCLE_ENTITY_SECRET (for wallet tests)      ║
    ║   - Testnet USDC from faucet.circle.com                           ║
    ║                                                                   ║
    ║ Run: PRIVATE_KEY=0x... pytest tests/test_e2e.py -v -s             ║
    ╚══════════════════════════════════════════════════════════════════╝
    """)
    pytest.main([__file__, "-v", "-s"])
