"""
Comprehensive tests for circlekit Python SDK.

These tests verify that each module works correctly without hallucinations.
Run with: python -m pytest tests/test_circlekit.py -v
"""

import pytest
import json
import base64
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock


# ============================================================================
# TEST: constants.py
# ============================================================================

class TestConstants:
    """Test constants module."""
    
    def test_chain_configs_exist(self):
        """CHAIN_CONFIGS should have expected chains."""
        from circlekit.constants import CHAIN_CONFIGS
        
        assert "arcTestnet" in CHAIN_CONFIGS
        assert "baseSepolia" in CHAIN_CONFIGS
        assert "ethereumSepolia" in CHAIN_CONFIGS
    
    def test_arc_testnet_config(self):
        """Arc Testnet should have correct configuration."""
        from circlekit.constants import CHAIN_CONFIGS
        
        arc = CHAIN_CONFIGS["arcTestnet"]
        
        assert arc.chain_id == 5042002
        assert arc.name == "Arc Testnet"
        # Verified RPC from dRPC
        assert "arc-testnet.drpc.org" in arc.rpc_url
        # Verified USDC address
        assert arc.usdc_address == "0x2D270e6886d130D724215A266106e6832161EAEd"
        assert arc.gateway_address == "0x0077777d7eba4688bdef3e311b846f25870a19b9"
        assert arc.gateway_domain == 26  # Verified domain
        assert arc.is_testnet == True
    
    def test_protocol_constants(self):
        """Protocol constants should match x402 spec."""
        from circlekit.constants import (
            CIRCLE_BATCHING_NAME,
            CIRCLE_BATCHING_VERSION,
            CIRCLE_BATCHING_SCHEME,
            X402_VERSION,
            MIN_SIGNATURE_VALIDITY_SECONDS,
            USDC_DECIMALS,
        )
        
        assert CIRCLE_BATCHING_NAME == "GatewayWalletBatched"
        assert CIRCLE_BATCHING_VERSION == "1"
        assert CIRCLE_BATCHING_SCHEME == "exact"
        assert X402_VERSION == 2
        assert MIN_SIGNATURE_VALIDITY_SECONDS == 4 * 24 * 60 * 60  # 4 days
        assert USDC_DECIMALS == 6


# ============================================================================
# TEST: boa_utils.py
# ============================================================================

class TestBoaUtils:
    """Test boa_utils module."""
    
    def test_get_chain_config(self):
        """get_chain_config should return correct config."""
        from circlekit.boa_utils import get_chain_config
        
        config = get_chain_config("arcTestnet")
        assert config.chain_id == 5042002
        assert config.name == "Arc Testnet"
    
    def test_get_chain_config_invalid(self):
        """get_chain_config should raise for invalid chain."""
        from circlekit.boa_utils import get_chain_config
        
        with pytest.raises(ValueError, match="Unsupported chain"):
            get_chain_config("invalidChain")
    
    def test_get_rpc_url(self):
        """get_rpc_url should return correct URL."""
        from circlekit.boa_utils import get_rpc_url
        
        url = get_rpc_url("arcTestnet")
        # Verified RPC from dRPC
        assert "arc-testnet.drpc.org" in url
    
    def test_get_account_from_private_key(self):
        """get_account_from_private_key should derive correct address."""
        from circlekit.boa_utils import get_account_from_private_key
        
        # Known test vector: private key 1 -> specific address
        address, account = get_account_from_private_key(
            "0x0000000000000000000000000000000000000000000000000000000000000001"
        )
        
        assert address == "0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf"
        assert account is not None
    
    def test_get_account_without_0x_prefix(self):
        """get_account_from_private_key should work without 0x prefix."""
        from circlekit.boa_utils import get_account_from_private_key
        
        address, _ = get_account_from_private_key(
            "0000000000000000000000000000000000000000000000000000000000000001"
        )
        
        assert address == "0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf"
    
    def test_format_usdc(self):
        """format_usdc should format correctly."""
        from circlekit.boa_utils import format_usdc
        
        assert format_usdc(1000000) == "1.000000"  # 1 USDC
        assert format_usdc(10000) == "0.010000"    # 0.01 USDC
        assert format_usdc(1500000) == "1.500000"  # 1.5 USDC
        assert format_usdc(0) == "0.000000"
    
    def test_parse_usdc(self):
        """parse_usdc should parse correctly."""
        from circlekit.boa_utils import parse_usdc
        
        assert parse_usdc("1.0") == 1000000
        assert parse_usdc("0.01") == 10000
        assert parse_usdc("1.5") == 1500000
        assert parse_usdc("$0.01") == 10000  # With $ prefix
        assert parse_usdc("$1.50") == 1500000
    
    def test_generate_nonce(self):
        """generate_nonce should return 32 random bytes."""
        from circlekit.boa_utils import generate_nonce
        
        nonce1 = generate_nonce()
        nonce2 = generate_nonce()
        
        assert len(nonce1) == 32
        assert len(nonce2) == 32
        assert nonce1 != nonce2  # Should be random


# ============================================================================
# TEST: x402.py
# ============================================================================

class TestX402:
    """Test x402 protocol module."""
    
    def test_parse_402_response(self):
        """parse_402_response should parse valid 402 body."""
        from circlekit.x402 import parse_402_response
        
        body = {
            "x402Version": 2,
            "resource": {"url": "/api/test"},
            "accepts": [
                {
                    "scheme": "exact",
                    "network": "eip155:5042002",
                    "asset": "0x3600000000000000000000000000000000000000",
                    "amount": "10000",
                    "payTo": "0x1234567890123456789012345678901234567890",
                    "maxTimeoutSeconds": 345600,
                    "extra": {
                        "name": "GatewayWalletBatched",
                        "version": "1",
                        "verifyingContract": "0x0077777d7eba4688bdef3e311b846f25870a19b9"
                    }
                }
            ]
        }
        
        result = parse_402_response(body)
        
        assert result.x402_version == 2
        assert len(result.accepts) == 1
        assert result.accepts[0].scheme == "exact"
        assert result.accepts[0].network == "eip155:5042002"
        assert result.accepts[0].amount == "10000"
        assert result.accepts[0].is_gateway_batched == True
    
    def test_parse_402_response_from_json_string(self):
        """parse_402_response should handle JSON string input."""
        from circlekit.x402 import parse_402_response
        
        body = json.dumps({
            "x402Version": 2,
            "accepts": [{"scheme": "exact", "network": "eip155:1", "amount": "100", "payTo": "0x123"}]
        })
        
        result = parse_402_response(body)
        assert result.x402_version == 2
    
    def test_parse_402_response_invalid(self):
        """parse_402_response should raise on invalid input."""
        from circlekit.x402 import parse_402_response
        
        with pytest.raises(ValueError, match="x402Version"):
            parse_402_response({"accepts": []})
        
        with pytest.raises(ValueError, match="accepts"):
            parse_402_response({"x402Version": 2})
    
    def test_payment_requirements_chain_id(self):
        """PaymentRequirements.chain_id should extract from network."""
        from circlekit.x402 import PaymentRequirements
        
        req = PaymentRequirements(
            scheme="exact",
            network="eip155:5042002",
            asset="0x123",
            amount="10000",
            pay_to="0x456",
        )
        
        assert req.chain_id == 5042002
    
    def test_payment_requirements_amount_formatted(self):
        """PaymentRequirements.amount_formatted should format correctly."""
        from circlekit.x402 import PaymentRequirements
        
        req = PaymentRequirements(
            scheme="exact",
            network="eip155:1",
            asset="0x123",
            amount="10000",  # 0.01 USDC
            pay_to="0x456",
        )
        
        assert req.amount_formatted == "$0.010000"
    
    def test_is_batch_payment(self):
        """is_batch_payment should detect Gateway payments."""
        from circlekit.x402 import is_batch_payment, PaymentRequirements
        
        gateway_req = PaymentRequirements(
            scheme="exact",
            network="eip155:1",
            asset="0x123",
            amount="100",
            pay_to="0x456",
            extra={"name": "GatewayWalletBatched"}
        )
        
        other_req = PaymentRequirements(
            scheme="exact",
            network="eip155:1",
            asset="0x123",
            amount="100",
            pay_to="0x456",
            extra={"name": "SomethingElse"}
        )
        
        assert is_batch_payment(gateway_req) == True
        assert is_batch_payment(other_req) == False
    
    def test_get_verifying_contract(self):
        """get_verifying_contract should extract Gateway address."""
        from circlekit.x402 import get_verifying_contract, PaymentRequirements
        
        gateway_req = PaymentRequirements(
            scheme="exact",
            network="eip155:5042002",
            asset="0x123",
            amount="100",
            pay_to="0x456",
            extra={
                "name": "GatewayWalletBatched",
                "verifyingContract": "0x0077777d7eba4688bdef3e311b846f25870a19b9"
            }
        )
        
        assert get_verifying_contract(gateway_req) == "0x0077777d7eba4688bdef3e311b846f25870a19b9"
        
        # Also works with dict
        req_dict = {
            "extra": {"verifyingContract": "0xABCD"}
        }
        assert get_verifying_contract(req_dict) == "0xABCD"
        
        # Returns None if not present
        empty_req = PaymentRequirements(
            scheme="exact",
            network="eip155:1",
            asset="0x123",
            amount="100",
            pay_to="0x456",
        )
        assert get_verifying_contract(empty_req) is None
    
    def test_build_402_response(self):
        """build_402_response should create valid response."""
        from circlekit.x402 import build_402_response
        
        response = build_402_response(
            seller_address="0x1234567890123456789012345678901234567890",
            amount="10000",
            chain_id=5042002,
            usdc_address="0x3600000000000000000000000000000000000000",
            gateway_address="0x0077777d7eba4688bdef3e311b846f25870a19b9",
            description="Test resource",
        )
        
        assert response["x402Version"] == 2
        assert len(response["accepts"]) == 1
        assert response["accepts"][0]["amount"] == "10000"
        assert response["accepts"][0]["scheme"] == "exact"
        assert response["accepts"][0]["network"] == "eip155:5042002"
        assert response["accepts"][0]["extra"]["name"] == "GatewayWalletBatched"
    
    def test_create_payment_payload(self):
        """create_payment_payload should create signed payload."""
        from circlekit.x402 import create_payment_payload, PaymentRequirements
        
        requirements = PaymentRequirements(
            scheme="exact",
            network="eip155:5042002",
            asset="0x3600000000000000000000000000000000000000",
            amount="10000",
            pay_to="0x1234567890123456789012345678901234567890",
            extra={"name": "GatewayWalletBatched"}
        )
        
        payload = create_payment_payload(
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
            payer_address="0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf",
            requirements=requirements,
        )
        
        assert payload.signature is not None
        assert len(payload.signature) > 0
        assert payload.authorization["from"] == "0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf"
        assert payload.authorization["to"] == "0x1234567890123456789012345678901234567890"
        assert payload.authorization["value"] == 10000
    
    def test_create_payment_header(self):
        """create_payment_header should return base64 string."""
        from circlekit.x402 import create_payment_header, PaymentRequirements
        
        requirements = PaymentRequirements(
            scheme="exact",
            network="eip155:5042002",
            asset="0x3600000000000000000000000000000000000000",
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
        assert "accepted" in data
    
    def test_decode_payment_header(self):
        """decode_payment_header should decode base64 header."""
        from circlekit.x402 import decode_payment_header
        
        original = {"test": "data", "number": 123}
        encoded = base64.b64encode(json.dumps(original).encode()).decode()
        
        decoded = decode_payment_header(encoded)
        
        assert decoded == original


# ============================================================================
# TEST: client.py
# ============================================================================

class TestGatewayClient:
    """Test GatewayClient class."""
    
    def test_client_initialization(self):
        """GatewayClient should initialize with correct properties."""
        from circlekit.client import GatewayClient
        
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        
        assert client.address == "0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf"
        assert client.chain_name == "Arc Testnet"
        assert client.chain_id == 5042002
        assert client.domain == 26  # Verified Gateway domain
    
    def test_client_invalid_chain(self):
        """GatewayClient should raise for invalid chain."""
        from circlekit.client import GatewayClient
        
        with pytest.raises(ValueError, match="Unsupported chain"):
            GatewayClient(
                chain="invalidChain",
                private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
            )
    
    @pytest.mark.asyncio
    async def test_client_supports_free_resource(self):
        """supports() should return True for free resources."""
        from circlekit.client import GatewayClient
        
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        
        # Mock a 200 response (free resource)
        with patch.object(client._http, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response
            
            result = await client.supports("http://example.com/free")
            
            assert result.supported == True
            assert result.error is None
        
        await client.close()
    
    @pytest.mark.asyncio
    async def test_client_supports_402_with_gateway(self):
        """supports() should detect Gateway support from 402."""
        from circlekit.client import GatewayClient
        
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        
        # Mock a 402 response with Gateway option
        with patch.object(client._http, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 402
            mock_response.content = json.dumps({
                "x402Version": 2,
                "accepts": [{
                    "scheme": "exact",
                    "network": "eip155:5042002",
                    "amount": "10000",
                    "payTo": "0x123",
                    "extra": {"name": "GatewayWalletBatched"}
                }]
            }).encode()
            mock_get.return_value = mock_response
            
            result = await client.supports("http://example.com/paid")
            
            assert result.supported == True
            assert result.requirements is not None
            assert result.requirements["amount"] == "10000"
        
        await client.close()


# ============================================================================
# TEST: server.py
# ============================================================================

class TestGatewayMiddleware:
    """Test server middleware."""
    
    def test_create_gateway_middleware(self):
        """create_gateway_middleware should create valid middleware."""
        from circlekit.server import create_gateway_middleware
        
        middleware = create_gateway_middleware(
            seller_address="0x1234567890123456789012345678901234567890",
            chain="arcTestnet",
        )
        
        assert middleware._config.seller_address == "0x1234567890123456789012345678901234567890"
        assert middleware._chain_config.chain_id == 5042002
    
    def test_middleware_require_returns_decorator(self):
        """require() should return a callable decorator."""
        from circlekit.server import create_gateway_middleware
        
        middleware = create_gateway_middleware(
            seller_address="0x1234567890123456789012345678901234567890",
        )
        
        decorator = middleware.require("$0.01")
        
        assert callable(decorator)


# ============================================================================
# TEST: boa_utils.py transaction helpers
# ============================================================================

class TestBoaTransactionHelpers:
    """Test transaction execution helpers."""
    
    def test_parse_usdc(self):
        """parse_usdc should convert decimal to raw amount."""
        from circlekit.boa_utils import parse_usdc
        
        assert parse_usdc("1.0") == 1000000
        assert parse_usdc("0.01") == 10000
        assert parse_usdc("$5.50") == 5500000
        assert parse_usdc("100") == 100000000
    
    def test_format_usdc(self):
        """format_usdc should convert raw amount to decimal string."""
        from circlekit.boa_utils import format_usdc
        
        assert format_usdc(1000000) == "1.000000"
        assert format_usdc(10000) == "0.010000"
        assert format_usdc(5500000) == "5.500000"
    
    def test_check_allowance_function_exists(self):
        """check_allowance should be importable."""
        from circlekit.boa_utils import check_allowance
        assert callable(check_allowance)
    
    def test_execute_approve_function_exists(self):
        """execute_approve should be importable."""
        from circlekit.boa_utils import execute_approve
        assert callable(execute_approve)
    
    def test_execute_deposit_function_exists(self):
        """execute_deposit should be importable."""
        from circlekit.boa_utils import execute_deposit
        assert callable(execute_deposit)
    
    def test_get_usdc_balance_function_exists(self):
        """get_usdc_balance should be importable."""
        from circlekit.boa_utils import get_usdc_balance
        assert callable(get_usdc_balance)
    
    def test_get_gateway_balance_function_exists(self):
        """get_gateway_balance should be importable."""
        from circlekit.boa_utils import get_gateway_balance
        assert callable(get_gateway_balance)


# ============================================================================
# TEST: client.py deposit/withdraw
# ============================================================================

class TestGatewayClientDepositWithdraw:
    """Test deposit and withdraw methods."""
    
    @pytest.mark.asyncio
    async def test_deposit_checks_allowance(self):
        """deposit() should check allowance before depositing."""
        from circlekit.client import GatewayClient
        
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        
        # Mock the boa functions
        with patch('circlekit.client.check_allowance', return_value=0) as mock_check, \
             patch('circlekit.client.execute_approve', return_value="0xapproval") as mock_approve, \
             patch('circlekit.client.execute_deposit', return_value="0xdeposit") as mock_deposit:
            
            result = await client.deposit("1.0")
            
            # Should have checked allowance
            mock_check.assert_called_once()
            
            # Should have approved (since allowance was 0)
            mock_approve.assert_called_once()
            
            # Should have deposited
            mock_deposit.assert_called_once()
            
            assert result.approval_tx_hash == "0xapproval"
            assert result.deposit_tx_hash == "0xdeposit"
            assert result.amount == 1000000
            assert result.formatted_amount == "1.000000"
        
        await client.close()
    
    @pytest.mark.asyncio
    async def test_deposit_skips_approval_if_sufficient(self):
        """deposit() should skip approval if allowance is sufficient."""
        from circlekit.client import GatewayClient
        
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        
        # Mock the boa functions - sufficient allowance
        with patch('circlekit.client.check_allowance', return_value=10000000) as mock_check, \
             patch('circlekit.client.execute_approve') as mock_approve, \
             patch('circlekit.client.execute_deposit', return_value="0xdeposit") as mock_deposit:
            
            result = await client.deposit("1.0")
            
            # Should have checked allowance
            mock_check.assert_called_once()
            
            # Should NOT have approved (sufficient allowance)
            mock_approve.assert_not_called()
            
            # Should have deposited
            mock_deposit.assert_called_once()
            
            assert result.approval_tx_hash is None
            assert result.deposit_tx_hash == "0xdeposit"
        
        await client.close()
    
    @pytest.mark.asyncio
    async def test_withdraw_calls_gateway_api(self):
        """withdraw() should call the Gateway API."""
        from circlekit.client import GatewayClient
        
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        
        # Mock the HTTP response
        with patch.object(client._http, 'post', new_callable=AsyncMock) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "transactionHash": "0xwithdraw123",
                "status": "success",
            }
            mock_post.return_value = mock_response
            
            result = await client.withdraw("5.0")
            
            # Should have called the API
            mock_post.assert_called_once()
            
            # Check the result
            assert result.mint_tx_hash == "0xwithdraw123"
            assert result.amount == 5000000
            assert result.formatted_amount == "5.000000"
            assert result.source_chain == "Arc Testnet"
            assert result.destination_chain == "Arc Testnet"
        
        await client.close()
    
    @pytest.mark.asyncio
    async def test_withdraw_cross_chain(self):
        """withdraw() should support cross-chain withdrawals."""
        from circlekit.client import GatewayClient
        
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        
        # Mock the HTTP response
        with patch.object(client._http, 'post', new_callable=AsyncMock) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "transactionHash": "0xcrosschain",
                "status": "success",
            }
            mock_post.return_value = mock_response
            
            result = await client.withdraw(
                "10.0",
                chain="baseSepolia",
                recipient="0x9999999999999999999999999999999999999999",
            )
            
            assert result.source_chain == "Arc Testnet"
            assert result.destination_chain == "Base Sepolia"
            assert result.recipient == "0x9999999999999999999999999999999999999999"
        
        await client.close()


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
