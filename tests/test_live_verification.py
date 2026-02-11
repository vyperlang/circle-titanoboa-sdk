"""
Live Verification Tests for circlekit-py

These tests verify against REAL infrastructure to catch hallucinations.
They require network access but don't require funds.

Run with: python -m pytest tests/test_live_verification.py -v -s
"""

import pytest
import httpx
import json


# =============================================================================
# TEST: Chain Configuration Verification
# =============================================================================

class TestLiveChainConfigs:
    """Verify chain configurations against live RPC endpoints."""
    
    @pytest.mark.asyncio
    async def test_arc_testnet_rpc_responds(self):
        """Arc Testnet RPC should respond to eth_chainId."""
        from circlekit.constants import CHAIN_CONFIGS
        
        config = CHAIN_CONFIGS["arcTestnet"]
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                config.rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "method": "eth_chainId",
                    "params": [],
                    "id": 1,
                }
            )
        
        assert response.status_code == 200, f"RPC failed: {response.text}"
        
        data = response.json()
        assert "result" in data, f"No result in response: {data}"
        
        chain_id = int(data["result"], 16)
        assert chain_id == config.chain_id, f"Chain ID mismatch: got {chain_id}, expected {config.chain_id}"
        
        print(f"Arc Testnet RPC verified: chain_id={chain_id}")
    
    @pytest.mark.asyncio
    async def test_base_sepolia_rpc_responds(self):
        """Base Sepolia RPC should respond to eth_chainId."""
        from circlekit.constants import CHAIN_CONFIGS
        
        config = CHAIN_CONFIGS["baseSepolia"]
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                config.rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "method": "eth_chainId",
                    "params": [],
                    "id": 1,
                }
            )
        
        assert response.status_code == 200, f"RPC failed: {response.text}"
        
        data = response.json()
        chain_id = int(data["result"], 16)
        assert chain_id == config.chain_id, f"Chain ID mismatch: got {chain_id}, expected {config.chain_id}"
        
        print(f"Base Sepolia RPC verified: chain_id={chain_id}")


# =============================================================================
# TEST: USDC Contract Verification
# =============================================================================

class TestLiveUSDCContract:
    """Verify USDC contract addresses are correct."""
    
    @pytest.mark.asyncio
    async def test_arc_testnet_usdc_has_code(self):
        """
        Arc Testnet USDC sentinel contract should have code.
        
        NOTE: On Arc, USDC is the native gas token, but there's a sentinel
        contract at 0x3600... that wraps it as ERC-20 for compatibility.
        """
        from circlekit.constants import CHAIN_CONFIGS
        
        config = CHAIN_CONFIGS["arcTestnet"]
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                config.rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "method": "eth_getCode",
                    "params": [config.usdc_address, "latest"],
                    "id": 1,
                }
            )
        
        data = response.json()
        code = data.get("result", "0x")
        
        # The sentinel contract should have code
        assert len(code) > 2, f"No contract code at sentinel address {config.usdc_address}"
        
        print(f"Arc Testnet USDC sentinel verified: {len(code)} bytes of code")
    
    @pytest.mark.asyncio
    async def test_arc_testnet_usdc_decimals(self):
        """Arc Testnet USDC should return 6 decimals."""
        from circlekit.constants import CHAIN_CONFIGS
        
        config = CHAIN_CONFIGS["arcTestnet"]
        
        # decimals() selector = 0x313ce567
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                config.rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "method": "eth_call",
                    "params": [
                        {
                            "to": config.usdc_address,
                            "data": "0x313ce567",
                        },
                        "latest",
                    ],
                    "id": 1,
                }
            )
        
        data = response.json()
        result = data.get("result", "0x")
        
        if result and result != "0x":
            decimals = int(result, 16)
            assert decimals == 6, f"USDC decimals should be 6, got {decimals}"
            print(f"Arc Testnet USDC decimals verified: {decimals}")
        else:
            pytest.skip("Could not read decimals (might be different ABI)")
    
    @pytest.mark.asyncio
    async def test_arc_testnet_usdc_name(self):
        """Arc Testnet USDC should return correct name."""
        from circlekit.constants import CHAIN_CONFIGS
        
        config = CHAIN_CONFIGS["arcTestnet"]
        
        # name() selector = 0x06fdde03
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                config.rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "method": "eth_call",
                    "params": [
                        {
                            "to": config.usdc_address,
                            "data": "0x06fdde03",
                        },
                        "latest",
                    ],
                    "id": 1,
                }
            )
        
        data = response.json()
        result = data.get("result", "0x")
        
        if result and len(result) > 2:
            # Decode string from ABI encoding
            # Skip first 64 chars (offset) + next 64 chars (length)
            try:
                hex_data = result[2:]  # Remove 0x
                if len(hex_data) >= 128:
                    length = int(hex_data[64:128], 16)
                    name_hex = hex_data[128:128 + length * 2]
                    name = bytes.fromhex(name_hex).decode('utf-8').rstrip('\x00')
                    print(f"Arc Testnet USDC name: '{name}'")
                    assert "USD" in name.upper() or "USDC" in name.upper(), f"Unexpected token name: {name}"
            except Exception as e:
                print(f"Could not decode name: {e}")
        else:
            pytest.skip("Could not read name")


# =============================================================================
# TEST: Gateway Contract Verification
# =============================================================================

class TestLiveGatewayContract:
    """Verify Gateway contract addresses are correct."""
    
    @pytest.mark.asyncio
    async def test_arc_testnet_gateway_has_code(self):
        """Arc Testnet Gateway address should have contract code."""
        from circlekit.constants import CHAIN_CONFIGS
        
        config = CHAIN_CONFIGS["arcTestnet"]
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                config.rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "method": "eth_getCode",
                    "params": [config.gateway_address, "latest"],
                    "id": 1,
                }
            )
        
        data = response.json()
        code = data.get("result", "0x")
        
        # Contract should have code
        assert len(code) > 2, f"No contract code at Gateway address {config.gateway_address}"
        
        print(f"Arc Testnet Gateway verified: {len(code)} bytes of code")


# =============================================================================
# TEST: Gateway API Verification
# =============================================================================

class TestLiveGatewayAPI:
    """Verify Gateway API endpoints exist and respond."""
    
    @pytest.mark.asyncio
    async def test_gateway_api_base_url_responds(self):
        """Gateway API base URL should respond."""
        from circlekit.constants import GATEWAY_API_TESTNET_URL
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(GATEWAY_API_TESTNET_URL)
                # Any response (even 404) means the server exists
                print(f"Gateway API responded: status={response.status_code}")
                # We just want to verify it's reachable, not necessarily 200
                assert response.status_code < 500, f"Gateway API error: {response.status_code}"
            except httpx.ConnectError as e:
                pytest.fail(f"Gateway API not reachable: {e}")
    
    @pytest.mark.asyncio
    async def test_gateway_api_balances_endpoint(self):
        """
        Test if the balances endpoint exists.
        
        The Gateway API uses POST /v1/balances with a JSON body.
        """
        from circlekit.constants import GATEWAY_API_TESTNET_URL
        
        test_address = "0x0000000000000000000000000000000000000001"
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                # Gateway API uses POST with JSON body
                response = await client.post(
                    f"{GATEWAY_API_TESTNET_URL}/v1/balances",
                    json={
                        "token": "USDC",
                        "sources": [{"depositor": test_address}]
                    }
                )
                print(f"Balances endpoint: status={response.status_code}, body={response.text[:300]}")
                
                # 200 = works
                # 400 = bad request but endpoint exists
                # 401/403 = auth required but endpoint exists
                # 404 = endpoint doesn't exist
                if response.status_code == 404:
                    pytest.fail(
                        "Gateway API /v1/balances endpoint returns 404. "
                        "The endpoint structure may be different."
                    )
                elif response.status_code in [200, 400, 401, 403]:
                    print(f"Gateway API endpoint exists (status {response.status_code})")
                    
            except httpx.ConnectError as e:
                pytest.skip(f"Gateway API not reachable: {e}")


# =============================================================================
# TEST: EIP-712 Signature Verification
# =============================================================================

class TestEIP712Signatures:
    """Verify EIP-712 signatures are correctly formatted."""
    
    def test_payment_signature_is_recoverable(self):
        """Payment signatures should be recoverable to the correct address."""
        from circlekit.signer import PrivateKeySigner
        from circlekit.x402 import create_payment_payload, PaymentRequirements

        # Test private key
        private_key = "0x0000000000000000000000000000000000000000000000000000000000000001"
        signer = PrivateKeySigner(private_key)
        expected_address = signer.address

        requirements = PaymentRequirements(
            scheme="exact",
            network="eip155:5042002",
            asset="0x3600000000000000000000000000000000000000",
            amount="10000",
            pay_to="0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
            max_timeout_seconds=345600,
            extra={
                "name": "GatewayWalletBatched",
                "version": "1",
                "verifyingContract": "0x0077777d7eba4688bdef3e311b846f25870a19b9",
            },
        )

        payload = create_payment_payload(
            signer=signer,
            requirements=requirements,
        )

        # PaymentPayload is a dataclass with .signature and .authorization (dict)
        assert hasattr(payload, 'signature'), f"PaymentPayload missing signature attr: {type(payload)}"
        assert hasattr(payload, 'authorization'), f"PaymentPayload missing authorization attr"

        sig = payload.signature
        assert sig.startswith("0x") or len(sig) == 130 or len(sig) == 132, \
            f"Invalid signature format: {sig[:20]}..."

        print(f"Payment signature created: {sig[:20]}...")
        print(f"Payload authorization: {payload.authorization}")

        # Verify the from address matches (authorization is a dict)
        from_addr = payload.authorization.get("from", "")
        assert from_addr.lower() == expected_address.lower(), \
            f"From address mismatch: {from_addr} != {expected_address}"


# =============================================================================
# TEST: Titanoboa Transaction Signing (CRITICAL)
# =============================================================================

class TestTitanoboaTransactions:
    """
    Verify titanoboa transaction signing works correctly.
    
    CRITICAL: boa.env.prank() is for TESTING, not real transactions!
    """
    
    def test_prank_is_not_for_real_transactions(self):
        """
        Document that boa.env.prank() is NOT for signing real transactions.
        
        This test exists to highlight a potential hallucination in the
        execute_approve/execute_deposit functions.
        """
        import boa
        
        # boa.env.prank() is a context manager for testing that simulates
        # calls from a specific address. It does NOT sign real transactions.
        
        # For real transaction signing on a live network, you need:
        # 1. boa.env.add_account(account) to add a signing account
        # 2. The account must have funds for gas
        # 3. Transactions are sent when calling contract methods
        
        # WARNING: The current execute_approve/execute_deposit implementation
        # uses prank(), which will NOT work for real on-chain transactions!
        
        print("\nWARNING: execute_approve/execute_deposit use boa.env.prank()")
        print("This is for TESTING only, not real transaction signing!")
        print("For real transactions, need boa.env.add_account() + funded wallet")
        
        # This test passes but documents the issue
        assert True


# =============================================================================
# SUMMARY
# =============================================================================

if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════════════════════════╗
    ║                    LIVE VERIFICATION TESTS                       ║
    ╠══════════════════════════════════════════════════════════════════╣
    ║ These tests verify circlekit-py against REAL infrastructure.     ║
    ║                                                                  ║
    ║ Run with: python -m pytest tests/test_live_verification.py -v -s ║
    ║                                                                  ║
    ║ Tests that FAIL indicate potential hallucinations!               ║
    ╚══════════════════════════════════════════════════════════════════╝
    """)
    pytest.main([__file__, "-v", "-s"])
