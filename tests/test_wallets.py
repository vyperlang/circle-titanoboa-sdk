"""
AgentWalletManager Tests for circlekit-py

Tests for Circle Programmable Wallets integration.

These tests require:
- CIRCLE_API_KEY environment variable
- CIRCLE_ENTITY_SECRET environment variable

Run with: CIRCLE_API_KEY=... CIRCLE_ENTITY_SECRET=... pytest tests/test_wallets.py -v

Note: Some tests create real wallet sets and wallets in your Circle account.
"""

import pytest
import os
from unittest.mock import patch, MagicMock
from dataclasses import fields

# Check if we have Circle credentials
HAS_CIRCLE_CREDS = bool(
    os.environ.get("CIRCLE_API_KEY") and os.environ.get("CIRCLE_ENTITY_SECRET")
)
SKIP_REASON = "CIRCLE_API_KEY or CIRCLE_ENTITY_SECRET not set"


# =============================================================================
# UNIT TESTS (No credentials required)
# =============================================================================

class TestAgentWalletDataClasses:
    """Test data class structures."""
    
    def test_agent_wallet_fields(self):
        """AgentWallet should have correct fields."""
        from circlekit.wallets import AgentWallet
        
        field_names = {f.name for f in fields(AgentWallet)}
        
        assert "wallet_id" in field_names
        assert "address" in field_names
        assert "blockchain" in field_names
        assert "name" in field_names
        assert "state" in field_names
        assert "wallet_set_id" in field_names
    
    def test_wallet_set_fields(self):
        """WalletSet should have correct fields."""
        from circlekit.wallets import WalletSet
        
        field_names = {f.name for f in fields(WalletSet)}
        
        assert "wallet_set_id" in field_names
        assert "name" in field_names
        assert "custody_type" in field_names
    
    def test_signature_result_fields(self):
        """SignatureResult should have correct fields."""
        from circlekit.wallets import SignatureResult
        
        field_names = {f.name for f in fields(SignatureResult)}
        
        assert "signature" in field_names
        assert "wallet_id" in field_names


class TestBlockchainMapping:
    """Test blockchain name normalization."""
    
    def test_testnet_mappings(self):
        """Testnet chains should map correctly."""
        from circlekit.wallets import BLOCKCHAIN_MAPPING
        
        assert BLOCKCHAIN_MAPPING["arcTestnet"] == "ARC-TESTNET"
        assert BLOCKCHAIN_MAPPING["baseSepolia"] == "BASE-SEPOLIA"
        assert BLOCKCHAIN_MAPPING["ethereumSepolia"] == "ETH-SEPOLIA"
        assert BLOCKCHAIN_MAPPING["avalancheFuji"] == "AVAX-FUJI"
    
    def test_mainnet_mappings(self):
        """Mainnet chains should map correctly."""
        from circlekit.wallets import BLOCKCHAIN_MAPPING
        
        assert BLOCKCHAIN_MAPPING["ethereum"] == "ETH"
        assert BLOCKCHAIN_MAPPING["base"] == "BASE"
        assert BLOCKCHAIN_MAPPING["polygon"] == "MATIC"
        assert BLOCKCHAIN_MAPPING["arbitrum"] == "ARB"
        assert BLOCKCHAIN_MAPPING["avalanche"] == "AVAX"
        assert BLOCKCHAIN_MAPPING["optimism"] == "OP"
    
    def test_alternate_formats(self):
        """Alternate format names should also work."""
        from circlekit.wallets import BLOCKCHAIN_MAPPING
        
        # Both formats should map to the same value
        assert BLOCKCHAIN_MAPPING["ARC_TESTNET"] == "ARC-TESTNET"
        assert BLOCKCHAIN_MAPPING["BASE_SEPOLIA"] == "BASE-SEPOLIA"


class TestAgentWalletManagerInit:
    """Test AgentWalletManager initialization."""
    
    def test_requires_api_key(self):
        """Should raise error without API key."""
        from circlekit.wallets import AgentWalletManager
        
        # Clear env vars temporarily
        with patch.dict(os.environ, {"CIRCLE_API_KEY": "", "CIRCLE_ENTITY_SECRET": "test"}):
            with pytest.raises(ValueError) as exc_info:
                AgentWalletManager(api_key=None)
            
            assert "API key required" in str(exc_info.value)
    
    def test_requires_entity_secret(self):
        """Should raise error without entity secret."""
        from circlekit.wallets import AgentWalletManager
        
        with patch.dict(os.environ, {"CIRCLE_API_KEY": "test", "CIRCLE_ENTITY_SECRET": ""}):
            with pytest.raises(ValueError) as exc_info:
                AgentWalletManager(api_key="test", entity_secret=None)
            
            assert "entity secret required" in str(exc_info.value)
    
    def test_accepts_params_directly(self):
        """Should accept credentials as parameters."""
        from circlekit.wallets import AgentWalletManager
        
        # Mock the Circle SDK initialization
        with patch("circlekit.wallets.init_developer_controlled_wallets_client"):
            with patch("circlekit.wallets.generate_entity_secret_ciphertext"):
                with patch("circlekit.wallets.WalletsApi"):
                    with patch("circlekit.wallets.WalletSetsApi"):
                        with patch("circlekit.wallets.SigningApi"):
                            manager = AgentWalletManager(
                                api_key="test-api-key",
                                entity_secret="test-entity-secret"
                            )
                            
                            assert manager._api_key == "test-api-key"
                            assert manager._entity_secret == "test-entity-secret"
    
    def test_reads_from_env_vars(self):
        """Should read credentials from environment variables."""
        from circlekit.wallets import AgentWalletManager
        
        with patch.dict(os.environ, {
            "CIRCLE_API_KEY": "env-api-key",
            "CIRCLE_ENTITY_SECRET": "env-entity-secret"
        }):
            with patch("circlekit.wallets.init_developer_controlled_wallets_client"):
                with patch("circlekit.wallets.generate_entity_secret_ciphertext"):
                    with patch("circlekit.wallets.WalletsApi"):
                        with patch("circlekit.wallets.WalletSetsApi"):
                            with patch("circlekit.wallets.SigningApi"):
                                manager = AgentWalletManager()
                                
                                assert manager._api_key == "env-api-key"
                                assert manager._entity_secret == "env-entity-secret"


class TestHelperFunction:
    """Test the create_agent_wallet_manager helper."""
    
    def test_create_agent_wallet_manager_exists(self):
        """Helper function should be importable."""
        from circlekit.wallets import create_agent_wallet_manager
        
        assert callable(create_agent_wallet_manager)
    
    def test_creates_manager_instance(self):
        """Helper should create AgentWalletManager instance."""
        from circlekit.wallets import create_agent_wallet_manager, AgentWalletManager
        
        with patch.dict(os.environ, {
            "CIRCLE_API_KEY": "test-key",
            "CIRCLE_ENTITY_SECRET": "test-secret"
        }):
            with patch("circlekit.wallets.init_developer_controlled_wallets_client"):
                with patch("circlekit.wallets.generate_entity_secret_ciphertext"):
                    with patch("circlekit.wallets.WalletsApi"):
                        with patch("circlekit.wallets.WalletSetsApi"):
                            with patch("circlekit.wallets.SigningApi"):
                                manager = create_agent_wallet_manager()
                                
                                assert isinstance(manager, AgentWalletManager)


# =============================================================================
# MOCK TESTS (Simulate Circle API responses)
# =============================================================================

class TestMockedWalletOperations:
    """Test wallet operations with mocked Circle API."""
    
    @pytest.fixture
    def mock_manager(self):
        """Create a manager with mocked Circle SDK."""
        from circlekit.wallets import AgentWalletManager
        
        with patch.dict(os.environ, {
            "CIRCLE_API_KEY": "test-key",
            "CIRCLE_ENTITY_SECRET": "test-secret"
        }):
            with patch("circlekit.wallets.init_developer_controlled_wallets_client"):
                with patch("circlekit.wallets.generate_entity_secret_ciphertext") as mock_cipher:
                    mock_cipher.return_value = "mock-ciphertext"
                    with patch("circlekit.wallets.WalletsApi") as mock_wallets:
                        with patch("circlekit.wallets.WalletSetsApi") as mock_sets:
                            with patch("circlekit.wallets.SigningApi") as mock_signing:
                                manager = AgentWalletManager()
                                manager._mock_wallets_api = mock_wallets.return_value
                                manager._mock_wallet_sets_api = mock_sets.return_value
                                manager._mock_signing_api = mock_signing.return_value
                                yield manager
    
    def test_normalize_blockchain_arc(self, mock_manager):
        """Should normalize arcTestnet to ARC-TESTNET."""
        result = mock_manager._normalize_blockchain("arcTestnet")
        assert result == "ARC-TESTNET"
    
    def test_normalize_blockchain_passthrough(self, mock_manager):
        """Unknown blockchain names should pass through."""
        result = mock_manager._normalize_blockchain("UNKNOWN-CHAIN")
        assert result == "UNKNOWN-CHAIN"
    
    def test_generate_idempotency_key(self, mock_manager):
        """Should generate unique idempotency keys."""
        key1 = mock_manager._generate_idempotency_key()
        key2 = mock_manager._generate_idempotency_key()
        
        assert key1 != key2
        # Should be valid UUID format
        assert len(key1) == 36  # UUID format: 8-4-4-4-12


# =============================================================================
# INTEGRATION TESTS (Require Circle credentials)
# =============================================================================

class TestLiveWalletOperations:
    """Test against real Circle API.
    
    ⚠️  These tests create real resources in your Circle account!
    """
    
    @pytest.fixture
    def live_manager(self):
        """Create a manager with real Circle credentials."""
        if not HAS_CIRCLE_CREDS:
            pytest.skip(SKIP_REASON)
        
        from circlekit.wallets import AgentWalletManager
        return AgentWalletManager()
    
    @pytest.mark.skipif(not HAS_CIRCLE_CREDS, reason=SKIP_REASON)
    def test_list_wallet_sets(self, live_manager):
        """Should list wallet sets from Circle API."""
        wallet_sets = live_manager.list_wallet_sets()
        
        print(f"\nFound {len(wallet_sets)} wallet set(s)")
        for ws in wallet_sets:
            print(f"  - {ws.name} ({ws.wallet_set_id})")
        
        # Should return a list (even if empty)
        assert isinstance(wallet_sets, list)
    
    @pytest.mark.skipif(not HAS_CIRCLE_CREDS, reason=SKIP_REASON)
    def test_list_wallets(self, live_manager):
        """Should list wallets from Circle API."""
        wallets = live_manager.list_wallets()
        
        print(f"\nFound {len(wallets)} wallet(s)")
        for w in wallets[:5]:  # Show first 5
            print(f"  - {w.name}: {w.address} ({w.blockchain})")
        
        # Should return a list (even if empty)
        assert isinstance(wallets, list)
    
    @pytest.mark.skipif(not HAS_CIRCLE_CREDS, reason=SKIP_REASON)
    def test_create_wallet_set(self, live_manager):
        """Should create a new wallet set.
        
        ⚠️  This creates a real wallet set in your Circle account!
        """
        import uuid
        
        # Use unique name to avoid conflicts
        name = f"pytest-{uuid.uuid4().hex[:8]}"
        
        wallet_set = live_manager.create_wallet_set(name)
        
        print(f"\nCreated wallet set:")
        print(f"  - ID: {wallet_set.wallet_set_id}")
        print(f"  - Name: {wallet_set.name}")
        
        assert wallet_set.wallet_set_id is not None
        assert len(wallet_set.wallet_set_id) > 0
    
    @pytest.mark.skipif(not HAS_CIRCLE_CREDS, reason=SKIP_REASON)
    def test_create_wallet(self, live_manager):
        """Should create a new wallet on Arc Testnet.
        
        ⚠️  This creates a real wallet in your Circle account!
        """
        import uuid
        
        # First, get or create a wallet set
        wallet_sets = live_manager.list_wallet_sets()
        
        if wallet_sets:
            wallet_set_id = wallet_sets[0].wallet_set_id
            print(f"\nUsing existing wallet set: {wallet_set_id}")
        else:
            # Create a new wallet set
            ws = live_manager.create_wallet_set(f"pytest-{uuid.uuid4().hex[:8]}")
            wallet_set_id = ws.wallet_set_id
            print(f"\nCreated wallet set: {wallet_set_id}")
        
        # Create a wallet
        wallet_name = f"pytest-agent-{uuid.uuid4().hex[:8]}"
        
        wallet = live_manager.create_wallet(
            wallet_set_id=wallet_set_id,
            name=wallet_name,
            blockchain="arcTestnet"
        )
        
        print(f"\nCreated wallet:")
        print(f"  - ID: {wallet.wallet_id}")
        print(f"  - Address: {wallet.address}")
        print(f"  - Blockchain: {wallet.blockchain}")
        print(f"  - State: {wallet.state}")
        
        assert wallet.wallet_id is not None
        assert wallet.address is not None
        assert wallet.address.startswith("0x")
        assert len(wallet.address) == 42
    
    @pytest.mark.skipif(not HAS_CIRCLE_CREDS, reason=SKIP_REASON)
    def test_sign_message(self, live_manager):
        """Should sign a message using a Circle wallet.
        
        ⚠️  Requires at least one wallet to exist!
        """
        wallets = live_manager.list_wallets()
        
        if not wallets:
            pytest.skip("No wallets available for signing test")
        
        wallet = wallets[0]
        message = "Hello from circlekit-py test!"
        
        print(f"\nSigning message with wallet {wallet.wallet_id}")
        print(f"  Message: {message}")
        
        result = live_manager.sign_message(wallet.wallet_id, message)
        
        print(f"  Signature: {result.signature[:40]}...")
        
        assert result.signature is not None
        assert result.signature.startswith("0x")
        assert len(result.signature) > 50  # Should be a real signature
    
    @pytest.mark.skipif(not HAS_CIRCLE_CREDS, reason=SKIP_REASON)
    def test_sign_typed_data(self, live_manager):
        """Should sign EIP-712 typed data.
        
        ⚠️  Requires at least one wallet to exist!
        """
        wallets = live_manager.list_wallets()
        
        if not wallets:
            pytest.skip("No wallets available for signing test")
        
        wallet = wallets[0]
        
        # EIP-712 typed data for a payment
        typed_data = {
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                ],
                "Message": [
                    {"name": "content", "type": "string"},
                ],
            },
            "primaryType": "Message",
            "domain": {
                "name": "Test",
                "version": "1",
                "chainId": 5042002,  # Arc Testnet
            },
            "message": {
                "content": "Test typed data signing",
            },
        }
        
        print(f"\nSigning typed data with wallet {wallet.wallet_id}")
        
        result = live_manager.sign_typed_data(wallet.wallet_id, typed_data)
        
        print(f"  Signature: {result.signature[:40]}...")
        
        assert result.signature is not None
        assert result.signature.startswith("0x")
    
    @pytest.mark.skipif(not HAS_CIRCLE_CREDS, reason=SKIP_REASON)
    def test_get_wallet_balance(self, live_manager):
        """Should get wallet token balances.
        
        ⚠️  Requires at least one wallet to exist!
        """
        wallets = live_manager.list_wallets()
        
        if not wallets:
            pytest.skip("No wallets available for balance test")
        
        wallet = wallets[0]
        
        print(f"\nGetting balance for wallet {wallet.wallet_id}")
        
        balances = live_manager.get_wallet_balance(wallet.wallet_id)
        
        print(f"  Found {len(balances)} token(s):")
        for b in balances:
            print(f"    - {b['token']}: {b['amount']}")
        
        # Should return a list (even if empty)
        assert isinstance(balances, list)


# =============================================================================
# EXPORT TESTS
# =============================================================================

class TestExports:
    """Test that wallet classes are properly exported."""
    
    def test_agentwalletmanager_importable_from_circlekit(self):
        """AgentWalletManager should be importable from circlekit."""
        from circlekit import AgentWalletManager
        assert AgentWalletManager is not None
    
    def test_agentwallet_importable(self):
        """AgentWallet dataclass should be importable."""
        from circlekit.wallets import AgentWallet
        assert AgentWallet is not None
    
    def test_walletset_importable(self):
        """WalletSet dataclass should be importable."""
        from circlekit.wallets import WalletSet
        assert WalletSet is not None
    
    def test_create_agent_wallet_manager_importable(self):
        """Helper function should be importable from circlekit."""
        from circlekit import create_agent_wallet_manager
        assert callable(create_agent_wallet_manager)


# =============================================================================
# SUMMARY
# =============================================================================

if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════════════════════════╗
    ║              AGENT WALLET MANAGER TESTS                           ║
    ╠══════════════════════════════════════════════════════════════════╣
    ║ Unit tests: Run without credentials                               ║
    ║ Integration tests: Require CIRCLE_API_KEY & CIRCLE_ENTITY_SECRET  ║
    ║                                                                   ║
    ║ Run all: pytest tests/test_wallets.py -v                          ║
    ║ Run unit only: pytest tests/test_wallets.py -v -k "not Live"      ║
    ║                                                                   ║
    ║ ⚠️  Integration tests create real resources in Circle!            ║
    ╚══════════════════════════════════════════════════════════════════╝
    """)
    pytest.main([__file__, "-v"])
