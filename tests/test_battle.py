"""
Battle Tests for circlekit-py

These tests ensure the SDK is robust against:
- Edge cases and malformed inputs
- Error handling and recovery
- Security issues
- Concurrent operations
- Boundary conditions

Run with: python -m pytest tests/test_battle.py -v
"""

import pytest
import json
import base64
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock


# =============================================================================
# TEST: Input Validation & Edge Cases
# =============================================================================

class TestInputValidation:
    """Test that invalid inputs are handled gracefully."""
    
    def test_parse_402_empty_accepts(self):
        """Empty accepts array should be handled."""
        from circlekit.x402 import parse_402_response
        
        # Empty accepts is valid (though unusual) - the SDK handles this
        result = parse_402_response({"x402Version": 2, "accepts": []})
        assert result.x402_version == 2
        assert result.accepts == []
    
    def test_parse_402_missing_fields(self):
        """Missing required fields should raise."""
        from circlekit.x402 import parse_402_response
        
        # Missing x402Version
        with pytest.raises(ValueError):
            parse_402_response({"accepts": [{"scheme": "exact"}]})
        
        # Missing accepts
        with pytest.raises(ValueError):
            parse_402_response({"x402Version": 2})
    
    def test_parse_402_invalid_json(self):
        """Invalid JSON should raise."""
        from circlekit.x402 import parse_402_response
        
        with pytest.raises((ValueError, json.JSONDecodeError)):
            parse_402_response("{invalid json")
    
    def test_parse_402_non_dict_input(self):
        """Non-dict input should be handled."""
        from circlekit.x402 import parse_402_response
        
        with pytest.raises((ValueError, TypeError, AttributeError)):
            parse_402_response([1, 2, 3])
    
    def test_parse_usdc_invalid_formats(self):
        """Invalid USDC formats should be handled."""
        from circlekit.boa_utils import parse_usdc
        
        # These should work
        assert parse_usdc("1.0") == 1000000
        assert parse_usdc("$1.0") == 1000000
        assert parse_usdc("1") == 1000000
        
        # Empty string
        try:
            result = parse_usdc("")
            # If it doesn't raise, it should return 0
            assert result == 0
        except ValueError:
            pass  # Also acceptable
    
    def test_format_usdc_edge_cases(self):
        """Edge cases for USDC formatting."""
        from circlekit.boa_utils import format_usdc
        
        # Zero
        assert format_usdc(0) == "0.000000"
        
        # Large values
        large = format_usdc(1000000000000)  # 1M USDC
        assert "1000000" in large
        
        # Negative (should still format, though unusual)
        negative = format_usdc(-1000000)
        assert "-" in negative
    
    def test_private_key_formats(self):
        """Various private key formats should work."""
        from circlekit.boa_utils import get_account_from_private_key
        
        key = "0000000000000000000000000000000000000000000000000000000000000001"
        
        # With 0x prefix
        addr1, _ = get_account_from_private_key("0x" + key)
        
        # Without 0x prefix
        addr2, _ = get_account_from_private_key(key)
        
        assert addr1 == addr2
    
    def test_invalid_private_key(self):
        """Invalid private key should raise."""
        from circlekit.boa_utils import get_account_from_private_key
        
        with pytest.raises((ValueError, Exception)):
            get_account_from_private_key("not-a-valid-key")
        
        with pytest.raises((ValueError, Exception)):
            get_account_from_private_key("0x00")  # Too short


# =============================================================================
# TEST: Chain Configuration Completeness
# =============================================================================

class TestChainConfigCompleteness:
    """Ensure all chain configs are complete and valid."""
    
    def test_all_chains_have_required_fields(self):
        """Every chain config should have all required fields."""
        from circlekit.constants import CHAIN_CONFIGS
        
        required_fields = [
            "chain_id",
            "name", 
            "rpc_url",
            "usdc_address",
            "gateway_address",
            "gateway_domain",
        ]
        
        for chain_name, config in CHAIN_CONFIGS.items():
            for field in required_fields:
                value = getattr(config, field, None)
                assert value is not None, f"{chain_name} missing {field}"
                if field != "is_testnet":
                    assert value != "", f"{chain_name} has empty {field}"
    
    def test_all_chains_have_valid_addresses(self):
        """All addresses should be valid Ethereum format."""
        from circlekit.constants import CHAIN_CONFIGS
        import re
        
        eth_address_pattern = re.compile(r"^0x[a-fA-F0-9]{40}$")
        
        for chain_name, config in CHAIN_CONFIGS.items():
            assert eth_address_pattern.match(config.usdc_address), \
                f"{chain_name} invalid usdc_address: {config.usdc_address}"
            assert eth_address_pattern.match(config.gateway_address), \
                f"{chain_name} invalid gateway_address: {config.gateway_address}"
    
    def test_all_chains_have_valid_rpc_urls(self):
        """All RPC URLs should be valid HTTPS URLs."""
        from circlekit.constants import CHAIN_CONFIGS
        
        for chain_name, config in CHAIN_CONFIGS.items():
            assert config.rpc_url.startswith("https://"), \
                f"{chain_name} RPC should use HTTPS: {config.rpc_url}"
    
    def test_testnet_flag_consistency(self):
        """Testnet chains should have is_testnet=True."""
        from circlekit.constants import CHAIN_CONFIGS
        
        testnet_keywords = ["testnet", "sepolia", "fuji"]
        
        for chain_name, config in CHAIN_CONFIGS.items():
            is_testnet_name = any(kw in chain_name.lower() for kw in testnet_keywords)
            assert config.is_testnet == is_testnet_name, \
                f"{chain_name} is_testnet mismatch"
    
    def test_chain_ids_are_unique(self):
        """No duplicate chain IDs."""
        from circlekit.constants import CHAIN_CONFIGS
        
        chain_ids = [c.chain_id for c in CHAIN_CONFIGS.values()]
        assert len(chain_ids) == len(set(chain_ids)), "Duplicate chain IDs found"
    
    def test_get_chain_config_all_chains(self):
        """get_chain_config should work for all chains."""
        from circlekit.constants import CHAIN_CONFIGS, get_chain_config
        
        for chain_name in CHAIN_CONFIGS.keys():
            config = get_chain_config(chain_name)
            assert config is not None
            assert config.name is not None
    
    def test_get_chain_by_id_all_chains(self):
        """get_chain_by_id should find all chains."""
        from circlekit.constants import CHAIN_CONFIGS, get_chain_by_id
        
        for chain_name, expected_config in CHAIN_CONFIGS.items():
            found = get_chain_by_id(expected_config.chain_id)
            assert found is not None, f"Chain ID {expected_config.chain_id} not found"
            assert found.chain_id == expected_config.chain_id


# =============================================================================
# TEST: Error Handling
# =============================================================================

class TestErrorHandling:
    """Test error handling in various scenarios."""
    
    def test_unsupported_chain(self):
        """Unsupported chain should raise clear error."""
        from circlekit.client import GatewayClient
        
        with pytest.raises(ValueError, match="Unsupported chain"):
            GatewayClient(
                chain="nonexistent-chain",
                private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
            )
    
    @pytest.mark.asyncio
    async def test_network_timeout_handling(self):
        """Network timeouts should be handled gracefully."""
        from circlekit.client import GatewayClient
        import httpx
        
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        
        # The supports() method catches exceptions and returns a result with error
        with patch.object(client._http, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.TimeoutException("Connection timed out")
            
            result = await client.supports("http://slow-server.example.com")
            # Should return a result indicating failure, not crash
            assert result.supported == False or result.error is not None
        
        await client.close()
    
    @pytest.mark.asyncio
    async def test_connection_error_handling(self):
        """Connection errors should be handled gracefully."""
        from circlekit.client import GatewayClient
        import httpx
        
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        
        # The supports() method catches exceptions and returns a result with error
        with patch.object(client._http, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.ConnectError("Connection refused")
            
            result = await client.supports("http://unreachable.example.com")
            # Should return a result indicating failure, not crash
            assert result.supported == False or result.error is not None
        
        await client.close()
    
    @pytest.mark.asyncio
    async def test_malformed_402_response_handling(self):
        """Malformed 402 responses should be handled."""
        from circlekit.client import GatewayClient
        
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        
        with patch.object(client._http, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 402
            mock_response.content = b"not valid json"
            mock_get.return_value = mock_response
            
            # Should handle gracefully
            result = await client.supports("http://bad-server.example.com")
            
            # Might fail to parse but shouldn't crash
            assert result.supported == False or result.error is not None
        
        await client.close()


# =============================================================================
# TEST: Security
# =============================================================================

class TestSecurity:
    """Test security-related aspects."""
    
    def test_signature_includes_nonce(self):
        """Payment signatures should include unique nonce."""
        from circlekit.x402 import create_payment_payload, PaymentRequirements
        
        requirements = PaymentRequirements(
            scheme="exact",
            network="eip155:5042002",
            asset="0x2D270e6886d130D724215A266106e6832161EAEd",
            amount="10000",
            pay_to="0x1234567890123456789012345678901234567890",
        )
        
        pk = "0x0000000000000000000000000000000000000000000000000000000000000001"
        
        payload1 = create_payment_payload(
            private_key=pk,
            payer_address="0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf",
            requirements=requirements,
        )
        
        payload2 = create_payment_payload(
            private_key=pk,
            payer_address="0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf",
            requirements=requirements,
        )
        
        # Signatures should be different due to different nonces
        assert payload1.signature != payload2.signature
    
    def test_payment_header_is_base64(self):
        """Payment header should be valid base64."""
        from circlekit.x402 import create_payment_header, PaymentRequirements
        
        requirements = PaymentRequirements(
            scheme="exact",
            network="eip155:5042002",
            asset="0x2D270e6886d130D724215A266106e6832161EAEd",
            amount="10000",
            pay_to="0x1234567890123456789012345678901234567890",
        )
        
        header = create_payment_header(
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
            payer_address="0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf",
            requirements=requirements,
        )
        
        # Should be valid base64
        decoded = base64.b64decode(header)
        data = json.loads(decoded)
        
        assert "signature" in data
        assert "authorization" in data
    
    def test_private_key_not_in_header(self):
        """Private key should not appear in payment header."""
        from circlekit.x402 import create_payment_header, PaymentRequirements
        
        private_key = "0x0000000000000000000000000000000000000000000000000000000000000001"
        
        requirements = PaymentRequirements(
            scheme="exact",
            network="eip155:5042002",
            asset="0x2D270e6886d130D724215A266106e6832161EAEd",
            amount="10000",
            pay_to="0x1234567890123456789012345678901234567890",
        )
        
        header = create_payment_header(
            private_key=private_key,
            payer_address="0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf",
            requirements=requirements,
        )
        
        # Decode and check
        decoded = base64.b64decode(header).decode()
        
        # Private key should NOT appear
        assert private_key not in decoded
        assert private_key.replace("0x", "") not in decoded


# =============================================================================
# TEST: Payment Amounts & Boundaries
# =============================================================================

class TestPaymentAmounts:
    """Test payment amount handling."""
    
    def test_minimum_payment(self):
        """Minimum payment (1 unit = 0.000001 USDC) should work."""
        from circlekit.x402 import create_payment_payload, PaymentRequirements
        
        requirements = PaymentRequirements(
            scheme="exact",
            network="eip155:5042002",
            asset="0x2D270e6886d130D724215A266106e6832161EAEd",
            amount="1",  # 0.000001 USDC
            pay_to="0x1234567890123456789012345678901234567890",
        )
        
        payload = create_payment_payload(
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
            payer_address="0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf",
            requirements=requirements,
        )
        
        assert payload.authorization["value"] == 1
    
    def test_large_payment(self):
        """Large payment amounts should work."""
        from circlekit.x402 import create_payment_payload, PaymentRequirements
        
        # 1 million USDC
        large_amount = str(1_000_000 * 1_000_000)
        
        requirements = PaymentRequirements(
            scheme="exact",
            network="eip155:5042002",
            asset="0x2D270e6886d130D724215A266106e6832161EAEd",
            amount=large_amount,
            pay_to="0x1234567890123456789012345678901234567890",
        )
        
        payload = create_payment_payload(
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
            payer_address="0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf",
            requirements=requirements,
        )
        
        assert payload.authorization["value"] == int(large_amount)
    
    def test_zero_payment_amount(self):
        """Zero amount should be handled (though unusual)."""
        from circlekit.x402 import create_payment_payload, PaymentRequirements
        
        requirements = PaymentRequirements(
            scheme="exact",
            network="eip155:5042002",
            asset="0x2D270e6886d130D724215A266106e6832161EAEd",
            amount="0",
            pay_to="0x1234567890123456789012345678901234567890",
        )
        
        payload = create_payment_payload(
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
            payer_address="0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf",
            requirements=requirements,
        )
        
        assert payload.authorization["value"] == 0


# =============================================================================
# TEST: Middleware Configuration
# =============================================================================

class TestMiddlewareConfiguration:
    """Test server middleware configuration."""
    
    def test_middleware_requires_seller_address(self):
        """Middleware should require seller address."""
        from circlekit.server import create_gateway_middleware
        
        # Should work with valid address
        middleware = create_gateway_middleware(
            seller_address="0x1234567890123456789012345678901234567890",
        )
        assert middleware is not None
    
    def test_middleware_default_chain(self):
        """Middleware should use default chain if not specified."""
        from circlekit.server import create_gateway_middleware
        
        middleware = create_gateway_middleware(
            seller_address="0x1234567890123456789012345678901234567890",
        )
        
        # Should have a chain config
        assert middleware._chain_config is not None
    
    def test_middleware_custom_chain(self):
        """Middleware should accept custom chain."""
        from circlekit.server import create_gateway_middleware
        
        middleware = create_gateway_middleware(
            seller_address="0x1234567890123456789012345678901234567890",
            chain="baseSepolia",
        )
        
        assert middleware._chain_config.chain_id == 84532
    
    def test_require_decorator_parses_amount(self):
        """require() decorator should parse amount correctly."""
        from circlekit.server import create_gateway_middleware
        
        middleware = create_gateway_middleware(
            seller_address="0x1234567890123456789012345678901234567890",
        )
        
        # Various amount formats
        decorator1 = middleware.require("0.01")
        decorator2 = middleware.require("$0.01")
        decorator3 = middleware.require("1.0")
        
        assert callable(decorator1)
        assert callable(decorator2)
        assert callable(decorator3)


# =============================================================================
# TEST: x402 Response Building
# =============================================================================

class TestX402ResponseBuilding:
    """Test 402 response construction."""
    
    def test_build_402_response_structure(self):
        """402 response should have correct structure."""
        from circlekit.x402 import build_402_response
        
        response = build_402_response(
            seller_address="0x1234567890123456789012345678901234567890",
            amount="10000",
            chain_id=5042002,
            usdc_address="0x2D270e6886d130D724215A266106e6832161EAEd",
            gateway_address="0x0077777d7eba4688bdef3e311b846f25870a19b9",
        )
        
        # Check structure
        assert response["x402Version"] == 2
        assert "accepts" in response
        assert len(response["accepts"]) == 1
        
        accept = response["accepts"][0]
        assert accept["scheme"] == "exact"
        assert accept["network"] == "eip155:5042002"
        assert accept["amount"] == "10000"
        assert accept["payTo"] == "0x1234567890123456789012345678901234567890"
    
    def test_build_402_response_gateway_extra(self):
        """402 response should include Gateway extra fields."""
        from circlekit.x402 import build_402_response
        
        response = build_402_response(
            seller_address="0x1234567890123456789012345678901234567890",
            amount="10000",
            chain_id=5042002,
            usdc_address="0x2D270e6886d130D724215A266106e6832161EAEd",
            gateway_address="0x0077777d7eba4688bdef3e311b846f25870a19b9",
        )
        
        accept = response["accepts"][0]
        assert "extra" in accept
        assert accept["extra"]["name"] == "GatewayWalletBatched"
        assert accept["extra"]["version"] == "1"


# =============================================================================
# TEST: Concurrency
# =============================================================================

class TestConcurrency:
    """Test concurrent operations."""
    
    @pytest.mark.asyncio
    async def test_multiple_clients_concurrent(self):
        """Multiple clients can operate concurrently."""
        from circlekit.client import GatewayClient
        
        # Create multiple clients
        clients = []
        for i in range(3):
            pk = f"0x000000000000000000000000000000000000000000000000000000000000000{i+1}"
            client = GatewayClient(chain="arcTestnet", private_key=pk)
            clients.append(client)
        
        # Each should have different address
        addresses = [c.address for c in clients]
        assert len(set(addresses)) == 3
        
        # Clean up
        for client in clients:
            await client.close()
    
    def test_multiple_signatures_independent(self):
        """Multiple signatures should be independent."""
        from circlekit.x402 import create_payment_payload, PaymentRequirements
        
        requirements = PaymentRequirements(
            scheme="exact",
            network="eip155:5042002",
            asset="0x2D270e6886d130D724215A266106e6832161EAEd",
            amount="10000",
            pay_to="0x1234567890123456789012345678901234567890",
        )
        
        # Generate multiple signatures in sequence
        signatures = []
        for _ in range(5):
            payload = create_payment_payload(
                private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
                payer_address="0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf",
                requirements=requirements,
            )
            signatures.append(payload.signature)
        
        # All should be unique (different nonces)
        assert len(set(signatures)) == 5


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
