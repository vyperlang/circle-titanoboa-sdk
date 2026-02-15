"""
Parity Tests - Verify Python SDK matches TypeScript SDK structure.

Run: pytest tests/test_parity.py -v
"""

from dataclasses import fields

import pytest


class TestGatewayClientStructure:
    """Verify GatewayClient has same structure as TypeScript SDK."""

    def test_gatewayclient_exists(self):
        from circlekit import GatewayClient

        assert GatewayClient is not None

    def test_gatewayclient_constructor_params(self):
        import inspect

        from circlekit.client import GatewayClient

        sig = inspect.signature(GatewayClient.__init__)
        params = list(sig.parameters.keys())
        assert "chain" in params
        assert "signer" in params
        assert "rpc_url" in params
        assert "private_key" in params  # backwards compat

    def test_gatewayclient_has_properties(self):
        from circlekit.client import GatewayClient

        assert hasattr(GatewayClient, "address")
        assert hasattr(GatewayClient, "chain_name")
        assert hasattr(GatewayClient, "chain_id")
        assert hasattr(GatewayClient, "domain")

    def test_gatewayclient_has_methods(self):
        from circlekit.client import GatewayClient

        assert callable(getattr(GatewayClient, "deposit", None))
        assert callable(getattr(GatewayClient, "pay", None))
        assert callable(getattr(GatewayClient, "withdraw", None))
        assert callable(getattr(GatewayClient, "get_balances", None))
        assert callable(getattr(GatewayClient, "supports", None))


class TestDataClassParity:
    """Verify data classes match TypeScript SDK types."""

    def test_deposit_result_fields(self):
        from circlekit.client import DepositResult

        field_names = {f.name for f in fields(DepositResult)}
        assert "approval_tx_hash" in field_names
        assert "deposit_tx_hash" in field_names
        assert "amount" in field_names
        assert "formatted_amount" in field_names

    def test_pay_result_fields(self):
        from circlekit.client import PayResult

        field_names = {f.name for f in fields(PayResult)}
        assert "data" in field_names
        assert "amount" in field_names
        assert "formatted_amount" in field_names
        assert "transaction" in field_names
        assert "status" in field_names

    def test_withdraw_result_fields(self):
        from circlekit.client import WithdrawResult

        field_names = {f.name for f in fields(WithdrawResult)}
        assert "mint_tx_hash" in field_names
        assert "amount" in field_names
        assert "formatted_amount" in field_names
        assert "source_chain" in field_names
        assert "destination_chain" in field_names
        assert "recipient" in field_names

    def test_gateway_balance_fields(self):
        from circlekit.client import GatewayBalance

        field_names = {f.name for f in fields(GatewayBalance)}
        assert "total" in field_names
        assert "available" in field_names
        assert "withdrawing" in field_names
        assert "withdrawable" in field_names

    def test_balances_structure(self):
        from circlekit.client import Balances

        field_names = {f.name for f in fields(Balances)}
        assert "wallet" in field_names
        assert "gateway" in field_names


class TestMiddlewareParity:
    """Verify middleware matches TypeScript createGatewayMiddleware."""

    def test_middleware_exists(self):
        from circlekit import create_gateway_middleware

        assert create_gateway_middleware is not None

    def test_middleware_has_process_request(self):
        """Middleware should have process_request method (framework-agnostic)."""
        from circlekit import create_gateway_middleware

        middleware = create_gateway_middleware(
            seller_address="0x0000000000000000000000000000000000000000",
            chain="arcTestnet",
        )
        assert hasattr(middleware, "process_request")
        assert callable(middleware.process_request)


class TestX402ProtocolParity:
    """Verify x402 protocol helpers match TypeScript SDK."""

    def test_parse_402_response_exists(self):
        from circlekit import parse_402_response

        assert parse_402_response is not None

    def test_create_payment_header_exists(self):
        from circlekit import create_payment_header

        assert create_payment_header is not None

    def test_is_batch_payment_exists(self):
        from circlekit import is_batch_payment

        assert is_batch_payment is not None

    def test_get_verifying_contract_exists(self):
        from circlekit import get_verifying_contract

        assert get_verifying_contract is not None

    def test_batch_evm_scheme_exists(self):
        from circlekit import BatchEvmScheme

        assert BatchEvmScheme is not None


class TestSignerParity:
    """Verify Signer/PrivateKeySigner match TS BatchEvmSigner interface."""

    def test_signer_protocol_exists(self):
        from circlekit import Signer

        assert Signer is not None

    def test_private_key_signer_exists(self):
        from circlekit import PrivateKeySigner

        assert PrivateKeySigner is not None

    def test_facilitator_client_exists(self):
        from circlekit import BatchFacilitatorClient

        assert BatchFacilitatorClient is not None


class TestConstantsParity:
    """Verify constants match TypeScript SDK."""

    def test_circle_batching_name(self):
        from circlekit import CIRCLE_BATCHING_NAME

        assert CIRCLE_BATCHING_NAME == "GatewayWalletBatched"

    def test_circle_batching_version(self):
        from circlekit import CIRCLE_BATCHING_VERSION

        assert CIRCLE_BATCHING_VERSION == "1"

    def test_circle_batching_scheme(self):
        from circlekit import CIRCLE_BATCHING_SCHEME

        assert CIRCLE_BATCHING_SCHEME == "exact"

    def test_chain_aliases(self):
        """TS uses 'sepolia' and 'mainnet', so we should support both."""
        from circlekit.constants import get_chain_config

        sepolia = get_chain_config("sepolia")
        assert sepolia.chain_id == 11155111  # Ethereum Sepolia
        mainnet = get_chain_config("mainnet")
        assert mainnet.chain_id == 1  # Ethereum


class TestFacilitatorParity:
    """Verify facilitator response types match TS SDK."""

    def test_verify_response_fields(self):
        from dataclasses import fields

        from circlekit.facilitator import VerifyResponse

        field_names = {f.name for f in fields(VerifyResponse)}
        assert "is_valid" in field_names
        assert "payer" in field_names
        assert "invalid_reason" in field_names

    def test_settle_response_fields(self):
        from dataclasses import fields

        from circlekit.facilitator import SettleResponse

        field_names = {f.name for f in fields(SettleResponse)}
        assert "success" in field_names
        assert "transaction" in field_names
        assert "error_reason" in field_names
        assert "payer" in field_names


class TestNoHallucinations:
    """Tests that specifically catch hallucinated functionality."""

    def test_wallets_module_removed(self):
        """wallets.py should not exist anymore."""
        with pytest.raises(ImportError):
            from circlekit.wallets import AgentWalletManager  # noqa: F401

    def test_no_flask_imports(self):
        """server.py should not import Flask."""
        import inspect

        import circlekit.server as server_mod

        source = inspect.getsource(server_mod)
        assert "from flask" not in source
        assert "import flask" not in source

    def test_no_fastapi_imports(self):
        """server.py should not import FastAPI."""
        import inspect

        import circlekit.server as server_mod

        source = inspect.getsource(server_mod)
        assert "from fastapi" not in source
        assert "import fastapi" not in source
