"""
Battle Tests for circlekit-py

Edge cases, error handling, security, concurrency, and boundary conditions.
Run with: python -m pytest tests/test_battle.py -v
"""

import base64
import json
from unittest.mock import AsyncMock, patch

import pytest


class TestInputValidation:
    """Test that invalid inputs are handled gracefully."""

    def test_parse_402_empty_accepts(self):
        from circlekit.x402 import parse_402_response

        result = parse_402_response({"x402Version": 2, "accepts": []})
        assert result.x402_version == 2
        assert result.accepts == []

    def test_parse_402_missing_fields(self):
        from circlekit.x402 import parse_402_response

        with pytest.raises(ValueError):
            parse_402_response({"accepts": [{"scheme": "exact"}]})
        with pytest.raises(ValueError):
            parse_402_response({"x402Version": 2})

    def test_parse_402_invalid_json(self):
        from circlekit.x402 import parse_402_response

        with pytest.raises((ValueError, json.JSONDecodeError)):
            parse_402_response("{invalid json")

    def test_parse_402_non_dict_input(self):
        from circlekit.x402 import parse_402_response

        with pytest.raises((ValueError, TypeError, AttributeError)):
            parse_402_response([1, 2, 3])

    def test_parse_usdc_basic(self):
        from circlekit.boa_utils import parse_usdc

        assert parse_usdc("1.0") == 1000000
        assert parse_usdc("$1.0") == 1000000
        assert parse_usdc("1") == 1000000

    def test_format_usdc_edge_cases(self):
        from circlekit.boa_utils import format_usdc

        assert format_usdc(0) == "0.000000"
        large = format_usdc(1000000000000)
        assert "1000000" in large

    def test_private_key_formats(self):
        from circlekit.boa_utils import get_account_from_private_key

        key = "0000000000000000000000000000000000000000000000000000000000000001"
        addr1, _ = get_account_from_private_key("0x" + key)
        addr2, _ = get_account_from_private_key(key)
        assert addr1 == addr2

    def test_invalid_private_key(self):
        from circlekit.boa_utils import get_account_from_private_key

        with pytest.raises((ValueError, Exception)):
            get_account_from_private_key("not-a-valid-key")

    def test_normalize_rejects_short_key(self):
        from circlekit.key_utils import normalize_private_key

        with pytest.raises(ValueError, match="64 hex chars"):
            normalize_private_key("0xdead")

    def test_normalize_strips_trailing_newline(self):
        from circlekit.key_utils import normalize_private_key

        key = "0x0000000000000000000000000000000000000000000000000000000000000001"
        assert normalize_private_key(key + "\n") == key


class TestChainConfigCompleteness:
    """Ensure all chain configs are complete and valid."""

    def test_all_chains_have_required_fields(self):
        from circlekit.constants import CHAIN_CONFIGS

        for chain_name, config in CHAIN_CONFIGS.items():
            for field_name in [
                "chain_id",
                "name",
                "rpc_url",
                "usdc_address",
                "gateway_address",
                "gateway_minter",
                "gateway_domain",
            ]:
                value = getattr(config, field_name, None)
                assert value is not None, f"{chain_name} missing {field_name}"

    def test_all_chains_have_valid_addresses(self):
        import re

        from circlekit.constants import CHAIN_CONFIGS

        pattern = re.compile(r"^0x[a-fA-F0-9]{40}$")
        for chain_name, config in CHAIN_CONFIGS.items():
            assert pattern.match(config.usdc_address), f"{chain_name} invalid usdc_address"
            assert pattern.match(config.gateway_address), f"{chain_name} invalid gateway_address"
            assert pattern.match(config.gateway_minter), f"{chain_name} invalid gateway_minter"

    def test_all_chains_have_valid_rpc_urls(self):
        from circlekit.constants import CHAIN_CONFIGS

        for chain_name, config in CHAIN_CONFIGS.items():
            assert config.rpc_url.startswith("https://"), f"{chain_name} RPC should use HTTPS"

    def test_chain_ids_are_unique(self):
        from circlekit.constants import CHAIN_CONFIGS

        chain_ids = [c.chain_id for c in CHAIN_CONFIGS.values()]
        assert len(chain_ids) == len(set(chain_ids))


class TestErrorHandling:
    """Test error handling in various scenarios."""

    def test_unsupported_chain(self):
        from circlekit.client import GatewayClient

        with pytest.raises(ValueError, match="Unsupported chain"):
            GatewayClient(
                chain="nonexistent-chain",
                private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
            )

    @pytest.mark.asyncio
    async def test_network_timeout_handling(self):
        import httpx
        from circlekit.client import GatewayClient

        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        with patch.object(client._http, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.TimeoutException("Connection timed out")
            result = await client.supports("http://slow-server.example.com")
            assert result.supported is False or result.error is not None
        await client.close()


class TestSecurity:
    """Test security-related aspects."""

    def test_private_key_signer_repr_safe(self):
        from circlekit.signer import PrivateKeySigner

        pk = "0x0000000000000000000000000000000000000000000000000000000000000001"
        signer = PrivateKeySigner(pk)
        for text in (repr(signer), str(signer)):
            assert pk not in text
            assert pk[2:] not in text

    def test_boa_tx_executor_repr_safe(self):
        from circlekit.tx_executor import BoaTxExecutor

        pk = "0x0000000000000000000000000000000000000000000000000000000000000001"
        executor = BoaTxExecutor(pk)
        for text in (repr(executor), str(executor)):
            assert pk not in text
            assert pk[2:] not in text

    def test_executor_constructor_error_hides_key(self):
        from circlekit.tx_executor import BoaTxExecutor

        bad_key = "0xdeadbeef"
        try:
            BoaTxExecutor(bad_key)
        except ValueError as e:
            assert "deadbeef" not in str(e)

    def test_signer_constructor_error_hides_key(self):
        from circlekit.signer import PrivateKeySigner

        bad_key = "0xdeadbeef"
        try:
            PrivateKeySigner(bad_key)
        except ValueError as e:
            assert "deadbeef" not in str(e)

    def test_signature_includes_nonce(self):
        from circlekit.signer import PrivateKeySigner
        from circlekit.x402 import PaymentRequirements, create_payment_payload

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
        p1 = create_payment_payload(signer, requirements)
        p2 = create_payment_payload(signer, requirements)
        assert p1.signature != p2.signature

    def test_private_key_not_in_header(self):
        from circlekit.signer import PrivateKeySigner
        from circlekit.x402 import PaymentRequirements, create_payment_header

        pk = "0x0000000000000000000000000000000000000000000000000000000000000001"
        signer = PrivateKeySigner(pk)
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
        header = create_payment_header(signer, requirements)
        decoded = base64.b64decode(header).decode()
        assert pk not in decoded
        assert pk.replace("0x", "") not in decoded


class TestPaymentAmounts:
    """Test payment amount handling."""

    def test_minimum_payment(self):
        from circlekit.signer import PrivateKeySigner
        from circlekit.x402 import PaymentRequirements, create_payment_payload

        signer = PrivateKeySigner(
            "0x0000000000000000000000000000000000000000000000000000000000000001"
        )
        requirements = PaymentRequirements(
            scheme="exact",
            network="eip155:5042002",
            asset="0x3600000000000000000000000000000000000000",
            amount="1",
            pay_to="0x1234567890123456789012345678901234567890",
            extra={
                "name": "GatewayWalletBatched",
                "version": "1",
                "verifyingContract": "0x0077777d7EBA4688BDeF3E311b846F25870A19B9",
            },
        )
        payload = create_payment_payload(signer, requirements)
        assert payload.authorization["value"] == "1"


class TestConcurrency:
    """Test concurrent operations."""

    @pytest.mark.asyncio
    async def test_multiple_clients_concurrent(self):
        from circlekit.client import GatewayClient

        clients = []
        for i in range(3):
            pk = f"0x000000000000000000000000000000000000000000000000000000000000000{i + 1}"
            client = GatewayClient(chain="arcTestnet", private_key=pk)
            clients.append(client)
        addresses = [c.address for c in clients]
        assert len(set(addresses)) == 3
        for client in clients:
            await client.close()

    def test_multiple_signatures_independent(self):
        from circlekit.signer import PrivateKeySigner
        from circlekit.x402 import PaymentRequirements, create_payment_payload

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
        signatures = []
        for _ in range(5):
            payload = create_payment_payload(signer, requirements)
            signatures.append(payload.signature)
        assert len(set(signatures)) == 5


class TestDecimalPrecision:
    """Test USDC decimal handling (6 decimals)."""

    def test_parse_usdc_precision(self):
        from circlekit.boa_utils import parse_usdc

        assert parse_usdc("1.0") == 1_000_000
        assert parse_usdc("0.1") == 100_000
        assert parse_usdc("0.01") == 10_000
        assert parse_usdc("0.001") == 1_000
        assert parse_usdc("0.0001") == 100
        assert parse_usdc("0.00001") == 10
        assert parse_usdc("0.000001") == 1

    def test_round_trip_usdc(self):
        from circlekit.boa_utils import format_usdc, parse_usdc

        test_values = [0, 1, 100, 1000, 1000000, 123456789]
        for val in test_values:
            formatted = format_usdc(val)
            parsed = parse_usdc(formatted)
            assert parsed == val, f"Round trip failed: {val} -> {formatted} -> {parsed}"


class TestNonceGeneration:
    """Test nonce generation for replay protection."""

    def test_nonces_are_unique(self):
        from circlekit.boa_utils import generate_nonce

        nonces = [generate_nonce() for _ in range(1000)]
        assert len(set(nonces)) == 1000

    def test_nonce_is_bytes32(self):
        from circlekit.boa_utils import generate_nonce

        nonce = generate_nonce()
        assert isinstance(nonce, bytes)
        assert len(nonce) == 32


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
