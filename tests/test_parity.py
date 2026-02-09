"""
Parity Tests - Verify Python SDK matches TypeScript SDK structure.

These tests catch hallucinations by verifying:
1. API structure matches TypeScript SDK
2. Data classes have correct fields
3. Method signatures are correct
4. No fabricated functionality

Run: pytest tests/test_parity.py -v
"""

import pytest
from dataclasses import fields


class TestGatewayClientStructure:
    """Verify GatewayClient has same structure as TypeScript SDK."""

    def test_gatewayclient_exists(self):
        """GatewayClient should be importable."""
        from circlekit import GatewayClient
        assert GatewayClient is not None

    def test_gatewayclient_constructor_params(self):
        """Constructor should accept chain, private_key, rpc_url."""
        from circlekit.client import GatewayClient
        import inspect
        
        sig = inspect.signature(GatewayClient.__init__)
        params = list(sig.parameters.keys())
        
        # TypeScript: chain, privateKey, rpcUrl?
        assert "chain" in params, "Missing 'chain' parameter"
        assert "private_key" in params, "Missing 'private_key' parameter"
        assert "rpc_url" in params, "Missing 'rpc_url' parameter"

    def test_gatewayclient_has_properties(self):
        """Should have address, chain_name, chain_id, domain properties."""
        from circlekit.client import GatewayClient
        
        # Check properties exist (without instantiating)
        assert hasattr(GatewayClient, "address")
        assert hasattr(GatewayClient, "chain_name")
        assert hasattr(GatewayClient, "chain_id")
        assert hasattr(GatewayClient, "domain")

    def test_gatewayclient_has_methods(self):
        """Should have pay, deposit, withdraw, get_balances, supports methods."""
        from circlekit.client import GatewayClient
        
        # TypeScript methods: deposit, pay, withdraw, getBalances, supports
        assert callable(getattr(GatewayClient, "deposit", None)), "Missing deposit method"
        assert callable(getattr(GatewayClient, "pay", None)), "Missing pay method"
        assert callable(getattr(GatewayClient, "withdraw", None)), "Missing withdraw method"
        assert callable(getattr(GatewayClient, "get_balances", None)), "Missing get_balances method"
        assert callable(getattr(GatewayClient, "supports", None)), "Missing supports method"


class TestDataClassParity:
    """Verify data classes match TypeScript SDK types."""

    def test_deposit_result_fields(self):
        """DepositResult should match TypeScript DepositResult."""
        from circlekit.client import DepositResult
        
        field_names = {f.name for f in fields(DepositResult)}
        
        # TypeScript: approvalTxHash?, depositTxHash, amount, formattedAmount
        assert "approval_tx_hash" in field_names, "Missing approval_tx_hash"
        assert "deposit_tx_hash" in field_names, "Missing deposit_tx_hash"
        assert "amount" in field_names, "Missing amount"
        assert "formatted_amount" in field_names, "Missing formatted_amount"

    def test_pay_result_fields(self):
        """PayResult should match TypeScript PayResult."""
        from circlekit.client import PayResult
        
        field_names = {f.name for f in fields(PayResult)}
        
        # TypeScript: data, amount, formattedAmount, transaction, status
        assert "data" in field_names, "Missing data"
        assert "amount" in field_names, "Missing amount"
        assert "formatted_amount" in field_names, "Missing formatted_amount"
        assert "transaction" in field_names, "Missing transaction"
        assert "status" in field_names, "Missing status"

    def test_withdraw_result_fields(self):
        """WithdrawResult should match TypeScript WithdrawResult."""
        from circlekit.client import WithdrawResult
        
        field_names = {f.name for f in fields(WithdrawResult)}
        
        # TypeScript: mintTxHash, amount, formattedAmount, sourceChain, destinationChain, recipient
        assert "mint_tx_hash" in field_names, "Missing mint_tx_hash"
        assert "amount" in field_names, "Missing amount"
        assert "formatted_amount" in field_names, "Missing formatted_amount"
        assert "source_chain" in field_names, "Missing source_chain"
        assert "destination_chain" in field_names, "Missing destination_chain"
        assert "recipient" in field_names, "Missing recipient"

    def test_gateway_balance_fields(self):
        """GatewayBalance should match TypeScript GatewayBalance."""
        from circlekit.client import GatewayBalance
        
        field_names = {f.name for f in fields(GatewayBalance)}
        
        # TypeScript: total, available, withdrawing, withdrawable,
        #             formattedTotal, formattedAvailable, formattedWithdrawing, formattedWithdrawable
        assert "total" in field_names, "Missing total"
        assert "available" in field_names, "Missing available"
        assert "withdrawing" in field_names, "Missing withdrawing"
        assert "withdrawable" in field_names, "Missing withdrawable"
        assert "formatted_total" in field_names, "Missing formatted_total"
        assert "formatted_available" in field_names, "Missing formatted_available"
        assert "formatted_withdrawing" in field_names, "Missing formatted_withdrawing"
        assert "formatted_withdrawable" in field_names, "Missing formatted_withdrawable"

    def test_balances_structure(self):
        """Balances should have wallet and gateway."""
        from circlekit.client import Balances
        
        field_names = {f.name for f in fields(Balances)}
        
        # TypeScript: { wallet: WalletBalance, gateway: GatewayBalance }
        assert "wallet" in field_names, "Missing wallet"
        assert "gateway" in field_names, "Missing gateway"


class TestMiddlewareParity:
    """Verify middleware matches TypeScript createGatewayMiddleware."""

    def test_middleware_exists(self):
        """create_gateway_middleware should be importable."""
        from circlekit import create_gateway_middleware
        assert create_gateway_middleware is not None

    def test_middleware_returns_object_with_require(self):
        """Middleware should return object with require() method."""
        from circlekit import create_gateway_middleware
        
        middleware = create_gateway_middleware(
            seller_address="0x0000000000000000000000000000000000000000",
            chain="arcTestnet",
        )
        
        # TypeScript: gateway.require('$0.01')
        assert hasattr(middleware, "require"), "Missing require method"
        assert callable(middleware.require), "require should be callable"


class TestX402ProtocolParity:
    """Verify x402 protocol helpers match TypeScript SDK."""

    def test_parse_402_response_exists(self):
        """parse_402_response should be importable."""
        from circlekit import parse_402_response
        assert parse_402_response is not None

    def test_create_payment_header_exists(self):
        """create_payment_header should be importable."""
        from circlekit import create_payment_header
        assert create_payment_header is not None

    def test_is_batch_payment_exists(self):
        """is_batch_payment should be importable (supportsBatching in TS)."""
        from circlekit import is_batch_payment
        assert is_batch_payment is not None

    def test_get_verifying_contract_exists(self):
        """get_verifying_contract should be importable."""
        from circlekit import get_verifying_contract
        assert get_verifying_contract is not None


class TestConstantsParity:
    """Verify constants match TypeScript SDK."""

    def test_circle_batching_name(self):
        """CIRCLE_BATCHING_NAME should be 'GatewayWalletBatched'."""
        from circlekit import CIRCLE_BATCHING_NAME
        # Verified from SDK_REFERENCE.md
        assert CIRCLE_BATCHING_NAME == "GatewayWalletBatched"

    def test_circle_batching_version(self):
        """CIRCLE_BATCHING_VERSION should be '1'."""
        from circlekit import CIRCLE_BATCHING_VERSION
        # Verified from SDK_REFERENCE.md
        assert CIRCLE_BATCHING_VERSION == "1"

    def test_circle_batching_scheme(self):
        """CIRCLE_BATCHING_SCHEME should be 'exact'."""
        from circlekit import CIRCLE_BATCHING_SCHEME
        # Verified from SDK_REFERENCE.md
        assert CIRCLE_BATCHING_SCHEME == "exact"


class TestChainConfigParity:
    """Verify chain configs match TypeScript CHAIN_CONFIGS."""

    def test_chain_configs_exists(self):
        """CHAIN_CONFIGS should be importable."""
        from circlekit import CHAIN_CONFIGS
        assert CHAIN_CONFIGS is not None

    def test_arc_testnet_config(self):
        """Arc Testnet should have correct chain ID (5042002)."""
        from circlekit.boa_utils import get_chain_config
        
        config = get_chain_config("arcTestnet")
        # Verified from NETWORKS.md: Arc Testnet = 5042002
        assert config.chain_id == 5042002

    def test_base_sepolia_config(self):
        """Base Sepolia should have correct chain ID (84532)."""
        from circlekit.boa_utils import get_chain_config
        
        config = get_chain_config("baseSepolia")
        # Verified from NETWORKS.md: Base Sepolia = 84532
        assert config.chain_id == 84532


class TestNoHallucinations:
    """Tests that specifically catch hallucinated functionality."""

    def test_no_nonexistent_methods(self):
        """GatewayClient should NOT have methods that don't exist in TS SDK."""
        from circlekit.client import GatewayClient
        
        # These methods exist in TypeScript SDK (should exist):
        valid_methods = {"deposit", "pay", "withdraw", "get_balances", "supports", "close"}
        
        # Check we don't have random extra public methods
        public_methods = {m for m in dir(GatewayClient) if not m.startswith("_") and callable(getattr(GatewayClient, m, None))}
        
        # Remove known valid ones and check what's left
        extra = public_methods - valid_methods
        
        # These are OK (Python boilerplate or contextmanager support)
        allowed_extra = {"__aenter__", "__aexit__"}
        
        suspicious = extra - allowed_extra
        
        # If there are suspicious extra methods, they might be hallucinated
        # This is a soft check - it warns but doesn't fail
        if suspicious:
            # Only fail if these look like fabricated API methods
            fabricated = {m for m in suspicious if not m.startswith("_")}
            assert not fabricated, f"Potentially hallucinated methods: {fabricated}"

    def test_no_fabricated_chains(self):
        """Only support chains documented in NETWORKS.md."""
        from circlekit.boa_utils import CHAIN_CONFIGS
        
        # Chains documented in NETWORKS.md
        documented_chains = {
            # Testnets
            "arcTestnet",       # Arc Testnet (5042002)
            "baseSepolia",      # Base Sepolia (84532)
            "ethereumSepolia",  # Ethereum Sepolia (11155111)
            "avalancheFuji",    # Avalanche Fuji (43113)
            # Mainnets
            "base",             # Base (8453)
            "ethereum",         # Ethereum (1)
            "polygon",          # Polygon (137)
            "arbitrum",         # Arbitrum (42161)
            "avalanche",        # Avalanche (43114)
            "optimism",         # Optimism (10)
        }
        
        configured_chains = set(CHAIN_CONFIGS.keys())
        
        # Every configured chain should be documented
        # (We might not support ALL documented chains, but what we support should be real)
        for chain in configured_chains:
            assert chain in documented_chains, f"Chain '{chain}' is not documented in NETWORKS.md - potentially hallucinated"
