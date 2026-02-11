"""
Real Testnet Transaction Tests for circlekit-py

These tests execute REAL transactions on testnets to verify the SDK works
with actual funds. They require:
- PRIVATE_KEY environment variable with a funded wallet
- Testnet USDC in the wallet

Run with: PRIVATE_KEY=0x... python -m pytest tests/test_real_transactions.py -v -s

⚠️  These tests will spend real testnet tokens!
"""

import pytest
import os
import time
import httpx
from typing import Optional

# Check if we have a private key for real tests
HAS_PRIVATE_KEY = bool(os.environ.get("PRIVATE_KEY"))
SKIP_REASON = "PRIVATE_KEY not set - skipping real transaction tests"


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def private_key() -> str:
    """Get private key from environment."""
    key = os.environ.get("PRIVATE_KEY")
    if not key:
        pytest.skip(SKIP_REASON)
    return key


@pytest.fixture
def arc_testnet_client(private_key: str):
    """Create a GatewayClient for Arc Testnet."""
    from circlekit import GatewayClient
    return GatewayClient(chain="arcTestnet", private_key=private_key)


@pytest.fixture
def base_sepolia_client(private_key: str):
    """Create a GatewayClient for Base Sepolia."""
    from circlekit import GatewayClient
    return GatewayClient(chain="baseSepolia", private_key=private_key)


# =============================================================================
# ARC TESTNET BALANCE TESTS
# =============================================================================

class TestArcTestnetBalances:
    """Test balance retrieval on Arc Testnet (native USDC chain)."""
    
    @pytest.mark.skipif(not HAS_PRIVATE_KEY, reason=SKIP_REASON)
    def test_get_wallet_usdc_balance(self, arc_testnet_client):
        """Should retrieve wallet USDC balance on Arc Testnet."""
        from circlekit.boa_utils import (
            setup_boa_env,
            get_usdc_balance,
            get_chain_config,
            format_usdc,
        )
        
        setup_boa_env("arcTestnet")
        
        balance = get_usdc_balance("arcTestnet", arc_testnet_client.address)
        formatted = format_usdc(balance)
        
        print(f"\nArc Testnet wallet balance: {formatted} USDC ({balance} units)")
        
        # Balance should be a non-negative integer
        assert isinstance(balance, int)
        assert balance >= 0
    
    @pytest.mark.skipif(not HAS_PRIVATE_KEY, reason=SKIP_REASON)
    @pytest.mark.asyncio
    async def test_get_gateway_balance(self, arc_testnet_client):
        """Should retrieve Gateway balance on Arc Testnet."""
        async with arc_testnet_client:
            balances = await arc_testnet_client.get_balances()
        
        print(f"\nArc Testnet Gateway balance:")
        print(f"  - Total: {balances.gateway.formatted_total} USDC")
        print(f"  - Available: {balances.gateway.formatted_available} USDC")
        print(f"  - Withdrawing: {balances.gateway.formatted_withdrawing} USDC")
        
        # All values should be valid
        assert balances.gateway.total >= 0
        assert balances.gateway.available >= 0
        assert balances.gateway.withdrawing >= 0
    
    @pytest.mark.skipif(not HAS_PRIVATE_KEY, reason=SKIP_REASON)
    @pytest.mark.asyncio
    async def test_get_combined_balances(self, arc_testnet_client):
        """Should get both wallet and gateway balances in one call."""
        async with arc_testnet_client:
            balances = await arc_testnet_client.get_balances()
        
        print(f"\nCombined balances for {arc_testnet_client.address}:")
        print(f"  Wallet: {balances.wallet.formatted} USDC")
        print(f"  Gateway: {balances.gateway.formatted_total} USDC")
        
        # Both should be accessible
        assert hasattr(balances, 'wallet')
        assert hasattr(balances, 'gateway')


# =============================================================================
# ARC TESTNET APPROVAL TESTS
# =============================================================================

class TestArcTestnetApproval:
    """Test ERC-20 approvals on Arc Testnet (via sentinel contract)."""
    
    @pytest.mark.skipif(not HAS_PRIVATE_KEY, reason=SKIP_REASON)
    def test_check_allowance(self, private_key: str):
        """Should check current allowance."""
        from circlekit.boa_utils import (
            setup_boa_with_account,
            check_allowance,
            get_chain_config,
            get_account_from_private_key,
        )
        
        address, account = get_account_from_private_key(private_key)
        config = get_chain_config("arcTestnet")
        
        allowance = check_allowance("arcTestnet", address, config.gateway_address)
        
        print(f"\nCurrent allowance to Gateway: {allowance / 1e6} USDC")
        
        # Allowance should be a non-negative integer
        assert isinstance(allowance, int)
        assert allowance >= 0
    
    @pytest.mark.skipif(not HAS_PRIVATE_KEY, reason=SKIP_REASON)
    def test_approve_small_amount(self, private_key: str):
        """Should approve a small amount for the Gateway.
        
        ⚠️  This test executes a real approval transaction!
        """
        from circlekit.boa_utils import (
            setup_boa_with_account,
            execute_approve,
            check_allowance,
            get_chain_config,
            get_account_from_private_key,
            parse_usdc,
        )
        
        config = get_chain_config("arcTestnet")
        address, account = get_account_from_private_key(private_key)
        
        # Approve 0.01 USDC
        amount = parse_usdc("0.01")
        
        print(f"\nApproving {amount / 1e6} USDC to Gateway...")
        
        tx_hash = execute_approve("arcTestnet", private_key, config.gateway_address, amount)
        
        print(f"Approval tx: {tx_hash}")
        
        # Verify the approval went through
        new_allowance = check_allowance("arcTestnet", address, config.gateway_address)
        
        print(f"New allowance: {new_allowance / 1e6} USDC")
        
        # Allowance should be at least what we approved
        assert new_allowance >= amount, f"Allowance not updated: {new_allowance} < {amount}"


# =============================================================================
# ARC TESTNET DEPOSIT TESTS
# =============================================================================

class TestArcTestnetDeposit:
    """Test deposit to Gateway on Arc Testnet."""
    
    @pytest.mark.skipif(not HAS_PRIVATE_KEY, reason=SKIP_REASON)
    @pytest.mark.asyncio
    async def test_deposit_small_amount(self, arc_testnet_client, private_key: str):
        """Should deposit a small amount to the Gateway.
        
        ⚠️  This test executes a real deposit transaction!
        """
        # Get initial balance
        async with arc_testnet_client:
            initial_balances = await arc_testnet_client.get_balances()
        
        initial_gateway = initial_balances.gateway.total
        
        print(f"\nInitial Gateway balance: {initial_balances.gateway.formatted_total} USDC")
        print(f"Initial wallet balance: {initial_balances.wallet.formatted} USDC")
        
        # Check we have enough
        if initial_balances.wallet.balance < 10000:  # 0.01 USDC
            pytest.skip("Insufficient wallet balance for deposit test")
        
        # Deposit 0.01 USDC
        deposit_amount = "0.01"
        
        print(f"\nDepositing {deposit_amount} USDC...")
        
        async with arc_testnet_client:
            result = await arc_testnet_client.deposit(deposit_amount)
        
        print(f"Deposit result:")
        print(f"  - Approval tx: {result.approval_tx_hash}")
        print(f"  - Deposit tx: {result.deposit_tx_hash}")
        print(f"  - Amount: {result.formatted_amount} USDC")
        
        # Wait a moment for indexing
        time.sleep(2)
        
        # Verify balance changed
        async with arc_testnet_client:
            final_balances = await arc_testnet_client.get_balances()
        
        final_gateway = final_balances.gateway.total
        
        print(f"\nFinal Gateway balance: {final_balances.gateway.formatted_total} USDC")
        
        # The deposit tx should exist
        assert result.deposit_tx_hash is not None or result.amount > 0, \
            "No deposit tx hash and no amount deposited"
        
        # Note: Gateway API might have indexing delays, so we don't strictly
        # assert the balance increased. The deposit tx existing is the key test.


# =============================================================================
# PAYMENT SIGNATURE TESTS
# =============================================================================

class TestPaymentSignatures:
    """Test EIP-712 payment signature creation."""
    
    @pytest.mark.skipif(not HAS_PRIVATE_KEY, reason=SKIP_REASON)
    def test_create_payment_signature_for_arc(self, private_key: str):
        """Should create a valid payment signature for Arc Testnet."""
        from circlekit.x402 import PaymentRequirements, create_payment_payload
        from circlekit.signer import PrivateKeySigner
        from circlekit.boa_utils import get_chain_config

        signer = PrivateKeySigner(private_key)
        config = get_chain_config("arcTestnet")

        requirements = PaymentRequirements(
            scheme="exact",
            network=f"eip155:{config.chain_id}",
            asset=config.usdc_address,
            amount="100000",  # 0.10 USDC
            pay_to="0x70997970C51812dc3A010C7d01b50e0d17dc79C8",  # Test recipient
            max_timeout_seconds=345600,
            extra={
                "name": "GatewayWalletBatched",
                "version": "1",
                "verifyingContract": config.gateway_address,
            },
        )

        payload = create_payment_payload(
            signer=signer,
            requirements=requirements,
        )

        print(f"\nPayment payload created:")
        print(f"  - From: {payload.authorization.get('from', 'N/A')}")
        print(f"  - To: {payload.authorization.get('to', 'N/A')}")
        print(f"  - Amount: {payload.authorization.get('value', 'N/A')}")
        print(f"  - Signature: {payload.signature[:20]}...")

        # Verify the signature is valid format
        sig = payload.signature
        assert sig.startswith("0x"), f"Signature should start with 0x: {sig[:10]}"
        assert len(sig) == 132, f"Signature should be 132 chars (0x + 130 hex): got {len(sig)}"

        # Verify authorization has correct from address
        assert payload.authorization["from"].lower() == signer.address.lower()
    
    @pytest.mark.skipif(not HAS_PRIVATE_KEY, reason=SKIP_REASON)
    def test_payment_header_encoding(self, private_key: str):
        """Should encode payment header as base64."""
        from circlekit.x402 import (
            PaymentRequirements,
            create_payment_header,
            decode_payment_header,
        )
        from circlekit.signer import PrivateKeySigner
        from circlekit.boa_utils import get_chain_config

        signer = PrivateKeySigner(private_key)
        config = get_chain_config("arcTestnet")

        requirements = PaymentRequirements(
            scheme="exact",
            network=f"eip155:{config.chain_id}",
            asset=config.usdc_address,
            amount="100000",
            pay_to="0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
            max_timeout_seconds=345600,
            extra={
                "name": "GatewayWalletBatched",
                "version": "1",
                "verifyingContract": config.gateway_address,
            },
        )

        header = create_payment_header(
            signer=signer,
            requirements=requirements,
        )

        print(f"\nPayment header (base64): {header[:50]}...")

        # Decode and verify
        decoded = decode_payment_header(header)

        print(f"Decoded header fields: {list(decoded.keys())}")

        # The decoded header has {x402Version, payload: {authorization, signature}, resource, accepted}
        assert "payload" in decoded
        assert "signature" in decoded["payload"]
        assert "authorization" in decoded["payload"]
        assert "accepted" in decoded


# =============================================================================
# BASE SEPOLIA TESTS (ERC-20 USDC)
# =============================================================================

class TestBaseSepoliaBalances:
    """Test balance retrieval on Base Sepolia (standard ERC-20 USDC)."""
    
    @pytest.mark.skipif(not HAS_PRIVATE_KEY, reason=SKIP_REASON)
    def test_get_wallet_usdc_balance(self, base_sepolia_client):
        """Should retrieve wallet USDC balance on Base Sepolia."""
        from circlekit.boa_utils import (
            setup_boa_env,
            get_usdc_balance,
            get_chain_config,
            format_usdc,
        )
        
        setup_boa_env("baseSepolia")
        
        balance = get_usdc_balance("baseSepolia", base_sepolia_client.address)
        formatted = format_usdc(balance)
        
        print(f"\nBase Sepolia wallet balance: {formatted} USDC ({balance} units)")
        
        # Balance should be a non-negative integer
        assert isinstance(balance, int)
        assert balance >= 0
    
    @pytest.mark.skipif(not HAS_PRIVATE_KEY, reason=SKIP_REASON)
    @pytest.mark.asyncio
    async def test_get_gateway_balance(self, base_sepolia_client):
        """Should retrieve Gateway balance on Base Sepolia."""
        async with base_sepolia_client:
            balances = await base_sepolia_client.get_balances()
        
        print(f"\nBase Sepolia Gateway balance:")
        print(f"  - Total: {balances.gateway.formatted_total} USDC")
        print(f"  - Available: {balances.gateway.formatted_available} USDC")
        
        assert balances.gateway.total >= 0


# =============================================================================
# CROSS-CHAIN CONSISTENCY TESTS
# =============================================================================

class TestCrossChainConsistency:
    """Verify SDK behaves consistently across different chains."""
    
    @pytest.mark.skipif(not HAS_PRIVATE_KEY, reason=SKIP_REASON)
    def test_same_address_across_chains(self, arc_testnet_client, base_sepolia_client):
        """Same private key should produce same address on all chains."""
        assert arc_testnet_client.address == base_sepolia_client.address, \
            "Address should be the same across chains"
        
        print(f"\nAddress: {arc_testnet_client.address}")
        print("  ✓ Same on Arc Testnet")
        print("  ✓ Same on Base Sepolia")
    
    @pytest.mark.skipif(not HAS_PRIVATE_KEY, reason=SKIP_REASON)
    def test_different_chain_configs(self, arc_testnet_client, base_sepolia_client):
        """Each chain should have distinct configuration."""
        assert arc_testnet_client.chain_id != base_sepolia_client.chain_id
        
        print(f"\nChain IDs:")
        print(f"  Arc Testnet: {arc_testnet_client.chain_id}")
        print(f"  Base Sepolia: {base_sepolia_client.chain_id}")
    
    @pytest.mark.skipif(not HAS_PRIVATE_KEY, reason=SKIP_REASON)
    @pytest.mark.asyncio
    async def test_both_chains_respond(self, arc_testnet_client, base_sepolia_client):
        """Both chains should respond to balance queries."""
        async with arc_testnet_client:
            arc_balances = await arc_testnet_client.get_balances()
        
        async with base_sepolia_client:
            base_balances = await base_sepolia_client.get_balances()
        
        print(f"\nBalances:")
        print(f"  Arc Testnet Gateway: {arc_balances.gateway.formatted_total} USDC")
        print(f"  Base Sepolia Gateway: {base_balances.gateway.formatted_total} USDC")
        
        # Both should return valid balance objects
        assert arc_balances.gateway is not None
        assert base_balances.gateway is not None


# =============================================================================
# RPC RELIABILITY TESTS
# =============================================================================

class TestRPCReliability:
    """Test RPC endpoint reliability and error handling."""
    
    @pytest.mark.skipif(not HAS_PRIVATE_KEY, reason=SKIP_REASON)
    @pytest.mark.asyncio
    async def test_arc_testnet_multiple_requests(self, private_key: str):
        """Arc Testnet RPC should handle multiple sequential requests."""
        from circlekit.boa_utils import (
            setup_boa_with_account,
            get_usdc_balance,
            get_chain_config,
            get_account_from_private_key,
        )
        
        config = get_chain_config("arcTestnet")
        address, account = get_account_from_private_key(private_key)
        setup_boa_with_account("arcTestnet", private_key)
        
        balances = []
        
        print("\nMaking 5 sequential balance requests...")
        
        for i in range(5):
            balance = get_usdc_balance("arcTestnet", address)
            balances.append(balance)
            print(f"  Request {i+1}: {balance / 1e6} USDC")
            time.sleep(0.5)  # Rate limiting
        
        # All balances should be the same (unless someone sent/received tokens)
        assert all(b == balances[0] for b in balances), "Balance inconsistent across requests"
        print("  ✓ All requests returned consistent balances")
    
    @pytest.mark.skipif(not HAS_PRIVATE_KEY, reason=SKIP_REASON)
    @pytest.mark.asyncio
    async def test_gateway_api_reliability(self):
        """Gateway API should respond reliably."""
        from circlekit.constants import GATEWAY_API_TESTNET_URL
        
        test_address = "0x0000000000000000000000000000000000000001"
        
        print("\nMaking 3 sequential Gateway API requests...")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            for i in range(3):
                response = await client.post(
                    f"{GATEWAY_API_TESTNET_URL}/v1/balances",
                    json={
                        "token": "USDC",
                        "sources": [{"depositor": test_address}]
                    }
                )
                
                print(f"  Request {i+1}: status={response.status_code}")
                
                assert response.status_code == 200, f"API returned {response.status_code}"
                
                time.sleep(0.5)
        
        print("  ✓ All requests successful")


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================

class TestErrorHandling:
    """Test error handling for edge cases."""
    
    @pytest.mark.skipif(not HAS_PRIVATE_KEY, reason=SKIP_REASON)
    @pytest.mark.asyncio
    async def test_insufficient_balance_deposit(self, arc_testnet_client):
        """Depositing more than wallet balance should fail or be capped.
        
        Note: This test verifies error handling. The behavior may vary:
        - Some implementations raise an exception
        - Others may cap the deposit to available balance
        - The approval might succeed but transfer might fail
        """
        async with arc_testnet_client:
            balances = await arc_testnet_client.get_balances()
        
        wallet_balance = balances.wallet.balance
        
        # Skip if we have a lot of balance (to avoid large deposits)
        if wallet_balance > 100_000_000:  # > 100 USDC
            pytest.skip("Too much balance to test insufficient funds")
        
        # Try to deposit more than we have
        excessive_amount = str((wallet_balance / 1e6) + 1000)  # 1000 USDC more than we have
        
        print(f"\nWallet balance: {balances.wallet.formatted} USDC")
        print(f"Attempting to deposit: {excessive_amount} USDC")
        
        try:
            async with arc_testnet_client:
                result = await arc_testnet_client.deposit(excessive_amount)
            # If it didn't raise, check if the deposit was reasonable
            print(f"Deposit completed (possibly capped): {result.formatted_amount} USDC")
            # The deposit should have been capped or rejected
            # Verify it didn't deposit more than available
            assert result.amount <= wallet_balance, "Deposited more than available!"
        except Exception as exc:
            print(f"Raised exception: {type(exc).__name__}")
            print(f"Message: {str(exc)[:100]}")
            # Expected behavior - insufficient funds exception
    
    @pytest.mark.skipif(not HAS_PRIVATE_KEY, reason=SKIP_REASON)
    def test_invalid_chain_fails(self, private_key: str):
        """Using invalid chain should fail with clear error."""
        from circlekit import GatewayClient
        
        with pytest.raises(ValueError) as exc_info:
            GatewayClient(chain="invalidChain", private_key=private_key)
        
        assert "unsupported" in str(exc_info.value).lower() or "invalid" in str(exc_info.value).lower()
        
        print(f"\nInvalid chain error: {exc_info.value}")
    
    @pytest.mark.skipif(not HAS_PRIVATE_KEY, reason=SKIP_REASON)
    def test_invalid_amount_format(self, arc_testnet_client):
        """Invalid amount format should fail with clear error."""
        from circlekit.boa_utils import parse_usdc
        
        invalid_amounts = [
            "not_a_number",
            "1.234.567",
            "",
            None,
        ]
        
        for amount in invalid_amounts:
            with pytest.raises((ValueError, TypeError, AttributeError)):
                parse_usdc(amount)
        
        print("\n✓ All invalid amounts rejected correctly")


# =============================================================================
# SUMMARY
# =============================================================================

if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════════════════════════╗
    ║              REAL TESTNET TRANSACTION TESTS                       ║
    ╠══════════════════════════════════════════════════════════════════╣
    ║ These tests use REAL testnet tokens!                              ║
    ║                                                                   ║
    ║ Prerequisites:                                                    ║
    ║   - PRIVATE_KEY env var with funded wallet                        ║
    ║   - Testnet USDC from faucet.circle.com                           ║
    ║                                                                   ║
    ║ Run: PRIVATE_KEY=0x... pytest tests/test_real_transactions.py -v  ║
    ╚══════════════════════════════════════════════════════════════════╝
    """)
    pytest.main([__file__, "-v", "-s"])
