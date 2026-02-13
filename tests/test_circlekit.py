"""
Comprehensive tests for circlekit Python SDK.

Run with: python -m pytest tests/test_circlekit.py -v
"""

import pytest
import json
import base64
import time
from unittest.mock import patch, MagicMock, AsyncMock


# ============================================================================
# TEST: constants.py
# ============================================================================

class TestConstants:
    """Test constants module."""

    def test_chain_configs_exist(self):
        from circlekit.constants import CHAIN_CONFIGS
        assert "arcTestnet" in CHAIN_CONFIGS
        assert "baseSepolia" in CHAIN_CONFIGS
        assert "ethereumSepolia" in CHAIN_CONFIGS

    def test_arc_testnet_config(self):
        from circlekit.constants import CHAIN_CONFIGS
        arc = CHAIN_CONFIGS["arcTestnet"]
        assert arc.chain_id == 5042002
        assert arc.name == "Arc Testnet"
        assert "arc-testnet.drpc.org" in arc.rpc_url
        assert arc.usdc_address == "0x3600000000000000000000000000000000000000"
        assert arc.gateway_domain == 26
        assert arc.is_testnet is True

    def test_gateway_domain_ids_correct(self):
        """Gateway domain IDs must match Circle's GATEWAY_DOMAINS, not chain IDs."""
        from circlekit.constants import CHAIN_CONFIGS
        expected = {
            "arcTestnet": 26,
            "baseSepolia": 6,
            "ethereumSepolia": 0,
            "avalancheFuji": 1,
            "hyperEvmTestnet": 19,
            "sonicTestnet": 13,
            "worldChainSepolia": 14,
            "seiAtlantic": 16,
            "ethereum": 0,
            "base": 6,
            "arbitrum": 3,
            "polygon": 7,
            "optimism": 2,
            "avalanche": 1,
            "sonic": 13,
            "unichain": 10,
            "worldChain": 14,
            "hyperEvm": 19,
            "sei": 16,
        }
        for chain_name, expected_domain in expected.items():
            assert CHAIN_CONFIGS[chain_name].gateway_domain == expected_domain, \
                f"{chain_name} domain should be {expected_domain}, got {CHAIN_CONFIGS[chain_name].gateway_domain}"

    def test_mainnet_gateway_addresses(self):
        """Mainnet chains must use mainnet gateway addresses."""
        from circlekit.constants import CHAIN_CONFIGS, MAINNET_GATEWAY_WALLET, MAINNET_GATEWAY_MINTER
        mainnet_chains = ["ethereum", "base", "arbitrum", "polygon", "optimism", "avalanche"]
        for chain_name in mainnet_chains:
            config = CHAIN_CONFIGS[chain_name]
            assert config.gateway_address == MAINNET_GATEWAY_WALLET, \
                f"{chain_name} gateway_address wrong"
            assert config.gateway_minter == MAINNET_GATEWAY_MINTER, \
                f"{chain_name} gateway_minter wrong"

    def test_testnet_gateway_addresses(self):
        """Testnet chains must use testnet gateway addresses."""
        from circlekit.constants import CHAIN_CONFIGS, TESTNET_GATEWAY_WALLET, TESTNET_GATEWAY_MINTER
        testnet_chains = ["arcTestnet", "baseSepolia", "ethereumSepolia", "avalancheFuji"]
        for chain_name in testnet_chains:
            config = CHAIN_CONFIGS[chain_name]
            assert config.gateway_address == TESTNET_GATEWAY_WALLET, \
                f"{chain_name} gateway_address wrong"
            assert config.gateway_minter == TESTNET_GATEWAY_MINTER, \
                f"{chain_name} gateway_minter wrong"

    def test_chain_config_has_gateway_minter(self):
        """Every chain config must have a gateway_minter field."""
        from circlekit.constants import CHAIN_CONFIGS
        for chain_name, config in CHAIN_CONFIGS.items():
            assert hasattr(config, "gateway_minter"), f"{chain_name} missing gateway_minter"
            assert config.gateway_minter.startswith("0x"), f"{chain_name} gateway_minter invalid"

    def test_protocol_constants(self):
        from circlekit.constants import (
            CIRCLE_BATCHING_NAME, CIRCLE_BATCHING_VERSION,
            CIRCLE_BATCHING_SCHEME, X402_VERSION, USDC_DECIMALS,
        )
        assert CIRCLE_BATCHING_NAME == "GatewayWalletBatched"
        assert CIRCLE_BATCHING_VERSION == "1"
        assert CIRCLE_BATCHING_SCHEME == "exact"
        assert X402_VERSION == 2
        assert USDC_DECIMALS == 6

    def test_usdc_constants_removed(self):
        """USDC_TOKEN_NAME, USDC_TOKEN_VERSION, EIP712_DOMAIN_TYPE should no longer exist."""
        from circlekit import constants
        assert not hasattr(constants, "USDC_TOKEN_NAME")
        assert not hasattr(constants, "USDC_TOKEN_VERSION")
        assert not hasattr(constants, "EIP712_DOMAIN_TYPE")
        assert not hasattr(constants, "TRANSFER_WITH_AUTHORIZATION_TYPE")


# ============================================================================
# TEST: signer.py
# ============================================================================

class TestSigner:
    """Test Signer protocol and PrivateKeySigner."""

    def test_private_key_signer_address(self):
        from circlekit.signer import PrivateKeySigner
        signer = PrivateKeySigner("0x0000000000000000000000000000000000000000000000000000000000000001")
        assert signer.address == "0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf"

    def test_private_key_signer_sign_typed_data(self):
        from circlekit.signer import PrivateKeySigner
        signer = PrivateKeySigner("0x0000000000000000000000000000000000000000000000000000000000000001")
        domain = {"name": "Test", "version": "1"}
        types = {"Message": [{"name": "content", "type": "string"}]}
        message = {"content": "hello"}
        sig = signer.sign_typed_data(domain, types, "Message", message)
        assert isinstance(sig, str)
        assert len(sig) > 0

    def test_private_key_signer_satisfies_protocol(self):
        from circlekit.signer import Signer, PrivateKeySigner
        signer = PrivateKeySigner("0x0000000000000000000000000000000000000000000000000000000000000001")
        assert isinstance(signer, Signer)


# ============================================================================
# TEST: boa_utils.py
# ============================================================================

class TestBoaUtils:
    """Test boa_utils module."""

    def test_get_chain_config(self):
        from circlekit.boa_utils import get_chain_config
        config = get_chain_config("arcTestnet")
        assert config.chain_id == 5042002

    def test_get_chain_config_invalid(self):
        from circlekit.boa_utils import get_chain_config
        with pytest.raises(ValueError, match="Unsupported chain"):
            get_chain_config("invalidChain")

    def test_get_rpc_url(self):
        from circlekit.boa_utils import get_rpc_url
        url = get_rpc_url("arcTestnet")
        assert "arc-testnet.drpc.org" in url

    def test_get_account_from_private_key(self):
        from circlekit.boa_utils import get_account_from_private_key
        address, account = get_account_from_private_key(
            "0x0000000000000000000000000000000000000000000000000000000000000001"
        )
        assert address == "0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf"

    def test_get_account_without_0x_prefix(self):
        from circlekit.boa_utils import get_account_from_private_key
        address, _ = get_account_from_private_key(
            "0000000000000000000000000000000000000000000000000000000000000001"
        )
        assert address == "0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf"

    def test_format_usdc(self):
        from circlekit.boa_utils import format_usdc
        assert format_usdc(1000000) == "1.000000"
        assert format_usdc(10000) == "0.010000"
        assert format_usdc(0) == "0.000000"

    def test_parse_usdc(self):
        from circlekit.boa_utils import parse_usdc
        assert parse_usdc("1.0") == 1000000
        assert parse_usdc("0.01") == 10000
        assert parse_usdc("$0.01") == 10000
        assert parse_usdc("$1.50") == 1500000

    def test_parse_usdc_rounding(self):
        """parse_usdc should round, not truncate (half-up)."""
        from circlekit.boa_utils import parse_usdc
        # $0.019999 * 1e6 = 19999.0 -> rounds to 19999
        assert parse_usdc("$0.019999") == 19999
        # $0.0199999 * 1e6 = 19999.9 -> rounds to 20000
        assert parse_usdc("$0.0199999") == 20000
        # $0.0100005 * 1e6 = 10000.5 -> rounds to 10001 (half up)
        assert parse_usdc("$0.0100005") == 10001

    def test_generate_nonce(self):
        from circlekit.boa_utils import generate_nonce
        nonce1 = generate_nonce()
        nonce2 = generate_nonce()
        assert len(nonce1) == 32
        assert nonce1 != nonce2

    def test_sign_typed_data_removed(self):
        """sign_typed_data should no longer exist in boa_utils (moved to signer)."""
        from circlekit import boa_utils
        assert not hasattr(boa_utils, "sign_typed_data")


# ============================================================================
# TEST: x402.py
# ============================================================================

class TestX402:
    """Test x402 protocol module."""

    def test_parse_402_response(self):
        from circlekit.x402 import parse_402_response
        body = {
            "x402Version": 2,
            "resource": {"url": "/api/test"},
            "accepts": [{
                "scheme": "exact",
                "network": "eip155:5042002",
                "asset": "0x3600000000000000000000000000000000000000",
                "amount": "10000",
                "payTo": "0x1234567890123456789012345678901234567890",
                "maxTimeoutSeconds": 345600,
                "extra": {
                    "name": "GatewayWalletBatched",
                    "version": "1",
                    "verifyingContract": "0x0077777d7EBA4688BDeF3E311b846F25870A19B9",
                }
            }]
        }
        result = parse_402_response(body)
        assert result.x402_version == 2
        assert len(result.accepts) == 1
        assert result.accepts[0].is_gateway_batched is True

    def test_parse_402_response_invalid(self):
        from circlekit.x402 import parse_402_response
        with pytest.raises(ValueError, match="x402Version"):
            parse_402_response({"accepts": []})
        with pytest.raises(ValueError, match="accepts"):
            parse_402_response({"x402Version": 2})

    def test_is_batch_payment_requires_name_and_version(self):
        """is_batch_payment must check BOTH name AND version."""
        from circlekit.x402 import is_batch_payment, PaymentRequirements
        # Both name and version -> True
        assert is_batch_payment(PaymentRequirements(
            scheme="exact", network="eip155:1", asset="0x123", amount="100", pay_to="0x456",
            extra={"name": "GatewayWalletBatched", "version": "1"}
        )) is True
        # Only name -> False
        assert is_batch_payment(PaymentRequirements(
            scheme="exact", network="eip155:1", asset="0x123", amount="100", pay_to="0x456",
            extra={"name": "GatewayWalletBatched"}
        )) is False
        # Wrong version -> False
        assert is_batch_payment(PaymentRequirements(
            scheme="exact", network="eip155:1", asset="0x123", amount="100", pay_to="0x456",
            extra={"name": "GatewayWalletBatched", "version": "2"}
        )) is False

    def test_get_verifying_contract_validates_string(self):
        """get_verifying_contract must verify that verifyingContract is a string."""
        from circlekit.x402 import get_verifying_contract, PaymentRequirements
        # String -> returns it
        req = PaymentRequirements(
            scheme="exact", network="eip155:1", asset="0x123", amount="100", pay_to="0x456",
            extra={"verifyingContract": "0xABCD"}
        )
        assert get_verifying_contract(req) == "0xABCD"
        # Non-string (int) -> returns None
        req2 = PaymentRequirements(
            scheme="exact", network="eip155:1", asset="0x123", amount="100", pay_to="0x456",
            extra={"verifyingContract": 12345}
        )
        assert get_verifying_contract(req2) is None
        # Missing -> None
        req3 = PaymentRequirements(
            scheme="exact", network="eip155:1", asset="0x123", amount="100", pay_to="0x456",
        )
        assert get_verifying_contract(req3) is None

    def test_create_payment_payload_uses_gateway_domain(self):
        """EIP-712 domain must be GatewayWalletBatched, NOT USDC."""
        from circlekit.x402 import create_payment_payload, PaymentRequirements
        from circlekit.signer import PrivateKeySigner

        signer = PrivateKeySigner("0x0000000000000000000000000000000000000000000000000000000000000001")
        requirements = PaymentRequirements(
            scheme="exact",
            network="eip155:5042002",
            asset="0x3600000000000000000000000000000000000000",
            amount="10000",
            pay_to="0x1234567890123456789012345678901234567890",
            extra={
                "name": "GatewayWalletBatched",
                "version": "1",
                "verifyingContract": "0x0077777d7EBA4688BDeF3E311b846F25870A19B9",
            }
        )
        payload = create_payment_payload(signer, requirements)
        assert payload.signature is not None
        assert len(payload.signature) > 0
        assert payload.x402_version == 2

    def test_authorization_fields_are_strings(self):
        """Authorization value, validAfter, validBefore must be strings, not ints."""
        from circlekit.x402 import create_payment_payload, PaymentRequirements
        from circlekit.signer import PrivateKeySigner

        signer = PrivateKeySigner("0x0000000000000000000000000000000000000000000000000000000000000001")
        requirements = PaymentRequirements(
            scheme="exact",
            network="eip155:5042002",
            asset="0x3600000000000000000000000000000000000000",
            amount="10000",
            pay_to="0x1234567890123456789012345678901234567890",
            extra={
                "name": "GatewayWalletBatched",
                "version": "1",
                "verifyingContract": "0x0077777d7EBA4688BDeF3E311b846F25870A19B9",
            }
        )
        payload = create_payment_payload(signer, requirements)
        assert isinstance(payload.authorization["value"], str)
        assert isinstance(payload.authorization["validAfter"], str)
        assert isinstance(payload.authorization["validBefore"], str)

    def test_valid_after_has_clock_skew_buffer(self):
        """validAfter should be current_time - 600 (10 min buffer)."""
        from circlekit.x402 import create_payment_payload, PaymentRequirements
        from circlekit.signer import PrivateKeySigner

        signer = PrivateKeySigner("0x0000000000000000000000000000000000000000000000000000000000000001")
        requirements = PaymentRequirements(
            scheme="exact",
            network="eip155:5042002",
            asset="0x3600000000000000000000000000000000000000",
            amount="10000",
            pay_to="0x1234567890123456789012345678901234567890",
            max_timeout_seconds=345600,
            extra={
                "name": "GatewayWalletBatched",
                "version": "1",
                "verifyingContract": "0x0077777d7EBA4688BDeF3E311b846F25870A19B9",
            }
        )
        before = int(time.time())
        payload = create_payment_payload(signer, requirements)
        after = int(time.time())

        valid_after = int(payload.authorization["validAfter"])
        valid_before = int(payload.authorization["validBefore"])

        # validAfter should be ~ now - 600
        assert before - 600 - 1 <= valid_after <= after - 600 + 1
        # validBefore should be ~ now + max_timeout_seconds
        assert before + 345600 - 1 <= valid_before <= after + 345600 + 1

    def test_payment_header_structure(self):
        """Header must have {x402Version, payload: {authorization, signature}, resource, accepted}."""
        from circlekit.x402 import create_payment_header, decode_payment_header, PaymentRequirements
        from circlekit.signer import PrivateKeySigner

        signer = PrivateKeySigner("0x0000000000000000000000000000000000000000000000000000000000000001")
        requirements = PaymentRequirements(
            scheme="exact",
            network="eip155:5042002",
            asset="0x3600000000000000000000000000000000000000",
            amount="10000",
            pay_to="0x1234567890123456789012345678901234567890",
            extra={
                "name": "GatewayWalletBatched",
                "version": "1",
                "verifyingContract": "0x0077777d7EBA4688BDeF3E311b846F25870A19B9",
            }
        )
        resource = {"url": "/api/test", "description": "test"}

        header = create_payment_header(signer, requirements, resource=resource)
        decoded = decode_payment_header(header)

        # Must have these top-level keys
        assert "x402Version" in decoded
        assert "payload" in decoded
        assert "resource" in decoded
        assert "accepted" in decoded

        # payload must have authorization and signature
        assert "authorization" in decoded["payload"]
        assert "signature" in decoded["payload"]

        # resource should match what we passed
        assert decoded["resource"]["url"] == "/api/test"

    def test_build_402_response(self):
        from circlekit.x402 import build_402_response
        response = build_402_response(
            seller_address="0x1234567890123456789012345678901234567890",
            amount="10000",
            chain_id=5042002,
            usdc_address="0x3600000000000000000000000000000000000000",
            gateway_address="0x0077777d7EBA4688BDeF3E311b846F25870A19B9",
        )
        assert response["x402Version"] == 2
        assert len(response["accepts"]) == 1
        assert response["accepts"][0]["extra"]["name"] == "GatewayWalletBatched"


# ============================================================================
# TEST: x402 header helpers
# ============================================================================

class TestX402Headers:
    """Test x402 header encode/decode helpers."""

    def test_encode_decode_payment_required_roundtrip(self):
        from circlekit.x402 import encode_payment_required, decode_payment_required
        body = {
            "x402Version": 2,
            "resource": {"url": "/api/test"},
            "accepts": [{
                "scheme": "exact",
                "network": "eip155:5042002",
                "asset": "0x3600000000000000000000000000000000000000",
                "amount": "10000",
                "payTo": "0x1234567890123456789012345678901234567890",
                "maxTimeoutSeconds": 345600,
                "extra": {
                    "name": "GatewayWalletBatched",
                    "version": "1",
                    "verifyingContract": "0x0077777d7EBA4688BDeF3E311b846F25870A19B9",
                }
            }]
        }
        encoded = encode_payment_required(body)
        decoded = decode_payment_required(encoded)
        assert decoded.x402_version == 2
        assert len(decoded.accepts) == 1
        assert decoded.accepts[0].network == "eip155:5042002"
        assert decoded.accepts[0].amount == "10000"

    def test_decode_payment_required_from_header(self):
        """Decode a manually constructed base64 header."""
        import base64, json
        from circlekit.x402 import decode_payment_required
        data = {
            "x402Version": 2,
            "resource": {},
            "accepts": [{"scheme": "exact", "network": "eip155:1", "amount": "5000", "payTo": "0xabc"}],
        }
        header = base64.b64encode(json.dumps(data).encode()).decode()
        result = decode_payment_required(header)
        assert result.x402_version == 2
        assert result.accepts[0].amount == "5000"

    def test_encode_decode_payment_response_roundtrip(self):
        from circlekit.x402 import encode_payment_response, decode_payment_response
        info = {"success": True, "transaction": "0xtx123", "payer": "0xabc", "network": "eip155:5042002"}
        encoded = encode_payment_response(info)
        decoded = decode_payment_response(encoded)
        assert decoded["success"] is True
        assert decoded["transaction"] == "0xtx123"
        assert decoded["payer"] == "0xabc"

    def test_get_payment_required_v2_header(self):
        """get_payment_required decodes v2 header."""
        from circlekit.x402 import get_payment_required, encode_payment_required
        body = {
            "x402Version": 2,
            "resource": {},
            "accepts": [{"scheme": "exact", "network": "eip155:1", "amount": "5000", "payTo": "0xabc"}],
        }
        header = encode_payment_required(body)
        result = get_payment_required(header, None)
        assert result.x402_version == 2
        assert result.accepts[0].amount == "5000"

    def test_get_payment_required_v1_body_fallback(self):
        """get_payment_required accepts v1 body when no header."""
        from circlekit.x402 import get_payment_required
        body = {
            "x402Version": 1,
            "resource": {},
            "accepts": [{"scheme": "exact", "network": "eip155:1", "amount": "3000", "payTo": "0xdef"}],
        }
        result = get_payment_required(None, body)
        assert result.x402_version == 1
        assert result.accepts[0].amount == "3000"

    def test_get_payment_required_rejects_v2_body_without_header(self):
        """get_payment_required raises on v2 body without PAYMENT-REQUIRED header."""
        from circlekit.x402 import get_payment_required
        body = {
            "x402Version": 2,
            "resource": {},
            "accepts": [{"scheme": "exact", "network": "eip155:1", "amount": "5000", "payTo": "0xabc"}],
        }
        with pytest.raises(ValueError, match="Invalid payment required response"):
            get_payment_required(None, body)

    def test_get_payment_required_malformed_header_raises(self):
        """get_payment_required raises on malformed header (does not fall back to body)."""
        from circlekit.x402 import get_payment_required
        body = {
            "x402Version": 1,
            "resource": {},
            "accepts": [{"scheme": "exact", "network": "eip155:1", "amount": "5000", "payTo": "0xabc"}],
        }
        with pytest.raises(Exception):
            get_payment_required("not-valid-base64!!!", body)

    @pytest.mark.asyncio
    async def test_client_pay_reads_header_first(self):
        """Client reads PAYMENT-REQUIRED header when present, ignoring body."""
        from circlekit.client import GatewayClient
        from circlekit.x402 import encode_payment_required
        import base64

        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )

        header_data = {
            "x402Version": 2,
            "resource": {"url": "/api/test"},
            "accepts": [{
                "scheme": "exact",
                "network": "eip155:5042002",
                "asset": "0x3600000000000000000000000000000000000000",
                "amount": "10000",
                "payTo": "0x1234567890123456789012345678901234567890",
                "maxTimeoutSeconds": 345600,
                "extra": {
                    "name": "GatewayWalletBatched",
                    "version": "1",
                    "verifyingContract": "0x0077777d7EBA4688BDeF3E311b846F25870A19B9",
                }
            }]
        }
        encoded_header = encode_payment_required(header_data)

        with patch.object(client._http, 'get', new_callable=AsyncMock) as mock_get:
            # 402 response with header but empty body
            mock_402 = MagicMock()
            mock_402.status_code = 402
            mock_402.headers = {"payment-required": encoded_header}
            mock_402.content = b"{}"  # empty/invalid body — header should be used

            # Paid response
            mock_paid = MagicMock()
            mock_paid.status_code = 200
            mock_paid.headers = {"content-type": "application/json"}
            mock_paid.json.return_value = {"result": "ok"}

            mock_get.side_effect = [mock_402, mock_paid]
            result = await client.pay("http://example.com/paid")
            assert result.status == 200
            assert result.amount == 10000
        await client.close()

    @pytest.mark.asyncio
    async def test_client_pay_falls_back_to_v1_body(self):
        """Client falls back to v1 body when PAYMENT-REQUIRED header is absent."""
        from circlekit.client import GatewayClient

        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )

        body_data = json.dumps({
            "x402Version": 1,
            "resource": {"url": "/api/test"},
            "accepts": [{
                "scheme": "exact",
                "network": "eip155:5042002",
                "asset": "0x3600000000000000000000000000000000000000",
                "amount": "20000",
                "payTo": "0x1234567890123456789012345678901234567890",
                "maxTimeoutSeconds": 345600,
                "extra": {
                    "name": "GatewayWalletBatched",
                    "version": "1",
                    "verifyingContract": "0x0077777d7EBA4688BDeF3E311b846F25870A19B9",
                }
            }]
        }).encode()

        with patch.object(client._http, 'get', new_callable=AsyncMock) as mock_get:
            # 402 response with no header, valid v1 body
            mock_402 = MagicMock()
            mock_402.status_code = 402
            mock_402.headers = {}
            mock_402.content = body_data

            # Paid response
            mock_paid = MagicMock()
            mock_paid.status_code = 200
            mock_paid.headers = {"content-type": "application/json"}
            mock_paid.json.return_value = {"result": "ok"}

            mock_get.side_effect = [mock_402, mock_paid]
            result = await client.pay("http://example.com/paid")
            assert result.status == 200
            assert result.amount == 20000
        await client.close()

    @pytest.mark.asyncio
    async def test_client_pay_rejects_v2_body_without_header(self):
        """Client rejects v2 body when PAYMENT-REQUIRED header is absent."""
        from circlekit.client import GatewayClient

        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )

        body_data = json.dumps({
            "x402Version": 2,
            "resource": {"url": "/api/test"},
            "accepts": [{
                "scheme": "exact",
                "network": "eip155:5042002",
                "asset": "0x3600000000000000000000000000000000000000",
                "amount": "20000",
                "payTo": "0x1234567890123456789012345678901234567890",
                "maxTimeoutSeconds": 345600,
                "extra": {
                    "name": "GatewayWalletBatched",
                    "version": "1",
                    "verifyingContract": "0x0077777d7EBA4688BDeF3E311b846F25870A19B9",
                }
            }]
        }).encode()

        with patch.object(client._http, 'get', new_callable=AsyncMock) as mock_get:
            mock_402 = MagicMock()
            mock_402.status_code = 402
            mock_402.headers = {}
            mock_402.content = body_data
            mock_get.return_value = mock_402

            with pytest.raises(ValueError, match="Invalid payment required response"):
                await client.pay("http://example.com/paid")
        await client.close()

    @pytest.mark.asyncio
    async def test_malformed_payment_response_header_falls_back_to_body(self):
        """Malformed PAYMENT-RESPONSE header should not crash a successful payment."""
        from circlekit.client import GatewayClient
        from circlekit.x402 import encode_payment_required

        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )

        header_data = {
            "x402Version": 2,
            "resource": {"url": "/api/test"},
            "accepts": [{
                "scheme": "exact",
                "network": "eip155:5042002",
                "asset": "0x3600000000000000000000000000000000000000",
                "amount": "10000",
                "payTo": "0x1234567890123456789012345678901234567890",
                "maxTimeoutSeconds": 345600,
                "extra": {
                    "name": "GatewayWalletBatched",
                    "version": "1",
                    "verifyingContract": "0x0077777d7EBA4688BDeF3E311b846F25870A19B9",
                }
            }]
        }
        encoded_header = encode_payment_required(header_data)

        with patch.object(client._http, 'get', new_callable=AsyncMock) as mock_get:
            mock_402 = MagicMock()
            mock_402.status_code = 402
            mock_402.headers = {"payment-required": encoded_header}
            mock_402.content = b"{}"

            # Paid response with malformed PAYMENT-RESPONSE header but valid body
            mock_paid = MagicMock()
            mock_paid.status_code = 200
            mock_paid.headers = {
                "content-type": "application/json",
                "payment-response": "not-valid-base64!!!",
            }
            mock_paid.json.return_value = {
                "result": "ok",
                "payment": {"transaction": "0xbody_tx"},
            }

            mock_get.side_effect = [mock_402, mock_paid]
            result = await client.pay("http://example.com/paid")
            assert result.status == 200
            assert result.transaction == "0xbody_tx"
        await client.close()

    @pytest.mark.asyncio
    async def test_success_includes_payment_response_header(self):
        """After valid payment, PaymentInfo includes PAYMENT-RESPONSE header."""
        from circlekit.server import create_gateway_middleware
        from circlekit.x402 import (
            create_payment_header, PaymentRequirements, decode_payment_response,
            PAYMENT_RESPONSE_HEADER,
        )
        from circlekit.signer import PrivateKeySigner
        from circlekit.facilitator import VerifyResponse, SettleResponse

        middleware = create_gateway_middleware(
            seller_address="0x1234567890123456789012345678901234567890",
            chain="arcTestnet",
        )

        signer = PrivateKeySigner(
            "0x0000000000000000000000000000000000000000000000000000000000000001"
        )
        requirements = PaymentRequirements(
            scheme="exact",
            network="eip155:5042002",
            asset="0x3600000000000000000000000000000000000000",
            amount="10000",
            pay_to="0x1234567890123456789012345678901234567890",
            extra={
                "name": "GatewayWalletBatched",
                "version": "1",
                "verifyingContract": "0x0077777d7EBA4688BDeF3E311b846F25870A19B9",
            },
        )
        resource = {"url": "/api/test", "description": "test"}
        header = create_payment_header(signer, requirements, resource=resource)

        with patch.object(middleware._facilitator, 'verify', new_callable=AsyncMock) as mock_verify, \
             patch.object(middleware._facilitator, 'settle', new_callable=AsyncMock) as mock_settle:
            mock_verify.return_value = VerifyResponse(is_valid=True)
            mock_settle.return_value = SettleResponse(success=True, transaction="0xtx456")

            result = await middleware.process_request(
                payment_header=header,
                path="/api/test",
                price="$0.01",
            )

        from circlekit.x402 import PaymentInfo
        assert isinstance(result, PaymentInfo)
        assert PAYMENT_RESPONSE_HEADER in result.response_headers
        receipt = decode_payment_response(result.response_headers[PAYMENT_RESPONSE_HEADER])
        assert receipt["success"] is True
        assert receipt["transaction"] == "0xtx456"
        assert receipt["payer"] == signer.address
        assert receipt["network"] == "eip155:5042002"


# ============================================================================
# TEST: client.py
# ============================================================================

class TestGatewayClient:
    """Test GatewayClient class."""

    def test_client_with_private_key(self):
        from circlekit.client import GatewayClient
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        assert client.address == "0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf"
        assert client.chain_name == "Arc Testnet"
        assert client.chain_id == 5042002
        assert client.domain == 26

    def test_client_with_signer(self):
        from circlekit.client import GatewayClient
        from circlekit.signer import PrivateKeySigner
        signer = PrivateKeySigner("0x0000000000000000000000000000000000000000000000000000000000000001")
        client = GatewayClient(chain="arcTestnet", signer=signer)
        assert client.address == "0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf"

    def test_client_requires_signer_or_key(self):
        from circlekit.client import GatewayClient
        with pytest.raises(ValueError, match="Either signer or private_key"):
            GatewayClient(chain="arcTestnet")

    def test_client_invalid_chain(self):
        from circlekit.client import GatewayClient
        with pytest.raises(ValueError, match="Unsupported chain"):
            GatewayClient(
                chain="invalidChain",
                private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
            )

    @pytest.mark.asyncio
    async def test_supports_returns_false_for_free_resource(self):
        """supports() must return False for non-402."""
        from circlekit.client import GatewayClient
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        with patch.object(client._http, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response
            result = await client.supports("http://example.com/free")
            assert result.supported is False
            assert "not 402" in result.error
        await client.close()

    @pytest.mark.asyncio
    async def test_supports_returns_true_for_gateway_402(self):
        from circlekit.client import GatewayClient
        from circlekit.x402 import encode_payment_required
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        body = {
            "x402Version": 2,
            "accepts": [{
                "scheme": "exact",
                "network": "eip155:5042002",
                "amount": "10000",
                "payTo": "0x123",
                "extra": {"name": "GatewayWalletBatched", "version": "1",
                          "verifyingContract": "0x0077777d7EBA4688BDeF3E311b846F25870A19B9"}
            }]
        }
        with patch.object(client._http, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 402
            mock_response.headers = {"payment-required": encode_payment_required(body)}
            mock_response.content = json.dumps(body).encode()
            mock_get.return_value = mock_response
            result = await client.supports("http://example.com/paid")
            assert result.supported is True
        await client.close()


# ============================================================================
# TEST: client.py deposit/withdraw
# ============================================================================

class TestGatewayClientDepositWithdraw:
    """Test deposit and withdraw methods."""

    @pytest.mark.asyncio
    async def test_deposit_checks_allowance(self):
        from circlekit.client import GatewayClient
        from circlekit.tx_executor import TxExecutor
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        with patch.object(client._http, 'post', new_callable=AsyncMock) as mock_post, \
             patch.object(client._tx_executor, 'check_allowance', return_value=0) as mock_check, \
             patch.object(client._tx_executor, 'execute_approve', return_value="0xapproval") as mock_approve, \
             patch.object(client._tx_executor, 'execute_deposit', return_value="0xdeposit") as mock_deposit:
            # Mock get_usdc_balance RPC call (10 USDC)
            mock_rpc = MagicMock()
            mock_rpc.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": "0x989680"}
            mock_post.return_value = mock_rpc
            result = await client.deposit("1.0")
            mock_check.assert_called_once()
            mock_approve.assert_called_once()
            mock_deposit.assert_called_once()
            assert result.approval_tx_hash == "0xapproval"
            assert result.deposit_tx_hash == "0xdeposit"
            assert result.amount == 1000000
        await client.close()

    @pytest.mark.asyncio
    async def test_deposit_skips_approval_if_sufficient(self):
        from circlekit.client import GatewayClient
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        with patch.object(client._http, 'post', new_callable=AsyncMock) as mock_post, \
             patch.object(client._tx_executor, 'check_allowance', return_value=10000000), \
             patch.object(client._tx_executor, 'execute_approve') as mock_approve, \
             patch.object(client._tx_executor, 'execute_deposit', return_value="0xdeposit"):
            # Mock get_usdc_balance RPC call (10 USDC)
            mock_rpc = MagicMock()
            mock_rpc.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": "0x989680"}
            mock_post.return_value = mock_rpc
            result = await client.deposit("1.0")
            mock_approve.assert_not_called()
            assert result.approval_tx_hash is None
        await client.close()

    @pytest.mark.asyncio
    async def test_withdraw_calls_transfer_api(self):
        """withdraw() should POST to /v1/transfer and call gatewayMint."""
        from circlekit.client import GatewayClient
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        with patch.object(client._http, 'post', new_callable=AsyncMock) as mock_post, \
             patch.object(client._tx_executor, 'execute_gateway_mint', return_value="0xmint_tx") as mock_mint:
            # First call: get_gateway_balance preflight
            mock_balance_response = MagicMock()
            mock_balance_response.status_code = 200
            mock_balance_response.json.return_value = {
                "balances": [{"balance": "10.0", "withdrawing": "0", "withdrawable": "0"}]
            }
            # Second call: /v1/transfer
            mock_transfer_response = MagicMock()
            mock_transfer_response.status_code = 200
            mock_transfer_response.json.return_value = [{
                "attestation": "0xaabb",
                "signature": "0xccdd",
                "transferId": "transfer-123",
            }]
            mock_post.side_effect = [mock_balance_response, mock_transfer_response]
            result = await client.withdraw("5.0")
            # Verify it called /v1/transfer (second post call)
            call_args = mock_post.call_args_list[1]
            assert "/v1/transfer" in call_args[0][0]
            # Verify gatewayMint was called on the destination chain
            mock_mint.assert_called_once()
            assert result.mint_tx_hash == "0xmint_tx"
            assert result.transfer_id == "transfer-123"
            assert result.amount == 5000000
        await client.close()

    @pytest.mark.asyncio
    async def test_withdraw_uses_burn_intent_types(self):
        """withdraw() should send burnIntent with nested TransferSpec (version=1)."""
        from circlekit.client import GatewayClient, DEFAULT_WITHDRAW_MAX_FEE
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        with patch.object(client._http, 'post', new_callable=AsyncMock) as mock_post, \
             patch.object(client._tx_executor, 'execute_gateway_mint', return_value="0xmint"):
            # First call: get_gateway_balance preflight
            mock_balance_response = MagicMock()
            mock_balance_response.status_code = 200
            mock_balance_response.json.return_value = {
                "balances": [{"balance": "10.0", "withdrawing": "0", "withdrawable": "0"}]
            }
            # Second call: /v1/transfer
            mock_transfer_response = MagicMock()
            mock_transfer_response.status_code = 200
            mock_transfer_response.json.return_value = [{"attestation": "0x01", "signature": "0x02", "transferId": "t1"}]
            mock_post.side_effect = [mock_balance_response, mock_transfer_response]
            await client.withdraw("1.0")
            # The JSON body should be a list with a burnIntent + signature
            call_kwargs = mock_post.call_args_list[1]
            body = call_kwargs[1]["json"]
            assert isinstance(body, list)
            assert "burnIntent" in body[0]
            assert "signature" in body[0]
            # BurnIntent should have nested spec (TransferSpec)
            burn_intent = body[0]["burnIntent"]
            assert "maxBlockHeight" in burn_intent
            assert "maxFee" in burn_intent
            assert burn_intent["maxFee"] == str(DEFAULT_WITHDRAW_MAX_FEE)
            assert "spec" in burn_intent
            spec = burn_intent["spec"]
            assert spec["version"] == 1
            assert "sourceDomain" in spec
            assert "destinationDomain" in spec
            assert "sourceDepositor" in spec
            assert "destinationRecipient" in spec
            assert "salt" in spec
        await client.close()

    @pytest.mark.asyncio
    async def test_deposit_raises_without_tx_executor(self):
        """deposit() raises if only signer is provided (no tx_executor)."""
        from circlekit.client import GatewayClient
        from circlekit.signer import PrivateKeySigner
        signer = PrivateKeySigner("0x0000000000000000000000000000000000000000000000000000000000000001")
        client = GatewayClient(chain="arcTestnet", signer=signer)
        with pytest.raises(ValueError, match="tx_executor or private_key"):
            await client.deposit("1.0")
        await client.close()

    @pytest.mark.asyncio
    async def test_withdraw_raises_without_tx_executor(self):
        """withdraw() raises if only signer is provided (no tx_executor)."""
        from circlekit.client import GatewayClient
        from circlekit.signer import PrivateKeySigner
        signer = PrivateKeySigner("0x0000000000000000000000000000000000000000000000000000000000000001")
        client = GatewayClient(chain="arcTestnet", signer=signer)
        with pytest.raises(ValueError, match="tx_executor or private_key"):
            await client.withdraw("1.0")
        await client.close()

    @pytest.mark.asyncio
    async def test_pay_works_without_tx_executor(self):
        """pay() works with signer-only client (no tx_executor needed)."""
        from circlekit.client import GatewayClient
        from circlekit.signer import PrivateKeySigner
        from circlekit.x402 import encode_payment_required

        signer = PrivateKeySigner("0x0000000000000000000000000000000000000000000000000000000000000001")
        client = GatewayClient(chain="arcTestnet", signer=signer)

        header_data = {
            "x402Version": 2,
            "resource": {"url": "/api/test"},
            "accepts": [{
                "scheme": "exact",
                "network": "eip155:5042002",
                "asset": "0x3600000000000000000000000000000000000000",
                "amount": "10000",
                "payTo": "0x1234567890123456789012345678901234567890",
                "maxTimeoutSeconds": 345600,
                "extra": {
                    "name": "GatewayWalletBatched",
                    "version": "1",
                    "verifyingContract": "0x0077777d7EBA4688BDeF3E311b846F25870A19B9",
                }
            }]
        }
        encoded_header = encode_payment_required(header_data)

        with patch.object(client._http, 'get', new_callable=AsyncMock) as mock_get:
            mock_402 = MagicMock()
            mock_402.status_code = 402
            mock_402.headers = {"payment-required": encoded_header}
            mock_402.content = b"{}"

            mock_paid = MagicMock()
            mock_paid.status_code = 200
            mock_paid.headers = {"content-type": "application/json"}
            mock_paid.json.return_value = {"result": "ok"}

            mock_get.side_effect = [mock_402, mock_paid]
            result = await client.pay("http://example.com/paid")
            assert result.status == 200
            assert result.amount == 10000
        await client.close()

    @pytest.mark.asyncio
    async def test_withdraw_raises_on_missing_attestation(self):
        """withdraw() raises if API response is missing attestation/signature."""
        from circlekit.client import GatewayClient
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        with patch.object(client._http, 'post', new_callable=AsyncMock) as mock_post:
            mock_balance_response = MagicMock()
            mock_balance_response.status_code = 200
            mock_balance_response.json.return_value = {
                "balances": [{"balance": "10.0", "withdrawing": "0", "withdrawable": "0"}]
            }
            mock_transfer_response = MagicMock()
            mock_transfer_response.status_code = 200
            mock_transfer_response.json.return_value = [{"transferId": "t1"}]  # no attestation/signature
            mock_post.side_effect = [mock_balance_response, mock_transfer_response]
            with pytest.raises(ValueError, match="missing attestation or signature"):
                await client.withdraw("1.0")
        await client.close()

    @pytest.mark.asyncio
    async def test_withdraw_does_not_pass_source_rpc_to_mint(self):
        """Cross-chain withdraw must not pass source-chain rpc_url to gatewayMint."""
        from circlekit.client import GatewayClient
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
            rpc_url="http://custom-source-rpc.example.com",
        )
        with patch.object(client._http, 'post', new_callable=AsyncMock) as mock_post, \
             patch.object(client._tx_executor, 'execute_gateway_mint', return_value="0xmint") as mock_mint:
            mock_balance_response = MagicMock()
            mock_balance_response.status_code = 200
            mock_balance_response.json.return_value = {
                "balances": [{"balance": "10.0", "withdrawing": "0", "withdrawable": "0"}]
            }
            mock_transfer_response = MagicMock()
            mock_transfer_response.status_code = 200
            mock_transfer_response.json.return_value = [{
                "attestation": "0xaa",
                "signature": "0xbb",
                "transferId": "t1",
            }]
            mock_post.side_effect = [mock_balance_response, mock_transfer_response]
            await client.withdraw("1.0", chain="baseSepolia")
            # rpc_url passed to gatewayMint must be None, not the source-chain override
            _, kwargs = mock_mint.call_args
            # It's passed positionally, so check args
            call_args = mock_mint.call_args[0]
            assert call_args[-1] is None, f"Expected None rpc_url for dest chain, got {call_args[-1]}"
        await client.close()

    def test_constructor_rejects_mismatched_signer_and_private_key(self):
        """Constructor raises if signer address != private_key address."""
        from circlekit.client import GatewayClient
        from circlekit.signer import PrivateKeySigner
        # Key 1 -> address 0x7E5F...
        # Key 2 -> different address
        signer = PrivateKeySigner("0x0000000000000000000000000000000000000000000000000000000000000002")
        with pytest.raises(ValueError, match="does not match"):
            GatewayClient(
                chain="arcTestnet",
                signer=signer,
                private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
            )

    def test_constructor_allows_matching_signer_and_private_key(self):
        """Constructor allows signer + private_key when addresses match."""
        from circlekit.client import GatewayClient
        from circlekit.signer import PrivateKeySigner
        key = "0x0000000000000000000000000000000000000000000000000000000000000001"
        signer = PrivateKeySigner(key)
        client = GatewayClient(chain="arcTestnet", signer=signer, private_key=key)
        assert client.address == signer.address

    def test_constructor_allows_matching_address_different_case(self):
        """Constructor allows signer/private_key when addresses differ only by case."""
        from circlekit.client import GatewayClient
        from circlekit.signer import PrivateKeySigner

        class LowercaseAddressSigner:
            def __init__(self, private_key: str):
                self._delegate = PrivateKeySigner(private_key)
                self.address = self._delegate.address.lower()

            def sign_typed_data(self, domain, types, primary_type, message):
                return self._delegate.sign_typed_data(domain, types, primary_type, message)

        key = "0x0000000000000000000000000000000000000000000000000000000000000001"
        signer = LowercaseAddressSigner(key)
        client = GatewayClient(chain="arcTestnet", signer=signer, private_key=key)
        assert client.address == signer.address


# ============================================================================
# TEST: client.py parity (F2-F7)
# ============================================================================

class TestGatewayClientParity:
    """Test parity fixes: version, maxFee, balances, trustless withdrawal, depositFor, transfer alias."""

    @pytest.mark.asyncio
    async def test_deposit_for_delegates_to_tx_executor(self):
        """deposit_for() should check allowance, approve, and call execute_deposit_for."""
        from circlekit.client import GatewayClient
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        with patch.object(client._http, 'post', new_callable=AsyncMock) as mock_post, \
             patch.object(client._tx_executor, 'check_allowance', return_value=0) as mock_check, \
             patch.object(client._tx_executor, 'execute_approve', return_value="0xapproval") as mock_approve, \
             patch.object(client._tx_executor, 'execute_deposit_for', return_value="0xdep_for") as mock_dep_for:
            # Mock get_usdc_balance RPC call (10 USDC)
            mock_rpc = MagicMock()
            mock_rpc.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": "0x989680"}
            mock_post.return_value = mock_rpc
            result = await client.deposit_for("1.0", depositor="0xDeAdBeEf00000000000000000000000000000000")
            mock_check.assert_called_once()
            mock_approve.assert_called_once()
            mock_dep_for.assert_called_once()
            # Verify the depositor was passed through
            dep_for_args = mock_dep_for.call_args[0]
            assert dep_for_args[2] == "0xDeAdBeEf00000000000000000000000000000000"
            assert result.deposit_tx_hash == "0xdep_for"
            assert result.amount == 1000000
        await client.close()

    @pytest.mark.asyncio
    async def test_transfer_is_withdraw_alias(self):
        """transfer() should delegate to withdraw() with a deprecation warning."""
        from circlekit.client import GatewayClient
        import warnings
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        with patch.object(client._http, 'post', new_callable=AsyncMock) as mock_post, \
             patch.object(client._tx_executor, 'execute_gateway_mint', return_value="0xmint"):
            mock_balance_response = MagicMock()
            mock_balance_response.status_code = 200
            mock_balance_response.json.return_value = {
                "balances": [{"balance": "10.0", "withdrawing": "0", "withdrawable": "0"}]
            }
            mock_transfer_response = MagicMock()
            mock_transfer_response.status_code = 200
            mock_transfer_response.json.return_value = [{
                "attestation": "0xaa", "signature": "0xbb", "transferId": "t1",
            }]
            mock_post.side_effect = [mock_balance_response, mock_transfer_response]
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                result = await client.transfer("1.0", destination_chain="arcTestnet")
                assert len(w) == 1
                assert issubclass(w[0].category, DeprecationWarning)
                assert "deprecated" in str(w[0].message).lower()
            assert result.amount == 1000000
        await client.close()

    @pytest.mark.asyncio
    async def test_trustless_withdrawal_delay(self):
        """get_trustless_withdrawal_delay() should call boa_utils view function."""
        from circlekit.client import GatewayClient
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        with patch("circlekit.client._boa_get_withdrawal_delay", return_value=100) as mock_delay:
            result = await client.get_trustless_withdrawal_delay()
            assert result == 100
            mock_delay.assert_called_once_with("arcTestnet", None)
        await client.close()

    @pytest.mark.asyncio
    async def test_initiate_trustless_withdrawal(self):
        """initiate_trustless_withdrawal() should call tx_executor and read withdrawal block."""
        from circlekit.client import GatewayClient
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        with patch.object(client._http, 'post', new_callable=AsyncMock) as mock_post, \
             patch.object(client._tx_executor, 'execute_initiate_withdrawal', return_value="0xinit_tx") as mock_init, \
             patch("circlekit.client._boa_get_withdrawal_block", return_value=12345) as mock_block:
            mock_balance_response = MagicMock()
            mock_balance_response.status_code = 200
            mock_balance_response.json.return_value = {
                "balances": [{"balance": "10.0", "withdrawing": "0", "withdrawable": "0"}]
            }
            mock_post.return_value = mock_balance_response
            result = await client.initiate_trustless_withdrawal("5.0")
            mock_init.assert_called_once()
            assert result.tx_hash == "0xinit_tx"
            assert result.amount == 5000000
            assert result.withdrawal_block == 12345
        await client.close()

    @pytest.mark.asyncio
    async def test_complete_trustless_withdrawal(self):
        """complete_trustless_withdrawal() should check withdrawable > 0 and call tx_executor."""
        from circlekit.client import GatewayClient
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        with patch.object(client._http, 'post', new_callable=AsyncMock) as mock_post, \
             patch.object(client._tx_executor, 'execute_complete_withdrawal', return_value="0xcomplete_tx") as mock_complete:
            mock_balance_response = MagicMock()
            mock_balance_response.status_code = 200
            mock_balance_response.json.return_value = {
                "balances": [{"balance": "5.0", "withdrawing": "0", "withdrawable": "3.0"}]
            }
            mock_post.return_value = mock_balance_response
            result = await client.complete_trustless_withdrawal()
            mock_complete.assert_called_once()
            assert result.tx_hash == "0xcomplete_tx"
            assert result.amount == 3000000
        await client.close()

    @pytest.mark.asyncio
    async def test_complete_trustless_withdrawal_rejects_zero_withdrawable(self):
        """complete_trustless_withdrawal() raises if withdrawable is 0."""
        from circlekit.client import GatewayClient
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        with patch.object(client._http, 'post', new_callable=AsyncMock) as mock_post:
            mock_balance_response = MagicMock()
            mock_balance_response.status_code = 200
            mock_balance_response.json.return_value = {
                "balances": [{"balance": "5.0", "withdrawing": "0", "withdrawable": "0"}]
            }
            mock_post.return_value = mock_balance_response
            with pytest.raises(ValueError, match="No withdrawable balance"):
                await client.complete_trustless_withdrawal()
        await client.close()

    @pytest.mark.asyncio
    async def test_get_gateway_balance_passes_domain(self):
        """get_gateway_balance() should include domain in the API request."""
        from circlekit.client import GatewayClient
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        with patch.object(client._http, 'post', new_callable=AsyncMock) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "balances": [{"balance": "5.0", "withdrawing": "1.0", "withdrawable": "0.5"}]
            }
            mock_post.return_value = mock_response
            await client.get_gateway_balance()
            # Check the request body included domain
            call_kwargs = mock_post.call_args[1]
            request_body = call_kwargs["json"]
            assert request_body["sources"][0]["domain"] == 26  # arcTestnet domain
        await client.close()

    @pytest.mark.asyncio
    async def test_get_gateway_balance_parses_withdrawing_withdrawable(self):
        """get_gateway_balance() should parse withdrawing and withdrawable from API."""
        from circlekit.client import GatewayClient
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        with patch.object(client._http, 'post', new_callable=AsyncMock) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "balances": [{"balance": "5.0", "withdrawing": "1.0", "withdrawable": "0.5"}]
            }
            mock_post.return_value = mock_response
            result = await client.get_gateway_balance()
            assert result.available == 5000000
            assert result.withdrawing == 1000000
            assert result.withdrawable == 500000
            # total = available + withdrawing
            assert result.total == 6000000
        await client.close()

    @pytest.mark.asyncio
    async def test_get_usdc_balance_standalone(self):
        """get_usdc_balance() should query on-chain USDC balance via RPC."""
        from circlekit.client import GatewayClient
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        with patch.object(client._http, 'post', new_callable=AsyncMock) as mock_post:
            mock_response = MagicMock()
            # 10 USDC = 10_000_000 = 0x989680
            mock_response.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": "0x989680"}
            mock_post.return_value = mock_response
            result = await client.get_usdc_balance()
            assert result.balance == 10000000
            assert result.formatted == "10.000000"
        await client.close()

    @pytest.mark.asyncio
    async def test_withdraw_preflight_rejects_insufficient_balance(self):
        """withdraw() should raise if gateway available balance < amount."""
        from circlekit.client import GatewayClient
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        with patch.object(client._http, 'post', new_callable=AsyncMock) as mock_post:
            mock_balance_response = MagicMock()
            mock_balance_response.status_code = 200
            mock_balance_response.json.return_value = {
                "balances": [{"balance": "1.0", "withdrawing": "0", "withdrawable": "0"}]
            }
            mock_post.return_value = mock_balance_response
            with pytest.raises(ValueError, match="Insufficient available balance"):
                await client.withdraw("5.0")
        await client.close()

    @pytest.mark.asyncio
    async def test_withdraw_preflight_allows_sufficient_balance(self):
        """withdraw() should proceed when gateway available balance >= amount."""
        from circlekit.client import GatewayClient
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        with patch.object(client._http, 'post', new_callable=AsyncMock) as mock_post, \
             patch.object(client._tx_executor, 'execute_gateway_mint', return_value="0xmint"):
            mock_balance_response = MagicMock()
            mock_balance_response.status_code = 200
            mock_balance_response.json.return_value = {
                "balances": [{"balance": "5.0", "withdrawing": "0", "withdrawable": "0"}]
            }
            mock_transfer_response = MagicMock()
            mock_transfer_response.status_code = 200
            mock_transfer_response.json.return_value = [{
                "attestation": "0xaa", "signature": "0xbb", "transferId": "t1",
            }]
            mock_post.side_effect = [mock_balance_response, mock_transfer_response]
            result = await client.withdraw("5.0")  # exactly matching balance
            assert result.amount == 5000000
        await client.close()

    @pytest.mark.asyncio
    async def test_get_gateway_balance_raises_on_error(self):
        """get_gateway_balance() should raise ValueError on non-200 response."""
        from circlekit.client import GatewayClient
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        with patch.object(client._http, 'post', new_callable=AsyncMock) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_post.return_value = mock_response
            with pytest.raises(ValueError, match="Gateway balance query failed"):
                await client.get_gateway_balance()
        await client.close()

    @pytest.mark.asyncio
    async def test_withdraw_max_fee_default(self):
        """withdraw() should use DEFAULT_WITHDRAW_MAX_FEE when max_fee is not specified."""
        from circlekit.client import GatewayClient, DEFAULT_WITHDRAW_MAX_FEE
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        assert DEFAULT_WITHDRAW_MAX_FEE == 2_010_000
        with patch.object(client._http, 'post', new_callable=AsyncMock) as mock_post, \
             patch.object(client._tx_executor, 'execute_gateway_mint', return_value="0xmint"):
            mock_balance_response = MagicMock()
            mock_balance_response.status_code = 200
            mock_balance_response.json.return_value = {
                "balances": [{"balance": "10.0", "withdrawing": "0", "withdrawable": "0"}]
            }
            mock_transfer_response = MagicMock()
            mock_transfer_response.status_code = 200
            mock_transfer_response.json.return_value = [{"attestation": "0x01", "signature": "0x02", "transferId": "t1"}]
            mock_post.side_effect = [mock_balance_response, mock_transfer_response]
            await client.withdraw("1.0")
            # Check maxFee in the API call
            transfer_call = mock_post.call_args_list[1]
            body = transfer_call[1]["json"]
            assert body[0]["burnIntent"]["maxFee"] == str(DEFAULT_WITHDRAW_MAX_FEE)
        await client.close()

    @pytest.mark.asyncio
    async def test_withdraw_max_fee_explicit_zero(self):
        """withdraw(max_fee=0) should override the default and use 0."""
        from circlekit.client import GatewayClient
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        with patch.object(client._http, 'post', new_callable=AsyncMock) as mock_post, \
             patch.object(client._tx_executor, 'execute_gateway_mint', return_value="0xmint"):
            mock_balance_response = MagicMock()
            mock_balance_response.status_code = 200
            mock_balance_response.json.return_value = {
                "balances": [{"balance": "10.0", "withdrawing": "0", "withdrawable": "0"}]
            }
            mock_transfer_response = MagicMock()
            mock_transfer_response.status_code = 200
            mock_transfer_response.json.return_value = [{"attestation": "0x01", "signature": "0x02", "transferId": "t1"}]
            mock_post.side_effect = [mock_balance_response, mock_transfer_response]
            await client.withdraw("1.0", max_fee=0)
            transfer_call = mock_post.call_args_list[1]
            body = transfer_call[1]["json"]
            assert body[0]["burnIntent"]["maxFee"] == "0"
        await client.close()

    @pytest.mark.asyncio
    async def test_deposit_preflight_rejects_insufficient_usdc(self):
        """deposit() should raise if wallet USDC balance < amount."""
        from circlekit.client import GatewayClient
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        with patch.object(client._http, 'post', new_callable=AsyncMock) as mock_post:
            # Mock get_usdc_balance RPC call (0.5 USDC = 500000 = 0x7A120)
            mock_rpc = MagicMock()
            mock_rpc.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": "0x7A120"}
            mock_post.return_value = mock_rpc
            with pytest.raises(ValueError, match="Insufficient USDC balance"):
                await client.deposit("1.0")
        await client.close()

    @pytest.mark.asyncio
    async def test_deposit_for_preflight_rejects_insufficient_usdc(self):
        """deposit_for() should raise if wallet USDC balance < amount."""
        from circlekit.client import GatewayClient
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        with patch.object(client._http, 'post', new_callable=AsyncMock) as mock_post:
            # Mock get_usdc_balance RPC call (0.5 USDC)
            mock_rpc = MagicMock()
            mock_rpc.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": "0x7A120"}
            mock_post.return_value = mock_rpc
            with pytest.raises(ValueError, match="Insufficient USDC balance"):
                await client.deposit_for("1.0", depositor="0xDeAdBeEf00000000000000000000000000000000")
        await client.close()

    @pytest.mark.asyncio
    async def test_deposit_skip_approval_check(self):
        """deposit(skip_approval_check=True) should skip approval entirely."""
        from circlekit.client import GatewayClient
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        with patch.object(client._http, 'post', new_callable=AsyncMock) as mock_post, \
             patch.object(client._tx_executor, 'check_allowance') as mock_check, \
             patch.object(client._tx_executor, 'execute_approve') as mock_approve, \
             patch.object(client._tx_executor, 'execute_deposit', return_value="0xdeposit"):
            # Mock get_usdc_balance RPC call (10 USDC)
            mock_rpc = MagicMock()
            mock_rpc.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": "0x989680"}
            mock_post.return_value = mock_rpc
            result = await client.deposit("1.0", skip_approval_check=True)
            mock_check.assert_not_called()
            mock_approve.assert_not_called()
            assert result.approval_tx_hash is None
        await client.close()

    @pytest.mark.asyncio
    async def test_deposit_for_skip_approval_check(self):
        """deposit_for(skip_approval_check=True) should skip approval entirely."""
        from circlekit.client import GatewayClient
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        with patch.object(client._http, 'post', new_callable=AsyncMock) as mock_post, \
             patch.object(client._tx_executor, 'check_allowance') as mock_check, \
             patch.object(client._tx_executor, 'execute_approve') as mock_approve, \
             patch.object(client._tx_executor, 'execute_deposit_for', return_value="0xdep_for"):
            mock_rpc = MagicMock()
            mock_rpc.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": "0x989680"}
            mock_post.return_value = mock_rpc
            result = await client.deposit_for(
                "1.0", depositor="0xDeAdBeEf00000000000000000000000000000000",
                skip_approval_check=True,
            )
            mock_check.assert_not_called()
            mock_approve.assert_not_called()
            assert result.approval_tx_hash is None
        await client.close()

    @pytest.mark.asyncio
    async def test_pay_raises_on_non_402_error(self):
        """pay() should raise httpx.HTTPStatusError on non-402 4xx/5xx responses."""
        import httpx
        from circlekit.client import GatewayClient
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        with patch.object(client._http, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.request = MagicMock()
            mock_get.return_value = mock_response
            with pytest.raises(httpx.HTTPStatusError, match="status 500"):
                await client.pay("http://example.com/broken")
        await client.close()

    @pytest.mark.asyncio
    async def test_pay_raises_on_403(self):
        """pay() should raise on 403 Forbidden (non-402 client error)."""
        import httpx
        from circlekit.client import GatewayClient
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        with patch.object(client._http, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 403
            mock_response.request = MagicMock()
            mock_get.return_value = mock_response
            with pytest.raises(httpx.HTTPStatusError):
                await client.pay("http://example.com/forbidden")
        await client.close()

    @pytest.mark.asyncio
    async def test_pay_raises_on_failed_paid_response(self):
        """pay() should raise when the paid (second) response is not OK."""
        import httpx
        from circlekit.client import GatewayClient
        from circlekit.x402 import encode_payment_required
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        header_data = {
            "x402Version": 2,
            "resource": {"url": "/api/test"},
            "accepts": [{
                "scheme": "exact",
                "network": "eip155:5042002",
                "asset": "0x3600000000000000000000000000000000000000",
                "amount": "10000",
                "payTo": "0x1234567890123456789012345678901234567890",
                "maxTimeoutSeconds": 345600,
                "extra": {
                    "name": "GatewayWalletBatched",
                    "version": "1",
                    "verifyingContract": "0x0077777d7EBA4688BDeF3E311b846F25870A19B9",
                }
            }]
        }
        encoded_header = encode_payment_required(header_data)
        with patch.object(client._http, 'get', new_callable=AsyncMock) as mock_get:
            mock_402 = MagicMock()
            mock_402.status_code = 402
            mock_402.headers = {"payment-required": encoded_header}
            mock_402.content = b"{}"
            # Paid response returns 500
            mock_paid = MagicMock()
            mock_paid.status_code = 500
            mock_paid.request = MagicMock()
            mock_get.side_effect = [mock_402, mock_paid]
            with pytest.raises(httpx.HTTPStatusError, match="Payment failed"):
                await client.pay("http://example.com/paid")
        await client.close()

    @pytest.mark.asyncio
    async def test_pay_returns_result_on_2xx(self):
        """pay() should return PayResult for successful 2xx responses."""
        from circlekit.client import GatewayClient
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        with patch.object(client._http, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "application/json"}
            mock_response.json.return_value = {"free": True}
            mock_get.return_value = mock_response
            result = await client.pay("http://example.com/free")
            assert result.status == 200
            assert result.amount == 0
        await client.close()

    @pytest.mark.asyncio
    async def test_get_balance_is_alias_for_get_gateway_balance(self):
        """get_balance() should return the same result as get_gateway_balance()."""
        from circlekit.client import GatewayClient
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        with patch.object(client._http, 'post', new_callable=AsyncMock) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "balances": [{"balance": "5.0", "withdrawing": "1.0", "withdrawable": "0.5"}]
            }
            mock_post.return_value = mock_response
            result = await client.get_balance()
            assert result.available == 5000000
            assert result.withdrawing == 1000000
            assert result.withdrawable == 500000
        await client.close()

    @pytest.mark.asyncio
    async def test_withdraw_rejects_api_success_false(self):
        """withdraw() should raise when API returns success=false."""
        from circlekit.client import GatewayClient
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        with patch.object(client._http, 'post', new_callable=AsyncMock) as mock_post:
            mock_balance_response = MagicMock()
            mock_balance_response.status_code = 200
            mock_balance_response.json.return_value = {
                "balances": [{"balance": "10.0", "withdrawing": "0", "withdrawable": "0"}]
            }
            mock_transfer_response = MagicMock()
            mock_transfer_response.status_code = 200
            mock_transfer_response.json.return_value = [{
                "success": False,
                "error": "Rate limit exceeded",
            }]
            mock_post.side_effect = [mock_balance_response, mock_transfer_response]
            with pytest.raises(ValueError, match="Rate limit exceeded"):
                await client.withdraw("1.0")
        await client.close()

    @pytest.mark.asyncio
    async def test_withdraw_rejects_api_error_field(self):
        """withdraw() should raise when API returns an error field."""
        from circlekit.client import GatewayClient
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        with patch.object(client._http, 'post', new_callable=AsyncMock) as mock_post:
            mock_balance_response = MagicMock()
            mock_balance_response.status_code = 200
            mock_balance_response.json.return_value = {
                "balances": [{"balance": "10.0", "withdrawing": "0", "withdrawable": "0"}]
            }
            mock_transfer_response = MagicMock()
            mock_transfer_response.status_code = 200
            mock_transfer_response.json.return_value = [{
                "error": "Insufficient funds for fee",
            }]
            mock_post.side_effect = [mock_balance_response, mock_transfer_response]
            with pytest.raises(ValueError, match="Insufficient funds for fee"):
                await client.withdraw("1.0")
        await client.close()


# ============================================================================
# TEST: server.py
# ============================================================================

class TestGatewayMiddleware:
    """Test server middleware."""

    def test_create_gateway_middleware(self):
        from circlekit.server import create_gateway_middleware
        middleware = create_gateway_middleware(
            seller_address="0x1234567890123456789012345678901234567890",
            chain="arcTestnet",
        )
        assert middleware._config.seller_address == "0x1234567890123456789012345678901234567890"
        assert middleware._chain_config.chain_id == 5042002

    @pytest.mark.asyncio
    async def test_process_request_returns_402_without_header(self):
        from circlekit.server import create_gateway_middleware
        from circlekit.x402 import decode_payment_required, PAYMENT_REQUIRED_HEADER
        middleware = create_gateway_middleware(
            seller_address="0x1234567890123456789012345678901234567890",
        )
        result = await middleware.process_request(
            payment_header=None,
            path="/api/test",
            price="$0.01",
        )
        assert isinstance(result, dict)
        assert result["status"] == 402
        assert "accepts" in result["body"]
        # Verify PAYMENT-REQUIRED header
        assert "headers" in result
        assert PAYMENT_REQUIRED_HEADER in result["headers"]
        decoded = decode_payment_required(result["headers"][PAYMENT_REQUIRED_HEADER])
        assert decoded.x402_version == result["body"]["x402Version"]
        assert len(decoded.accepts) == len(result["body"]["accepts"])

    def test_networks_option_filters_accepted_chains(self):
        """When networks is specified, only those chains appear in accepted_chains."""
        from circlekit.server import create_gateway_middleware
        middleware = create_gateway_middleware(
            seller_address="0x1234567890123456789012345678901234567890",
            chain="arcTestnet",
            networks=["arcTestnet", "baseSepolia"],
        )
        assert "eip155:5042002" in middleware._accepted_chains
        assert "eip155:84532" in middleware._accepted_chains
        assert len(middleware._accepted_chains) == 2

    def test_networks_empty_defaults_to_primary_chain(self):
        """When networks is empty, accepted_chains defaults to primary chain."""
        from circlekit.server import create_gateway_middleware
        middleware = create_gateway_middleware(
            seller_address="0x1234567890123456789012345678901234567890",
            chain="baseSepolia",
        )
        assert "eip155:84532" in middleware._accepted_chains
        assert len(middleware._accepted_chains) == 1

    def test_networks_invalid_raises(self):
        """Unknown network name raises ValueError."""
        from circlekit.server import create_gateway_middleware
        with pytest.raises(ValueError, match="Unknown network"):
            create_gateway_middleware(
                seller_address="0x1234567890123456789012345678901234567890",
                networks=["nonexistentChain"],
            )

    @pytest.mark.asyncio
    async def test_402_response_has_multiple_accepts_for_networks(self):
        """402 response should have one accepts entry per accepted network."""
        from circlekit.server import create_gateway_middleware
        from circlekit.x402 import decode_payment_required, PAYMENT_REQUIRED_HEADER
        middleware = create_gateway_middleware(
            seller_address="0x1234567890123456789012345678901234567890",
            chain="arcTestnet",
            networks=["arcTestnet", "baseSepolia"],
        )
        result = await middleware.process_request(
            payment_header=None,
            path="/api/test",
            price="$0.01",
        )
        assert result["status"] == 402
        accepts = result["body"]["accepts"]
        assert len(accepts) == 2
        networks = {a["network"] for a in accepts}
        assert "eip155:5042002" in networks
        assert "eip155:84532" in networks
        # Verify PAYMENT-REQUIRED header matches body
        assert PAYMENT_REQUIRED_HEADER in result["headers"]
        decoded = decode_payment_required(result["headers"][PAYMENT_REQUIRED_HEADER])
        assert len(decoded.accepts) == 2

    @pytest.mark.asyncio
    async def test_payment_with_wrong_network_rejected(self):
        """Payment on a network not in accepted set should be rejected."""
        from circlekit.server import create_gateway_middleware
        import base64, json

        middleware = create_gateway_middleware(
            seller_address="0x1234567890123456789012345678901234567890",
            chain="arcTestnet",
            networks=["arcTestnet"],  # only Arc
        )

        # Fake a payment header claiming baseSepolia
        fake_header = base64.b64encode(json.dumps({
            "payload": {"authorization": {"from": "0xabc", "value": "10000"}, "signature": "0x123"},
            "accepted": {"network": "eip155:84532"},  # Base Sepolia - not accepted
        }).encode()).decode()

        result = await middleware.process_request(
            payment_header=fake_header,
            path="/api/test",
            price="$0.01",
        )
        assert isinstance(result, dict)
        assert result["status"] == 402
        assert "not accepted" in result["body"]["error"]

    @pytest.mark.asyncio
    async def test_malformed_header_list_returns_402(self):
        """Header that decodes to a JSON list (not object) must return 402, not 500."""
        from circlekit.server import create_gateway_middleware
        import base64, json

        middleware = create_gateway_middleware(
            seller_address="0x1234567890123456789012345678901234567890",
        )

        # Encode a list instead of an object
        bad_header = base64.b64encode(json.dumps(["not", "a", "dict"]).encode()).decode()
        result = await middleware.process_request(
            payment_header=bad_header,
            path="/api/test",
            price="$0.01",
        )
        assert isinstance(result, dict)
        assert result["status"] == 402
        assert "error" in result["body"]

    @pytest.mark.asyncio
    async def test_malformed_header_bad_accepted_returns_402(self):
        """Header with non-dict 'accepted' field must return 402, not 500."""
        from circlekit.server import create_gateway_middleware
        import base64, json

        middleware = create_gateway_middleware(
            seller_address="0x1234567890123456789012345678901234567890",
        )

        bad_header = base64.b64encode(json.dumps({
            "payload": {"authorization": {}, "signature": "0x"},
            "accepted": "not-a-dict",
        }).encode()).decode()
        result = await middleware.process_request(
            payment_header=bad_header,
            path="/api/test",
            price="$0.01",
        )
        assert isinstance(result, dict)
        assert result["status"] == 402
        assert "accepted" in result["body"]["error"].lower()

    @pytest.mark.asyncio
    async def test_process_request_blocks_on_settle_failure(self):
        """Must block access when settlement fails (not silently swallow)."""
        from circlekit.server import create_gateway_middleware
        from circlekit.facilitator import VerifyResponse
        import base64, json

        middleware = create_gateway_middleware(
            seller_address="0x1234567890123456789012345678901234567890",
        )

        fake_header = base64.b64encode(json.dumps({
            "payload": {"authorization": {"from": "0xabc", "value": "10000"}, "signature": "0x123"},
            "accepted": {},
        }).encode()).decode()

        with patch.object(middleware._facilitator, 'verify', new_callable=AsyncMock) as mock_verify, \
             patch.object(middleware._facilitator, 'settle', new_callable=AsyncMock) as mock_settle:
            mock_verify.return_value = VerifyResponse(is_valid=True)
            mock_settle.side_effect = ValueError("Settlement failed")

            result = await middleware.process_request(
                payment_header=fake_header,
                path="/api/test",
                price="$0.01",
            )
            # Must return error, not PaymentInfo
            assert isinstance(result, dict)
            assert result["status"] == 402
            assert "settlement" in result["body"]["error"].lower()


# ============================================================================
# TEST: boa_utils.py transaction helpers
# ============================================================================

class TestBoaTransactionHelpers:
    """Test transaction execution helpers."""

    def test_parse_usdc(self):
        from circlekit.boa_utils import parse_usdc
        assert parse_usdc("1.0") == 1000000
        assert parse_usdc("0.01") == 10000
        assert parse_usdc("$5.50") == 5500000
        assert parse_usdc("100") == 100000000

    def test_format_usdc(self):
        from circlekit.boa_utils import format_usdc
        assert format_usdc(1000000) == "1.000000"
        assert format_usdc(10000) == "0.010000"

    def test_minter_abi_exists(self):
        """GATEWAY_MINTER_ABI should exist with gatewayMint function."""
        from circlekit.boa_utils import GATEWAY_MINTER_ABI
        assert isinstance(GATEWAY_MINTER_ABI, list)
        assert any(f["name"] == "gatewayMint" for f in GATEWAY_MINTER_ABI)

    def test_gateway_wallet_abi_expanded(self):
        """GATEWAY_WALLET_ABI should have totalBalance, availableBalance, etc."""
        from circlekit.boa_utils import GATEWAY_WALLET_ABI
        names = {f["name"] for f in GATEWAY_WALLET_ABI}
        assert "totalBalance" in names
        assert "availableBalance" in names
        assert "withdrawingBalance" in names
        assert "withdrawableBalance" in names
        assert "withdrawalDelay" in names
        assert "withdrawalBlock" in names
        assert "initiateWithdrawal" in names
        # balanceOf should NOT be in Gateway ABI
        assert "balanceOf" not in names

    def test_boa_tx_executor_satisfies_protocol(self):
        """BoaTxExecutor must satisfy the TxExecutor protocol."""
        from circlekit.tx_executor import TxExecutor, BoaTxExecutor
        executor = BoaTxExecutor("0x0000000000000000000000000000000000000000000000000000000000000001")
        assert isinstance(executor, TxExecutor)

    def test_gateway_withdraw_abi_one_arg(self):
        """Gateway withdraw() takes 1 arg (token), not 2 (token, amount)."""
        from circlekit.boa_utils import GATEWAY_WALLET_ABI
        withdraw_entry = next(f for f in GATEWAY_WALLET_ABI if f["name"] == "withdraw")
        assert len(withdraw_entry["inputs"]) == 1
        assert withdraw_entry["inputs"][0]["name"] == "token"


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
